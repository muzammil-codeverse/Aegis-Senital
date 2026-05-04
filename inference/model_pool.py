from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_WORKER_THREAD_NAME = "model-pool-gpu-worker"

# Priority constants (lower number = higher priority)
PRIORITY_CRITICAL = 1
PRIORITY_HIGH = 3
PRIORITY_NORMAL = 5
PRIORITY_LOW = 9


# ── inference request/response protocol ──────────────────────────────────────

@dataclass
class _InferenceRequest:
    """
    Single inference task submitted to the GPU worker thread.

    The priority field controls scheduling order when multiple requests are
    queued: lower values run first (CRITICAL=1 before NORMAL=5 before LOW=9).
    Callers create a fresh SimpleQueue, submit this object to the priority
    queue, then block on their own SimpleQueue to receive the result.
    SimpleQueue is unbounded so the worker never deadlocks while writing
    the response.
    """
    model_type: str                       # "weapon" | "phone"
    frame: np.ndarray
    priority: int = PRIORITY_NORMAL       # Phase 6: scheduling priority
    _result: queue.SimpleQueue = field(default_factory=queue.SimpleQueue)

    def wait(self) -> list:
        """Block until the worker posts a result, then return or re-raise."""
        status, payload = self._result.get()
        if status == "error":
            raise payload
        return payload


# ── singleton model pool ──────────────────────────────────────────────────────

