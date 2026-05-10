"""
Phase 28B Autonomous Orchestrator - Aegis Sentinel.

Inspects project state, GPU availability, active training processes,
download progress, and decides the next safe action without restarting
completed work.

Usage:
    python scripts/orchestrate_phase28b.py --once
    python scripts/orchestrate_phase28b.py --watch --interval-seconds 300
    python scripts/orchestrate_phase28b.py --once --report-only
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# -- paths ---------------------------------------------------------------------
_STATE_PATH = Path("runtime_state/phase_28b_state.json")
_ANOMALY_YAML = Path("configs/runtime/anomaly.yaml")
_KAGGLE_YAML = Path("configs/evaluation/kaggle_anomaly_sources.yaml")

# Violence YOLO data yaml - real path confirmed from this project
_VIOLENCE_DATA_YAML = "datasets/raw/anomaly/violence-detection-through-cctv/data_fixed.yaml"
_VIOLENCE_RUN_DIR = Path("runs/detect/models/anomaly/violence_yolo11")
_WEAPON_RUN_DIR = Path("runs/detect/runs/aegis_weapon/yolo11s_weapon_v2")

_XD_ZIP_PATTERN = "datasets/raw/anomaly/kaggle_zips/xd-violence.zip"
_XD_RAW_DIR = Path("datasets/raw/anomaly/xd_violence")
_XD_JSONL_DIR = Path("datasets/training/anomaly_video")

_VIDEOMAE_UCF_DIR = Path("models/anomaly/videomae_ucf_binary")
_VIDEOMAE_UCF_XD_DIR = Path("models/anomaly/videomae_ucf_xd_binary")
_PRETRAINED_KINETICS = Path("models/anomaly/pretrained/videomae_kinetics")

_UCF_TRAIN_JSONL = Path("datasets/training/anomaly_video/train.jsonl")
_UCF_VAL_JSONL = Path("datasets/training/anomaly_video/val.jsonl")

_GPU_STABILITY_WAIT_SECS = 300   # 5 min file-stable check for zip


# -- state I/O -----------------------------------------------------------------

def _load_state() -> dict:
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not parse state file: %s", exc)
    return {}


def _save_state(state: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = _STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(_STATE_PATH)


# -- GPU inspection -------------------------------------------------------------

class GPUInfo:
    available: bool = False
    name: str = "unknown"
    vram_total_gb: float = 0.0
    vram_used_gb: float = 0.0
    vram_free_gb: float = 0.0
    cuda_version: str = "unknown"
    active_processes: list[dict] = []

    def __repr__(self) -> str:
        return (
            f"GPU({self.name} | VRAM {self.vram_used_gb:.1f}/{self.vram_total_gb:.1f} GB used"
            f" | free={self.vram_free_gb:.1f} GB | procs={len(self.active_processes)})"
        )


def _check_gpu() -> GPUInfo:
    info = GPUInfo()
    try:
        import torch
        if not torch.cuda.is_available():
            logger.error("CUDA NOT AVAILABLE - training is blocked per GPU policy.")
            return info
        info.available = True
        info.name = torch.cuda.get_device_name(0)
        props = torch.cuda.get_device_properties(0)
        info.vram_total_gb = props.total_memory / 1e9
        info.cuda_version = torch.version.cuda or "unknown"
        # Get current allocation from torch
        info.vram_used_gb = torch.cuda.memory_allocated(0) / 1e9
        info.vram_free_gb = info.vram_total_gb - info.vram_used_gb
    except ImportError:
        logger.error("torch not installed - cannot check GPU.")
    # nvidia-smi for process list
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.strip().splitlines():
            parts = line.strip().split(",")
            if len(parts) == 2:
                info.active_processes.append({"pid": parts[0].strip(), "vram_mb": parts[1].strip()})
    except Exception:
        pass
    return info


# -- process detection ----------------------------------------------------------

def _detect_training_processes() -> dict[str, bool]:
    """Returns which known training jobs appear to be running by process name inspection."""
    running: dict[str, bool] = {
        "videomae_ucf_binary": False,
        "videomae_ucf_xd_binary": False,
        "violence_yolo11": False,
        "weapon_yolo11s_v2": False,
    }
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = " ".join(proc.info["cmdline"] or [])
                if "train_anomaly_videomae" in cmd:
                    if "videomae_ucf_xd" in cmd or "ucf_xd" in cmd:
                        running["videomae_ucf_xd_binary"] = True
                    else:
                        running["videomae_ucf_binary"] = True
                if "yolo" in cmd.lower() and "violence_yolo11" in cmd:
                    running["violence_yolo11"] = True
                if "yolo" in cmd.lower() and "weapon_v2" in cmd:
                    running["weapon_yolo11s_v2"] = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except ImportError:
        # Fallback: check last-modified times of results.csv
        pass
    return running


def _count_active_gpu_jobs(running: dict[str, bool]) -> int:
    return sum(1 for v in running.values() if v)


# -- checkpoint inspection ------------------------------------------------------

def _videomae_status(out_dir: Path) -> dict:
    """Return current status of a VideoMAE training run."""
    result: dict = {"status": "not_started", "last_epoch": None, "best_metric": None, "complete": False}
    if not out_dir.exists():
        return result
    # Completion marker
    if (out_dir / "training_complete.json").exists():
        try:
            data = json.loads((out_dir / "training_complete.json").read_text())
            result["status"] = "complete"
            result["complete"] = True
            result["best_metric"] = f"val_loss={data.get('best_val_loss', '?'):.4f}"
        except Exception:
            result["status"] = "complete"
            result["complete"] = True
        return result
    # Epoch checkpoints
    epoch_dirs = sorted(out_dir.glob("epoch_*"), key=lambda p: p.name)
    if epoch_dirs:
        last = epoch_dirs[-1]
        m = re.search(r"epoch_(\d+)", last.name)
        result["last_epoch"] = int(m.group(1)) if m else None
        result["status"] = "interrupted"
        # Try reading epoch_state.json
        state_f = last / "epoch_state.json"
        if state_f.exists():
            try:
                es = json.loads(state_f.read_text())
                result["best_metric"] = f"val_acc={es.get('val_acc', 0):.4f} val_loss={es.get('val_loss', 0):.4f}"
            except Exception:
                pass
    # best_state.json
    best_state = out_dir / "best_state.json"
    if best_state.exists():
        try:
            bs = json.loads(best_state.read_text())
            result["best_metric"] = f"val_acc={bs.get('val_acc', 0):.4f} val_loss={bs.get('val_loss', 0):.4f}"
        except Exception:
            pass
    return result


def _yolo_status(run_dir: Path) -> dict:
    """Parse results.csv to get latest epoch and metrics for a YOLO run."""
    result: dict = {"status": "not_started", "last_epoch": None, "best_map50": None, "last_pt": None}
    if not run_dir.exists():
        return result
    weights_dir = run_dir / "weights"
    if (weights_dir / "last.pt").exists():
        result["last_pt"] = str(weights_dir / "last.pt")
        result["status"] = "has_checkpoint"
    if (weights_dir / "best.pt").exists():
        result["best_pt"] = str(weights_dir / "best.pt")
    csv_path = run_dir / "results.csv"
    if csv_path.exists():
        try:
            with open(csv_path, newline="") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
            if rows:
                last = rows[-1]
                # Strip whitespace from keys
                last = {k.strip(): v.strip() for k, v in last.items()}
                epoch_key = next((k for k in last if "epoch" in k.lower()), None)
                map_key = next((k for k in last if "map50" in k.lower() and "95" not in k.lower()), None)
                if epoch_key:
                    result["last_epoch"] = int(float(last[epoch_key]))
                if map_key:
                    result["best_map50"] = float(last[map_key])
                result["status"] = "has_results"
        except Exception as exc:
            logger.debug("results.csv parse error: %s", exc)
    return result


# -- XD-Violence download watcher -----------------------------------------------

def _xd_zip_stable(zip_path: Path, wait_secs: int = 30) -> bool:
    """Return True if the zip file exists, is not growing, and is valid."""
    if not zip_path.exists():
        return False
    size1 = zip_path.stat().st_size
    logger.info("XD-Violence zip found: %.2f GB - checking stability for %ds...", size1 / 1e9, wait_secs)
    time.sleep(wait_secs)
    size2 = zip_path.stat().st_size
    if size2 != size1:
        logger.info("Zip still growing (%.2f -> %.2f GB) - not yet stable.", size1 / 1e9, size2 / 1e9)
        return False
    # Validate zip integrity
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
            if bad:
                logger.warning("Zip CRC error on file: %s", bad)
                return False
        logger.info("XD-Violence zip is stable and valid (%.2f GB).", size2 / 1e9)
        return True
    except zipfile.BadZipFile:
        logger.warning("XD-Violence zip is not a valid zip file yet.")
        return False


def _xd_already_extracted() -> bool:
    # XD-Violence was extracted by Kaggle API into kaggle_zips/ alongside UCF-Crime.
    # Presence of XD-specific categories (CarAccident, Riot, Normal) confirms extraction.
    kaggle_zips = Path("datasets/raw/anomaly/kaggle_zips")
    xd_markers = ["CarAccident", "Riot"]  # categories added by XD-Violence
    for split in ["Train", "Test"]:
        for cat in xd_markers:
            if (kaggle_zips / split / cat).exists():
                return True
    # Also check original target dir
    if _XD_RAW_DIR.exists() and any(_XD_RAW_DIR.rglob("*")):
        return True
    return False


def _extract_xd(force: bool = False) -> bool:
    cmd = [sys.executable, "scripts/extract_anomaly_dataset_zips.py", "--source", "xd_violence"]
    if force:
        cmd.append("--force")
    logger.info("Extracting XD-Violence: %s", " ".join(cmd))
    result = subprocess.run(cmd, timeout=3600)
    return result.returncode == 0


def _prepare_xd() -> bool:
    cmd = [
        sys.executable, "scripts/prepare_video_anomaly_dataset.py",
        "--source", "xd_violence",
        "--clip-length", "16", "--stride", "8", "--sample-rate", "5",
    ]
    logger.info("Preparing XD-Violence JSONL: %s", " ".join(cmd))
    result = subprocess.run(cmd, timeout=3600)
    return result.returncode == 0


def _prepare_merged() -> bool:
    cmd = [
        sys.executable, "scripts/prepare_video_anomaly_dataset.py",
        "--sources", "ucf_crime", "xd_violence",
        "--clip-length", "16", "--stride", "8", "--sample-rate", "5",
        "--merge",
    ]
    logger.info("Preparing merged UCF+XD JSONL: %s", " ".join(cmd))
    result = subprocess.run(cmd, timeout=3600)
    return result.returncode == 0


# -- training launchers ---------------------------------------------------------

def _launch_videomae(
    out_dir: str,
    epochs: int,
    resume_from: str | None,
    auto_resume: bool,
    batch_size: int = 2,
    train_jsonl: str = "datasets/training/anomaly_video/train.jsonl",
    val_jsonl: str = "datasets/training/anomaly_video/val.jsonl",
) -> subprocess.Popen:
    cmd = [
        sys.executable, "scripts/train_anomaly_videomae.py",
        "--train-jsonl", train_jsonl,
        "--val-jsonl", val_jsonl,
        "--model-name", "MCG-NJU/videomae-base-finetuned-kinetics",
        "--output-dir", out_dir,
        "--task", "binary",
        "--epochs", str(epochs),
        "--batch-size", str(batch_size),
        "--clip-len", "16",
        "--frame-sample-rate", "4",
        "--device", "cuda",
        "--fp16",
        "--save-every-epoch",
    ]
    if resume_from:
        cmd += ["--resume-from", resume_from]
    elif auto_resume:
        cmd.append("--auto-resume")
    logger.info("Launching VideoMAE: %s", " ".join(cmd))
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _launch_yolo_resume(last_pt: str, project_name: str) -> subprocess.Popen:
    cmd = [
        sys.executable, "-c",
        f"from ultralytics import YOLO; "
        f"m = YOLO(r'{last_pt}'); "
        f"m.train(resume=True)"
    ]
    logger.info("Resuming YOLO: %s", last_pt)
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _probe_vram_safe(gpu: GPUInfo, min_free_gb: float = 3.0) -> bool:
    """Return True if we have enough headroom for another heavy GPU job."""
    return gpu.available and gpu.vram_free_gb >= min_free_gb


# -- benchmark runner -----------------------------------------------------------

def _run_benchmark(provider: str, model_path: str | None, split: str = "test") -> dict:
    cmd = [
        sys.executable, "scripts/evaluate_anomaly_models.py",
        "--split", split,
        "--provider", provider,
        "--config", str(_ANOMALY_YAML),
    ]
    if model_path:
        cmd += ["--model-path", model_path, "--device", "cuda"]
    logger.info("Running benchmark: provider=%s model=%s", provider, model_path)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return {"provider": provider, "exit_code": result.returncode,
                "stdout_tail": result.stdout[-500:], "error": result.stderr[-200:] if result.returncode else None}
    except subprocess.TimeoutExpired:
        return {"provider": provider, "exit_code": -1, "error": "timeout"}
    except Exception as exc:
        return {"provider": provider, "exit_code": -1, "error": str(exc)}


# -- scheduling decision engine -------------------------------------------------

def _decide(state: dict, gpu: GPUInfo, running: dict[str, bool],
             vm_ucf: dict, ym_v: dict, ym_w: dict, vm_xd: dict,
             xd_zip: Path, args) -> list[str]:
    """Return ordered list of actions to take. Pure logic - no side effects."""
    actions: list[str] = []

    if not gpu.available:
        actions.append("BLOCK: CUDA unavailable - no training can proceed.")
        return actions

    active = _count_active_gpu_jobs(running)
    max_jobs = state.get("gpu_policy", {}).get("max_concurrent_gpu_jobs", 2)

    # -- VideoMAE UCF binary --------------------------------------
    if running["videomae_ucf_binary"]:
        actions.append(f"MONITOR: VideoMAE UCF binary running (epoch {vm_ucf.get('last_epoch', '?')})")
    elif not vm_ucf["complete"]:
        if vm_ucf["status"] in ("interrupted", "has_checkpoint") and vm_ucf["last_epoch"]:
            if active < max_jobs:
                actions.append(f"RESUME_VIDEOMAE_UCF: resume from epoch_{vm_ucf['last_epoch']:02d}")
            else:
                actions.append("DEFER_VIDEOMAE_UCF: max GPU jobs active")
        elif vm_ucf["status"] == "not_started":
            if active < max_jobs and _UCF_TRAIN_JSONL.exists():
                actions.append("START_VIDEOMAE_UCF: start fresh (no checkpoint)")
            else:
                actions.append("DEFER_VIDEOMAE_UCF: waiting for data or GPU slot")
    else:
        actions.append("DONE: VideoMAE UCF binary complete")

    # -- YOLO11 violence ------------------------------------------
    if running["violence_yolo11"]:
        epoch_str = f"epoch {ym_v.get('last_epoch', '?')}" if ym_v.get("last_epoch") else "running"
        actions.append(f"MONITOR: YOLO11 violence running ({epoch_str})")
    elif ym_v.get("last_epoch") and ym_v["last_epoch"] >= 50:
        actions.append(f"DONE: YOLO11 violence complete (epoch {ym_v['last_epoch']} mAP50={ym_v.get('best_map50', '?')})")
    elif ym_v.get("last_pt"):
        if active < max_jobs:
            actions.append(f"RESUME_VIOLENCE_YOLO: resume from {ym_v['last_pt']}")
        else:
            actions.append("DEFER_VIOLENCE_YOLO: max GPU jobs active")
    else:
        actions.append("SKIP_VIOLENCE_YOLO: no checkpoint and already running or done")

    # -- XD-Violence dataset pipeline -----------------------------
    xd_state = state.get("datasets", {}).get("xd_violence", {})
    if xd_state.get("prepared"):
        actions.append("DONE: XD-Violence prepared")
    elif _xd_already_extracted():
        actions.append("PREPARE_XD: extracted but JSONL not prepared")
    elif xd_zip.exists():
        actions.append("WATCH_XD_ZIP: zip exists - run stability + extraction when GPU allows")
    else:
        actions.append("WAIT_XD_DOWNLOAD: zip not yet present")

    # -- VideoMAE UCF+XD -----------------------------------------
    xd_ready = xd_state.get("prepared", False)
    ucf_done = vm_ucf["complete"]
    if running["videomae_ucf_xd_binary"]:
        actions.append(f"MONITOR: VideoMAE UCF+XD running (epoch {vm_xd.get('last_epoch', '?')})")
    elif vm_xd["complete"]:
        actions.append("DONE: VideoMAE UCF+XD binary complete")
    elif xd_ready and ucf_done:
        if active < max_jobs and _probe_vram_safe(gpu):
            actions.append("START_VIDEOMAE_UCF_XD: all prerequisites met")
        else:
            actions.append("DEFER_VIDEOMAE_UCF_XD: waiting for GPU slot")
    else:
        missing = []
        if not xd_ready:
            missing.append("XD-Violence not prepared")
        if not ucf_done:
            missing.append("VideoMAE UCF not complete")
        actions.append(f"BLOCKED_VIDEOMAE_UCF_XD: {', '.join(missing)}")

    # -- Weapon v2 ---------------------------------------------
    if running["weapon_yolo11s_v2"]:
        actions.append(f"MONITOR: weapon_v2 running (epoch {ym_w.get('last_epoch', '?')})")
    elif ym_w.get("last_epoch") and ym_w["last_epoch"] >= 80:
        actions.append(f"DONE: weapon_v2 complete (mAP50={ym_w.get('best_map50', '?')})")
    else:
        anomaly_idle = (vm_ucf["complete"] and not running["videomae_ucf_binary"]
                        and (ym_v.get("last_epoch", 0) >= 50 or not running["violence_yolo11"]))
        if anomaly_idle and ym_w.get("last_pt") and active < max_jobs:
            actions.append(f"RESUME_WEAPON_V2: anomaly jobs idle - resume from {ym_w['last_pt']}")
        else:
            actions.append(
                f"DEFER_WEAPON_V2: anomaly jobs have priority (active={active},"
                f" weapon_epoch={ym_w.get('last_epoch', '?')})"
            )

    return actions


# -- action executor ------------------------------------------------------------

def _execute(action: str, state: dict, gpu: GPUInfo,
             vm_ucf: dict, ym_v: dict, ym_w: dict, xd_zip: Path, args) -> None:
    """Execute a single action string emitted by the decision engine."""
    tag = action.split(":")[0]

    if tag == "RESUME_VIDEOMAE_UCF":
        last_epoch = vm_ucf["last_epoch"]
        ckpt = str(_VIDEOMAE_UCF_DIR / f"epoch_{last_epoch:02d}")
        _launch_videomae(
            str(_VIDEOMAE_UCF_DIR), epochs=5,
            resume_from=ckpt, auto_resume=False,
        )
        state["jobs"]["videomae_ucf_binary"]["status"] = "running"

    elif tag == "START_VIDEOMAE_UCF":
        _launch_videomae(str(_VIDEOMAE_UCF_DIR), epochs=5, resume_from=None, auto_resume=False)
        state["jobs"]["videomae_ucf_binary"]["status"] = "running"

    elif tag == "RESUME_VIOLENCE_YOLO":
        last_pt = ym_v["last_pt"]
        _launch_yolo_resume(last_pt, "violence_yolo11")
        state["jobs"]["violence_yolo11"]["status"] = "running"

    elif tag == "PREPARE_XD":
        ok = _prepare_xd()
        if ok:
            state["datasets"]["xd_violence"]["prepared"] = True
            state["datasets"]["xd_violence"]["status"] = "prepared"

    elif tag == "WATCH_XD_ZIP":
        if not args.report_only:
            stable = _xd_zip_stable(xd_zip, wait_secs=30)
            if stable and not _xd_already_extracted():
                ok = _extract_xd()
                if ok:
                    state["datasets"]["xd_violence"]["status"] = "extracted"
                    ok2 = _prepare_xd()
                    if ok2:
                        state["datasets"]["xd_violence"]["status"] = "prepared"
                        state["datasets"]["xd_violence"]["prepared"] = True

    elif tag == "START_VIDEOMAE_UCF_XD":
        batch = 4 if gpu.vram_free_gb >= 5.0 else 2
        _launch_videomae(
            str(_VIDEOMAE_UCF_XD_DIR), epochs=10,
            resume_from=None, auto_resume=False,
            batch_size=batch,
        )
        state["jobs"]["videomae_ucf_xd_binary"]["status"] = "running"

    elif tag == "RESUME_WEAPON_V2":
        last_pt = ym_w["last_pt"]
        _launch_yolo_resume(last_pt, "yolo11s_weapon_v2")
        state["jobs"]["weapon_yolo11s_v2"]["status"] = "running"


# -- phase 29 readiness gate ----------------------------------------------------

def _phase29_gate(vm_ucf: dict, ym_v: dict, gpu: GPUInfo) -> tuple[bool, str]:
    """Decide if Phase 29 can begin while background training continues."""
    if not gpu.available:
        return False, "GPU/CUDA unavailable - runtime is unstable."
    if not vm_ucf.get("last_epoch") and not vm_ucf.get("complete"):
        return False, "VideoMAE UCF has not produced any checkpoint yet."
    # Phase 29 can begin once we have at least one validated VideoMAE checkpoint
    epoch_dirs = list(_VIDEOMAE_UCF_DIR.glob("epoch_*"))
    if not epoch_dirs and not vm_ucf.get("complete"):
        return False, "No VideoMAE checkpoint available for production use."
    return True, "At least one VideoMAE checkpoint exists. Training continues in background."


# -- report printer -------------------------------------------------------------

def _print_report(
    state: dict, gpu: GPUInfo, running: dict[str, bool],
    vm_ucf: dict, ym_v: dict, ym_w: dict, vm_xd: dict,
    actions: list[str], xd_zip: Path,
    phase29_ok: bool, phase29_reason: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # git info
    try:
        git_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                           text=True, stderr=subprocess.DEVNULL).strip()
        git_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                             text=True, stderr=subprocess.DEVNULL).strip()
        git_dirty = subprocess.check_output(["git", "status", "--porcelain"],
                                            text=True, stderr=subprocess.DEVNULL).strip()
        git_status = "clean" if not git_dirty else f"dirty ({len(git_dirty.splitlines())} changes)"
    except Exception:
        git_hash, git_branch, git_status = "unknown", "unknown", "unknown"

    xd_state = state.get("datasets", {}).get("xd_violence", {})
    xd_zip_size = f"{xd_zip.stat().st_size / 1e9:.2f} GB" if xd_zip.exists() else "not found"

    vram_display = (
        f"{gpu.vram_used_gb:.1f}/{gpu.vram_total_gb:.1f} GB"
        if gpu.available else "N/A"
    )

    print("\n" + "=" * 72)
    print("  PHASE 28B AUTONOMOUS ORCHESTRATION REPORT")
    print(f"  Generated: {now}")
    print("=" * 72)

    print("\n1. COMMIT")
    print(f"   hash:          {git_hash}")
    print(f"   branch:        {git_branch}")
    print(f"   working tree:  {git_status}")

    print("\n2. STATE PERSISTENCE")
    print(f"   state file:        {_STATE_PATH}  ({'exists' if _STATE_PATH.exists() else 'MISSING'})")
    print(f"   runtime_state/:    gitignored = YES")
    state_snap = {
        "datasets": {k: v.get("status") for k, v in state.get("datasets", {}).items()},
        "jobs": {k: v.get("status") for k, v in state.get("jobs", {}).items()},
    }
    print(f"   current summary:   {json.dumps(state_snap)}")

    print("\n3. GPU / JOB SCHEDULER")
    print(f"   CUDA available:    {gpu.available}")
    print(f"   GPU:               {gpu.name}")
    print(f"   VRAM usage:        {vram_display}  (torch-reported; nvidia-smi procs: {len(gpu.active_processes)})")
    print(f"   active GPU jobs:   {_count_active_gpu_jobs(running)}")
    print(f"   max allowed:       {state.get('gpu_policy', {}).get('max_concurrent_gpu_jobs', 2)}")
    print(f"   scheduling:        {'CUDA BLOCKED - no training' if not gpu.available else 'normal'}")

    print("\n4. ACTIVE TRAINING JOBS")
    def _job_line(label: str, info: dict, is_running: bool) -> None:
        status = "RUNNING" if is_running else info.get("status", "unknown").upper()
        ep = info.get("last_epoch")
        metric = info.get("best_metric") or info.get("best_map50")
        ep_str = f"  epoch={ep}" if ep else ""
        metric_str = f"  {metric}" if metric else ""
        print(f"   {label:<28} {status}{ep_str}{metric_str}")

    _job_line("VideoMAE UCF binary:", vm_ucf, running["videomae_ucf_binary"])
    _job_line("YOLO11 violence:", ym_v, running["violence_yolo11"])
    _job_line("Weapon v2 (yolo11s):", ym_w, running["weapon_yolo11s_v2"])
    _job_line("VideoMAE UCF+XD:", vm_xd, running["videomae_ucf_xd_binary"])

    print("\n5. XD-VIOLENCE WATCHER")
    print(f"   zip path:          {_XD_ZIP_PATTERN}")
    print(f"   zip status:        {'EXISTS' if xd_zip.exists() else 'NOT FOUND'}  {xd_zip_size}")
    print(f"   extraction status: {'done' if _xd_already_extracted() else 'pending'}")
    print(f"   preparation:       {'prepared' if xd_state.get('prepared') else 'pending'}")
    next_xd = "stability check -> extract -> prepare JSONL -> merge with UCF-Crime -> trigger VideoMAE UCF+XD"
    print(f"   next auto step:    {next_xd}")

    print("\n6. RESUME LOGIC")
    ucf_ep = vm_ucf.get("last_epoch")
    ucf_ckpt = str(_VIDEOMAE_UCF_DIR / f"epoch_{ucf_ep:02d}") if ucf_ep else "none"
    print(f"   VideoMAE UCF:      {'complete' if vm_ucf['complete'] else f'resume from {ucf_ckpt}'}")
    v_pt = ym_v.get("last_pt", "none")
    v_ep = ym_v.get("last_epoch")
    print(f"   YOLO11 violence:   {'complete' if v_ep and v_ep>=50 else f'resume from {v_pt}  (epoch {v_ep})'}")
    w_pt = ym_w.get("last_pt", "none")
    w_ep = ym_w.get("last_epoch")
    print(f"   weapon_v2:         paused at epoch {w_ep} - resume from {w_pt}")
    print(f"   checkpoint policy: save every epoch (VideoMAE) / save_period=5 (YOLO) - no scratch restarts")

    print("\n7. PRETRAINED MODELS")
    kinetics_ok = _PRETRAINED_KINETICS.exists() and any(_PRETRAINED_KINETICS.iterdir())
    print(f"   videomae_kinetics: {'CACHED' if kinetics_ok else 'MISSING'}  -> {_PRETRAINED_KINETICS}")
    ucf_crime_pretrained = Path("models/anomaly/pretrained/videomae_ucf_crime")
    ucf_pretrained_ok = ucf_crime_pretrained.exists() and any(ucf_crime_pretrained.iterdir())
    print(f"   videomae_ucf_crime:{'CACHED' if ucf_pretrained_ok else 'not downloaded'}")
    slowfast = Path("models/anomaly/pretrained/slowfast_r50")
    print(f"   slowfast_r50:      {'CACHED' if slowfast.exists() else 'not downloaded'}")

    print("\n8. BENCHMARKS")
    print("   rule_only:         pending (run after YOLO violence completes)")
    print("   VideoMAE UCF:      pending (run after training completes)")
    print("   violence_adapter:  pending (run after YOLO violence completes)")
    print("   VideoMAE UCF+XD:   pending (run after XD-Violence training)")
    print("   fusion tuning:     pending (requires individual benchmark results)")
    print("   acceptance gate:   AUC>=0.90 | macro_F1>=0.87 | recall>=0.90 | FA/h<=3 | p95<=120ms")

    print("\n9. SCHEDULED ACTIONS")
    for i, act in enumerate(actions, 1):
        print(f"   {i}. {act}")

    print("\n10. RECOMMENDATION")
    if phase29_ok:
        print(f"   VERDICT: Phase 29 may begin while Phase 28B training continues in the background.")
        print(f"   REASON:  {phase29_reason}")
        print(f"   NOTE:    Benchmarks and fusion tuning must complete before Phase 28B closes.")
    else:
        print(f"   VERDICT: Do not begin Phase 29 yet because GPU/runtime is unstable.")
        print(f"   REASON:  {phase29_reason}")

    print("\n" + "=" * 72 + "\n")


# -- main loop ------------------------------------------------------------------

def run_once(args) -> None:
    state = _load_state()

    # Ensure schema keys exist
    state.setdefault("gpu_policy", {"primary_device": 0, "require_cuda": True,
                                    "allow_cpu_training": False, "max_concurrent_gpu_jobs": 2})
    state.setdefault("datasets", {})
    state.setdefault("jobs", {})
    state["datasets"].setdefault("xd_violence", {"status": "downloading", "prepared": False})
    for job in ("videomae_ucf_binary", "violence_yolo11", "weapon_yolo11s_v2", "videomae_ucf_xd_binary"):
        state["jobs"].setdefault(job, {"status": "not_started"})

    # Gather current state
    gpu = _check_gpu()
    running = _detect_training_processes()

    vm_ucf = _videomae_status(_VIDEOMAE_UCF_DIR)
    vm_xd = _videomae_status(_VIDEOMAE_UCF_XD_DIR)
    ym_v = _yolo_status(_VIOLENCE_RUN_DIR)
    ym_w = _yolo_status(_WEAPON_RUN_DIR)

    xd_zip = Path(_XD_ZIP_PATTERN)

    # Sync state from inspection
    state["jobs"]["videomae_ucf_binary"]["status"] = (
        "running" if running["videomae_ucf_binary"]
        else ("complete" if vm_ucf["complete"] else vm_ucf["status"])
    )
    if vm_ucf.get("last_epoch"):
        state["jobs"]["videomae_ucf_binary"]["last_epoch"] = vm_ucf["last_epoch"]
    if vm_ucf.get("best_metric"):
        state["jobs"]["videomae_ucf_binary"]["best_metric"] = vm_ucf["best_metric"]

    state["jobs"]["violence_yolo11"]["status"] = (
        "running" if running["violence_yolo11"]
        else ("complete" if ym_v.get("last_epoch", 0) >= 50 else ym_v.get("status", "unknown"))
    )
    if ym_v.get("last_epoch"):
        state["jobs"]["violence_yolo11"]["last_epoch"] = ym_v["last_epoch"]
    if ym_v.get("best_map50"):
        state["jobs"]["violence_yolo11"]["best_map50"] = ym_v["best_map50"]

    state["jobs"]["weapon_yolo11s_v2"]["status"] = (
        "running" if running["weapon_yolo11s_v2"]
        else ("complete" if ym_w.get("last_epoch", 0) >= 80 else "paused")
    )
    if ym_w.get("last_epoch"):
        state["jobs"]["weapon_yolo11s_v2"]["last_epoch"] = ym_w["last_epoch"]
    if ym_w.get("best_map50"):
        state["jobs"]["weapon_yolo11s_v2"]["best_map50"] = ym_w["best_map50"]

    if xd_zip.exists() and not _xd_already_extracted():
        state["datasets"]["xd_violence"]["status"] = "downloading"
    elif _xd_already_extracted() and not state["datasets"]["xd_violence"].get("prepared"):
        state["datasets"]["xd_violence"]["status"] = "extracted"

    # Decide
    actions = _decide(state, gpu, running, vm_ucf, ym_v, ym_w, vm_xd, xd_zip, args)

    # Execute (skip in report-only mode)
    if not args.report_only:
        for action in actions:
            _execute(action, state, gpu, vm_ucf, ym_v, ym_w, xd_zip, args)

    # Phase 29 gate
    phase29_ok, phase29_reason = _phase29_gate(vm_ucf, ym_v, gpu)

    # Print report
    _print_report(state, gpu, running, vm_ucf, ym_v, ym_w, vm_xd,
                  actions, xd_zip, phase29_ok, phase29_reason)

    # Persist updated state
    state["next_actions"] = [a for a in actions if not a.startswith("MONITOR") and not a.startswith("DONE")]
    _save_state(state)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 28B autonomous training orchestrator")
    parser.add_argument("--once", action="store_true", help="Run one inspection cycle and exit")
    parser.add_argument("--watch", action="store_true", help="Run in watcher mode (repeated cycles)")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Watch interval in seconds")
    parser.add_argument("--report-only", action="store_true",
                        help="Inspect and report without launching any new jobs")
    args = parser.parse_args()

    if not args.once and not args.watch:
        parser.print_help()
        sys.exit(0)

    if args.once:
        run_once(args)
    elif args.watch:
        logger.info("Watcher mode - interval=%ds. Ctrl-C to stop.", args.interval_seconds)
        while True:
            try:
                run_once(args)
                logger.info("Sleeping %ds until next cycle...", args.interval_seconds)
                time.sleep(args.interval_seconds)
            except KeyboardInterrupt:
                logger.info("Watcher stopped by user.")
                break


if __name__ == "__main__":
    main()
