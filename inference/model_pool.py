from __future__ import annotations

import logging
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import numpy as np

logger = logging.getLogger(__name__)
DETERMINISTIC_MODE = os.getenv("AEGIS_DETERMINISTIC", "0") == "1"

_WORKER_THREAD_NAME = "model-pool-gpu-worker"
_GPU_QUEUE_MAXSIZE = 32  # hard cap — requests beyond this are rejected immediately

# Priority constants (lower number = higher priority)
PRIORITY_CRITICAL = 1
PRIORITY_HIGH = 3
PRIORITY_NORMAL = 5
PRIORITY_LOW = 9


# ── inference request/response protocol ──────────────────────────────────────

@dataclass
class _InferenceRequest:
    """
    Single-frame inference task submitted to the GPU worker thread.

    Priority controls scheduling: lower values run first (CRITICAL=1 before
    NORMAL=5 before LOW=9).  The seq counter breaks ties within the same
    priority tier (FIFO).  Each request carries its own SimpleQueue so the
    caller blocks independently without contention.
    """
    model_type: str                       # "weapon" | "phone"
    frame: np.ndarray
    priority: int = PRIORITY_NORMAL
    _result: queue.SimpleQueue = field(default_factory=queue.SimpleQueue)

    def wait(self) -> list:
        status, payload = self._result.get()
        if status == "error":
            raise payload
        return payload


@dataclass
class _BatchInferenceRequest:
    """
    Multi-frame batch inference task.  The GPU worker passes the entire list
    to YOLO in a single forward pass, avoiding per-frame kernel-launch overhead.
    Returns one ultralytics Results object per input frame.
    """
    model_type: str                       # "weapon" | "phone"
    frames: List[np.ndarray]
    priority: int = PRIORITY_NORMAL
    _result: queue.SimpleQueue = field(default_factory=queue.SimpleQueue)

    def wait(self) -> list:
        status, payload = self._result.get()
        if status == "error":
            raise payload
        return payload


# ── singleton model pool ──────────────────────────────────────────────────────