class ModelPool:
    """
    Process-wide singleton holding shared YOLO weapon and phone model instances.

    All stream processors submit inference requests to a single GPU worker
    thread via an internal PriorityQueue.  The worker processes them in
    priority order (CRITICAL first, LOW last) so high-severity streams are
    not starved by background processing.

    Phase-6 change: queue.Queue → queue.PriorityQueue with (priority, seq, req)
    tuples.  The monotonically-increasing seq counter ensures FIFO ordering
    within the same priority tier.

    Lifecycle:
        pool = get_model_pool()
        pool.load(weapon_path, phone_path)   # called once at startup
        results = pool.run_weapon(frame)     # submits to worker, blocks for result
        results = pool.run_weapon(frame, priority=PRIORITY_CRITICAL)  # fast-lane
    """

    _instance: "ModelPool | None" = None
    _class_lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "ModelPool":
        with cls._class_lock:
            if cls._instance is None:
                inst = object.__new__(cls)
                inst._initialized = False
                cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._model_lock: threading.Lock = threading.Lock()
        self._weapon_model: Any | None = None
        self._phone_model: Any | None = None
        self._device: str = "cpu"
        self._model_status: dict[str, str] = {
            "weapon_model": "not_loaded",
            "phone_model": "not_loaded",
        }
        # Phase 6: PriorityQueue replaces plain Queue
        self._request_queue: queue.PriorityQueue = queue.PriorityQueue()
        self._seq_counter: int = 0
        self._seq_lock: threading.Lock = threading.Lock()
        self._shutdown_event: threading.Event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._initialized: bool = True

    # ── model loading ─────────────────────────────────────────────────────────

    def load(self, weapon_path: str, phone_path: str, device: str = "auto") -> None:
        """Load YOLO models once and start the GPU worker thread.  No-op if already loaded."""
        with self._model_lock:
            if self._weapon_model is not None and self._phone_model is not None:
                return
            self._device = self._resolve_device(device)
            self._weapon_model = self._load_one(weapon_path, "weapon_model")
            self._phone_model = self._load_one(phone_path, "phone_model")
            logger.info(
                "ModelPool: both models loaded (device=%s, weapon=%s, phone=%s)",
                self._device, weapon_path, phone_path,
            )
        self._start_worker()

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            return device
        try:
            import torch
            if not torch.cuda.is_available():
                logger.warning("ModelPool: CUDA unavailable — using CPU")
                return "cpu"
            return "cuda"
        except ImportError:
            return "cpu"

    def _load_one(self, path: str, label: str) -> Any:
        from ultralytics import YOLO

        ext = Path(path).suffix.lower()
        if ext not in (".pt", ".onnx"):
            self._model_status[label] = f"error: unsupported format {ext}"
            raise RuntimeError(f"ModelPool: unsupported format for {label}: {path}")
        try:
            model = YOLO(path)
            self._model_status[label] = "loaded"
            logger.info("ModelPool: loaded %s from %s", label, path)
            return model
        except Exception as exc:
            self._model_status[label] = f"error: {exc}"
            raise RuntimeError(f"ModelPool: failed to load {label} from {path}") from exc

    # ── GPU worker thread ─────────────────────────────────────────────────────

    def _start_worker(self) -> None:
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return
        self._shutdown_event.clear()
        self._worker_thread = threading.Thread(
            target=self._gpu_worker_loop,
            name=_WORKER_THREAD_NAME,
            daemon=True,
        )
        self._worker_thread.start()
        logger.info("ModelPool: GPU worker thread started (PriorityQueue scheduler)")

    def _gpu_worker_loop(self) -> None:
        """
        Priority-ordered single-threaded GPU inference loop.

        Reads (priority, seq, _InferenceRequest) tuples from the PriorityQueue.
        CRITICAL priority requests (lower integer) are dequeued before NORMAL
        and LOW requests.  Shutdown is signalled via _shutdown_event so the
        sentinel does not need to be comparable.

        Each request carries its own SimpleQueue for the response so callers
        can block independently without contention.
        """
        while not self._shutdown_event.is_set():
            try:
                item = self._request_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            _, _, req = item
            try:
                if req.model_type == "weapon":
                    result = self._weapon_model(req.frame, verbose=False, device=self._device)
                else:
                    result = self._phone_model(req.frame, verbose=False, device=self._device)
                req._result.put(("ok", result))
            except Exception as exc:
                req._result.put(("error", exc))

    def shutdown(self) -> None:
        """Signal the GPU worker to stop and wait for it to exit."""
        self._shutdown_event.set()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=10.0)

    # ── priority enqueue ──────────────────────────────────────────────────────

    def _enqueue(self, req: _InferenceRequest) -> None:
        """Wrap request in a (priority, seq, req) tuple and push to PriorityQueue."""
        with self._seq_lock:
            seq = self._seq_counter
            self._seq_counter += 1
        self._request_queue.put((req.priority, seq, req))

    # ── public inference interface ────────────────────────────────────────────

    def run_weapon(self, frame: np.ndarray, priority: int = PRIORITY_NORMAL) -> list:
        """Submit a weapon-model inference request and block for the result."""
        if self._weapon_model is None:
            raise RuntimeError("ModelPool: weapon model not loaded — call load() first")
        req = _InferenceRequest(model_type="weapon", frame=frame, priority=priority)
        self._enqueue(req)
        return req.wait()

    def run_phone(self, frame: np.ndarray, priority: int = PRIORITY_NORMAL) -> list:
        """Submit a phone-model inference request and block for the result."""
        if self._phone_model is None:
            raise RuntimeError("ModelPool: phone model not loaded — call load() first")
        req = _InferenceRequest(model_type="phone", frame=frame, priority=priority)
        self._enqueue(req)
        return req.wait()

    # ── class-name maps ───────────────────────────────────────────────────────

    @property
    def weapon_names(self) -> dict:
        return self._weapon_model.names if self._weapon_model is not None else {}

    @property
    def phone_names(self) -> dict:
        return self._phone_model.names if self._phone_model is not None else {}

    # ── status / introspection ────────────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        return self._weapon_model is not None and self._phone_model is not None

    @property
    def model_status(self) -> dict[str, str]:
        return dict(self._model_status)

    @property
    def device(self) -> str:
        return self._device

    @property
    def worker_alive(self) -> bool:
        return self._worker_thread is not None and self._worker_thread.is_alive()

    @property
    def queue_depth(self) -> int:
        """Approximate number of inference requests waiting in the queue."""
        return self._request_queue.qsize()


# Process-wide singleton
_pool: ModelPool = ModelPool()


def get_model_pool() -> ModelPool:
    """Return the process-wide ModelPool singleton."""
    return _pool
