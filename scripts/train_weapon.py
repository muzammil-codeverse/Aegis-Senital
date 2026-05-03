import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import json
import time
import shutil
import argparse

import torch
from ultralytics import YOLO

from utils.data_check import validate_splits, count_images
from configs.train_config import TRAIN_CONFIG, MIN_TRAIN_IMAGES

_DATASET_DEFAULT = "/content/datasets/weapon"
_DATA_CFG_DEFAULT = os.path.join(ROOT, "configs", "weapon.yaml")
_OUTPUT_DEFAULT   = os.path.join(ROOT, "models")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sentinel AI — Weapon Detection Training",
        add_help=True,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--data",
        required=False,
        default=_DATA_CFG_DEFAULT,
        help="Path to YOLO dataset YAML (default: configs/weapon.yaml inside repo root)",
    )
    parser.add_argument(
        "--label-dir",
        default=_DATASET_DEFAULT,
        dest="label_dir",
        help="Dataset root; must contain train/valid/test splits (default: %(default)s)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=TRAIN_CONFIG["epochs"],
        help="Training epochs (default: %(default)s)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=TRAIN_CONFIG["imgsz"],
        help="Input image size in pixels (default: %(default)s)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=TRAIN_CONFIG["batch"],
        help="Batch size (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=_OUTPUT_DEFAULT,
        help="Base output directory; a timestamped run folder is created inside (default: %(default)s)",
    )
    return parser


def main(args: argparse.Namespace) -> None:
    torch.manual_seed(42)

    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(args.output, run_id)          # e.g. models/20240503_142536
    os.makedirs(run_dir, exist_ok=True)

    print("=" * 60)
    print("  Sentinel AI — Weapon Detection Training")
    print("=" * 60)
    print(f"  run_id:   {run_id}")
    print(f"  root:     {ROOT}")
    print(f"  data:     {args.data}")
    print(f"  dataset:  {args.label_dir}")
    print(f"  epochs:   {args.epochs}")
    print(f"  imgsz:    {args.imgsz}")
    print(f"  batch:    {args.batch}")
    print(f"  device:   {TRAIN_CONFIG['device']}")
    print(f"  output:   {run_dir}/weapon")
    print("=" * 60)

    # ── GATE 1: Label validation ──────────────────────────────────────────
    print("\n[GATE 1] Dataset label validation ...")
    try:
        validate_splits(
            args.label_dir,
            splits=("train", "valid", "test"),
        )
    except SystemExit:
        raise RuntimeError("Dataset validation failed. Training aborted.")
    print("[GATE 1] PASSED\n")

    # ── GATE 2: Minimum training image count ─────────────────────────────
    train_img_dir = os.path.join(args.label_dir, "train", "images")
    n_train = count_images(train_img_dir)
    print(f"[GATE 2] Training images: {n_train}  (minimum: {MIN_TRAIN_IMAGES})")
    if n_train < MIN_TRAIN_IMAGES:
        raise ValueError(
            f"Dataset too small for production training — "
            f"{n_train} images found in '{train_img_dir}' "
            f"(minimum required: {MIN_TRAIN_IMAGES})"
        )
    print("[GATE 2] PASSED\n")

    # ── Save config snapshot ──────────────────────────────────────────────
    if os.path.isfile(args.data):
        shutil.copy2(args.data, os.path.join(run_dir, "dataset_config.yaml"))

    metadata = {
        "dataset_path": args.label_dir,
        "epochs":       args.epochs,
        "batch":        args.batch,
        "imgsz":        args.imgsz,
        "train_images": n_train,
        "timestamp":    run_id,
        "device":       TRAIN_CONFIG["device"],
        "seed":         42,
        "save_period":  TRAIN_CONFIG["save_period"],
    }
    with open(os.path.join(run_dir, "metadata.json"), "w") as fh:
        json.dump(metadata, fh, indent=2)
    print(f"[META] metadata.json → {run_dir}/metadata.json")

    # ── Train ─────────────────────────────────────────────────────────────
    device = None if TRAIN_CONFIG["device"] == "auto" else TRAIN_CONFIG["device"]

    model = YOLO("yolov8n.pt")
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        save_period=TRAIN_CONFIG["save_period"],
        project=run_dir,
        name="weapon",
        exist_ok=True,
        verbose=True,
        seed=42,
    )

    # ── Report ────────────────────────────────────────────────────────────
    best_pt = os.path.join(run_dir, "weapon", "weights", "best.pt")
    last_pt = os.path.join(run_dir, "weapon", "weights", "last.pt")

    print("\n" + "=" * 60)
    print("  Training Complete")
    print("=" * 60)
    print(f"  run_id:    {run_id}")
    print(f"  best.pt:   {best_pt}")
    print(f"  last.pt:   {last_pt}")
    print(f"  metadata:  {run_dir}/metadata.json")
    print("=" * 60)


if __name__ == "__main__":
    _parser = build_parser()
    _args = _parser.parse_args()
    main(_args)