class ModelPool:
    """
    Process-wide singleton holding shared YOLO weapon and phone model instances.

    All stream processors submit inference requests to a single GPU worker
    thread via an internal PriorityQueue (maxsize=32).  The worker processes
    them in priority order (CRITICAL first, LOW last) so high-severity streams
    are not starved by background processing.

    Both single-frame (_InferenceRequest) and multi-frame (_BatchInferenceRequest)
    tasks are supported.  Batch tasks issue one YOLO forward pass for N frames,
    yielding 3-5× better GPU utilisation compared to N sequential single-frame
    calls.

    Queue is bounded (maxsize=32): callers that submit when the queue is full
    receive an immediate RuntimeError ("GPU queue overloaded") instead of
    blocking indefinitely.  The DetectionEngine catches this and returns an
    empty detection list for the frame, preserving pipeline progress.

    Lifecycle:
        pool = get_model_pool()
        pool.load(weapon_path, phone_path)      # once at startup
        results = pool.run_weapon(frame)        # single frame, blocks for result
        results = pool.run_weapon_batch(frames) # batch, blocks for result
        results = pool.run_weapon(frame, priority=PRIORITY_CRITICAL)
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
        # Bounded PriorityQueue — items are (priority, seq, request) tuples.
        self._request_queue: queue.PriorityQueue = queue.PriorityQueue(
            maxsize=_GPU_QUEUE_MAXSIZE
        )
        self._use_half: bool = False   # set to True when FP16 is available
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
            self._use_half = self._device == "cuda"
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
            # Explicitly move model weights to the target device.
            try:
                model.model.to(self._device)
                if self._use_half:
                    model.model.half()   # FP16 weights; ~2× GPU throughput on Ampere+
            except Exception:
                pass  # ultralytics handles device/dtype via runtime args if .half() fails
            self._model_status[label] = "loaded"
            logger.info("ModelPool: loaded %s from %s (device=%s)", label, path, self._device)
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
        logger.info(
            "ModelPool: GPU worker thread started (PriorityQueue, maxsize=%d)",
            _GPU_QUEUE_MAXSIZE,
        )

    def _gpu_worker_loop(self) -> None:
        """
        Priority-ordered single-threaded GPU inference loop.

        Handles both _InferenceRequest (single frame) and _BatchInferenceRequest
        (list of frames).  For batch requests the model is called once with the
        full frame list, which lets CUDA execute all images in a single kernel
        dispatch.
        """
        while not self._shutdown_event.is_set():
            try:
                item = self._request_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            _, _, req = item
            try:
                model = (
                    self._weapon_model
                    if req.model_type == "weapon"
                    else self._phone_model
                )
                _t_infer = time.monotonic()
                if isinstance(req, _BatchInferenceRequest):
                    if DETERMINISTIC_MODE:
                        req.frames = list(req.frames)
                    result = model(
                        req.frames,
                        verbose=False,
                        device=self._device,
                        half=self._use_half,
                    )
                else:
                    result = model(
                        req.frame,
                        verbose=False,
                        device=self._device,
                        half=self._use_half,
                    )
                busy_s = time.monotonic() - _t_infer
                from inference.monitoring.metrics import get_metrics
                get_metrics().record_gpu_inference(busy_s)
                req._result.put(("ok", result))
            except Exception as exc:
                req._result.put(("error", exc))

    def shutdown(self) -> None:
        """Signal the GPU worker to stop and wait for it to exit."""
        self._shutdown_event.set()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=10.0)

    # ── priority enqueue ──────────────────────────────────────────────────────

    def _enqueue(self, req: "_InferenceRequest | _BatchInferenceRequest") -> None:
        """
        Wrap request in a (priority, seq, req) tuple and push to the bounded
        PriorityQueue.  Raises RuntimeError immediately if the queue is full
        so callers can drop the frame rather than blocking the pipeline thread.
        """
        with self._seq_lock:
            seq = self._seq_counter
            self._seq_counter += 1
        try:
            self._request_queue.put_nowait((req.priority, seq, req))
        except queue.Full:
            from inference.metrics import metrics
            metrics.queue_overflows += 1
            raise RuntimeError(
                f"ModelPool GPU queue is full (maxsize={_GPU_QUEUE_MAXSIZE}) "
                "— inference request dropped to protect pipeline latency"
            )

    # ── public inference interface — single frame ─────────────────────────────

    def run_weapon(self, frame: np.ndarray, priority: int = PRIORITY_NORMAL) -> list:
        """Submit a weapon-model single-frame request and block for the result."""
        if self._weapon_model is None:
            raise RuntimeError("ModelPool: weapon model not loaded — call load() first")
        req = _InferenceRequest(model_type="weapon", frame=frame, priority=priority)
        self._enqueue(req)
        return req.wait()

    def run_phone(self, frame: np.ndarray, priority: int = PRIORITY_NORMAL) -> list:
        """Submit a phone-model single-frame request and block for the result."""
        if self._phone_model is None:
            raise RuntimeError("ModelPool: phone model not loaded — call load() first")
        req = _InferenceRequest(model_type="phone", frame=frame, priority=priority)
        self._enqueue(req)
        return req.wait()

    # ── public inference interface — batch ────────────────────────────────────

    def run_weapon_batch(
        self, frames: List[np.ndarray], priority: int = PRIORITY_NORMAL
    ) -> list:
        """
        Submit a weapon-model batch request and block for the result.

        Returns a list of ultralytics Results objects, one per input frame,
        produced by a single YOLO forward pass.
        """
        if self._weapon_model is None:
            raise RuntimeError("ModelPool: weapon model not loaded — call load() first")
        if not frames:
            return []
        req = _BatchInferenceRequest(model_type="weapon", frames=frames, priority=priority)
        self._enqueue(req)
        return req.wait()

    def run_phone_batch(
        self, frames: List[np.ndarray], priority: int = PRIORITY_NORMAL
    ) -> list:
        """
        Submit a phone-model batch request and block for the result.

        Returns a list of ultralytics Results objects, one per input frame,
        produced by a single YOLO forward pass.
        """
        if self._phone_model is None:
            raise RuntimeError("ModelPool: phone model not loaded — call load() first")
        if not frames:
            return []
        req = _BatchInferenceRequest(model_type="phone", frames=frames, priority=priority)
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

    @property
    def queue_full(self) -> bool:
        return self._request_queue.full()

    @property
    def use_half(self) -> bool:
        return self._use_half


# Process-wide singleton
_pool: ModelPool = ModelPool()


def get_model_pool() -> ModelPool:
    """Return the process-wide ModelPool singleton."""
    return _pool
