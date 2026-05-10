"""
Backup YOLO training checkpoints periodically.

Reads results.csv to determine current epoch and copies last.pt to
weights/epoch_backup_<epoch>.pt to guard against training interruptions.

Usage:
    python scripts/backup_yolo_checkpoints.py --run-dir runs/detect/models/anomaly/violence_yolo11
    python scripts/backup_yolo_checkpoints.py --run-dir runs/detect/runs/aegis_weapon/yolo11s_weapon_v2
    python scripts/backup_yolo_checkpoints.py --watch --interval-seconds 300 \
        --run-dirs runs/detect/models/anomaly/violence_yolo11 runs/detect/runs/aegis_weapon/yolo11s_weapon_v2
"""
from __future__ import annotations

import argparse
import csv
import logging
import shutil
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def _current_epoch(run_dir: Path) -> int | None:
    csv_path = run_dir / "results.csv"
    if not csv_path.exists():
        return None
    try:
        with open(csv_path, newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        if not rows:
            return None
        last = {k.strip(): v.strip() for k, v in rows[-1].items()}
        epoch_key = next((k for k in last if "epoch" in k.lower()), None)
        return int(float(last[epoch_key])) if epoch_key else None
    except Exception as exc:
        logger.debug("results.csv parse error for %s: %s", run_dir, exc)
        return None


def _backup_once(run_dir: Path, every_n: int = 5) -> None:
    weights_dir = run_dir / "weights"
    last_pt = weights_dir / "last.pt"
    if not last_pt.exists():
        logger.warning("[%s] No last.pt found — skipping backup.", run_dir.name)
        return

    epoch = _current_epoch(run_dir)
    if epoch is None:
        logger.info("[%s] Could not determine epoch from results.csv — skipping backup.", run_dir.name)
        return

    if epoch % every_n != 0:
        logger.debug("[%s] Epoch %d not a backup epoch (every %d).", run_dir.name, epoch, every_n)
        return

    backup_path = weights_dir / f"epoch_backup_{epoch:03d}.pt"
    if backup_path.exists():
        logger.info("[%s] Backup already exists: %s", run_dir.name, backup_path.name)
        return

    shutil.copy2(str(last_pt), str(backup_path))
    logger.info("[%s] Epoch %d backup saved: %s", run_dir.name, epoch, backup_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Periodic YOLO checkpoint backup")
    parser.add_argument("--run-dir", help="Single training run directory")
    parser.add_argument("--run-dirs", nargs="+", help="Multiple training run directories")
    parser.add_argument("--every-n-epochs", type=int, default=5, help="Backup every N epochs (default 5)")
    parser.add_argument("--watch", action="store_true", help="Watch continuously")
    parser.add_argument("--interval-seconds", type=int, default=300, help="Watch interval in seconds")
    args = parser.parse_args()

    dirs: list[Path] = []
    if args.run_dir:
        dirs.append(Path(args.run_dir))
    if args.run_dirs:
        dirs.extend(Path(d) for d in args.run_dirs)

    if not dirs:
        parser.print_help()
        sys.exit(0)

    valid_dirs = [d for d in dirs if d.exists()]
    if not valid_dirs:
        logger.warning("None of the specified run directories exist yet. Will check again when watching.")

    def run_all() -> None:
        for d in dirs:
            if d.exists():
                _backup_once(d, every_n=args.every_n_epochs)
            else:
                logger.debug("Run dir not yet present: %s", d)

    if args.watch:
        logger.info("Watching %d run dirs every %ds.", len(dirs), args.interval_seconds)
        while True:
            try:
                run_all()
                time.sleep(args.interval_seconds)
            except KeyboardInterrupt:
                logger.info("Backup watcher stopped.")
                break
    else:
        run_all()


if __name__ == "__main__":
    main()
