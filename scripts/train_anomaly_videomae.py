"""
Fine-tune VideoMAE for anomaly detection using Phase 28 JSONL datasets.

Supports:
  - binary mode: normal vs. anomaly
  - multiclass mode: normal/violence/loitering/theft/etc.

Usage:
    python scripts/train_anomaly_videomae.py \
        --train-jsonl datasets/training/anomaly_video/train.jsonl \
        --val-jsonl datasets/training/anomaly_video/val.jsonl \
        --model-name MCG-NJU/videomae-base-finetuned-kinetics \
        --output-dir models/anomaly/videomae_ucf_xd_binary \
        --task binary \
        --epochs 5 \
        --batch-size 2 \
        --clip-len 16 \
        --frame-sample-rate 4 \
        --device cuda \
        --fp16 \
        --save-every-epoch

GPU mandatory: script exits if CUDA unavailable.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

BINARY_LABEL_MAP = {"normal": 0}  # everything else → 1 (anomaly)

MULTICLASS_LABELS = [
    "normal", "violence", "shooting", "explosion", "theft",
    "traffic_accident", "vandalism", "arrest", "generic_anomaly",
]


def _check_gpu(device: str) -> None:
    try:
        import torch
        if device.startswith("cuda") and not torch.cuda.is_available():
            logger.error(
                "CUDA NOT AVAILABLE. torch.cuda.is_available() = False.\n"
                "This script requires GPU. Fix PyTorch CUDA before running training.\n"
                "Install: pip install torch --index-url https://download.pytorch.org/whl/cu124"
            )
            sys.exit(1)
        if torch.cuda.is_available():
            logger.info(
                "GPU: %s | VRAM: %.1f GB | CUDA: %s",
                torch.cuda.get_device_name(0),
                torch.cuda.get_device_properties(0).total_memory / 1e9,
                torch.version.cuda,
            )
    except ImportError:
        logger.error("torch not installed.")
        sys.exit(1)


def _load_jsonl(path: str) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _build_label_map(records: list[dict], task: str) -> dict[str, int]:
    if task == "binary":
        return {r["label"]: (0 if r["label"] == "normal" else 1) for r in records}
    labels = sorted({r["label"] for r in records})
    return {l: i for i, l in enumerate(labels)}


class AnomalyClipDataset:
    """
    Minimal clip dataset that reads JSONL records and decodes video clips.

    Falls back to random tensors when the video file does not exist
    (useful for pipeline testing before datasets are available).
    """

    def __init__(
        self,
        records: list[dict],
        label_map: dict[str, int],
        clip_len: int = 16,
        frame_sample_rate: int = 4,
        image_size: int = 224,
        task: str = "binary",
    ) -> None:
        self.records = records
        self.label_map = label_map
        self.clip_len = clip_len
        self.frame_sample_rate = frame_sample_rate
        self.image_size = image_size
        self.task = task

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int):
        import torch
        import numpy as np
        rec = self.records[idx]
        label_str = rec.get("label", "normal")
        label_id = self.label_map.get(label_str, 1 if label_str != "normal" else 0)
        label = torch.tensor(label_id, dtype=torch.long)

        video_path = rec.get("video_path", "")
        start_sec = float(rec.get("start_sec", 0.0))
        end_sec = float(rec.get("end_sec", start_sec + 5.0))

        frames = self._decode_clip(video_path, start_sec, end_sec)
        return {"pixel_values": frames, "labels": label}

    def _decode_clip(self, video_path: str, start_sec: float, end_sec: float):
        import torch
        import numpy as np

        if not os.path.exists(video_path):
            # Fallback: random tensor for pipeline testing
            return torch.randn(self.clip_len, 3, self.image_size, self.image_size)

        try:
            import decord
            decord.bridge.set_bridge("torch")
            vr = decord.VideoReader(video_path, width=self.image_size, height=self.image_size)
            fps = vr.get_avg_fps()
            start_frame = max(0, int(start_sec * fps))
            end_frame = min(len(vr), int(end_sec * fps))
            total = end_frame - start_frame
            if total <= 0:
                total = self.clip_len * self.frame_sample_rate
                end_frame = start_frame + total
            step = max(1, total // self.clip_len)
            indices = list(range(start_frame, end_frame, step * self.frame_sample_rate))[: self.clip_len]
            if len(indices) < self.clip_len:
                indices += [indices[-1]] * (self.clip_len - len(indices))
            frames = vr.get_batch(indices[:self.clip_len])  # [T, H, W, C]
            frames = frames.float() / 255.0
            # Normalize ImageNet
            mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 1, 1, 3)
            std = torch.tensor([0.229, 0.224, 0.225]).view(1, 1, 1, 3)
            frames = (frames - mean) / std
            frames = frames.permute(0, 3, 1, 2)  # [T, C, H, W]
            return frames
        except Exception as exc:
            logger.warning("Clip decode failed for %s: %s — using random", video_path, exc)
            return torch.randn(self.clip_len, 3, self.image_size, self.image_size)


def _collate(batch: list[dict]):
    import torch
    pixel_values = torch.stack([b["pixel_values"] for b in batch])  # [B, T, C, H, W]
    labels = torch.stack([b["labels"] for b in batch])
    return {"pixel_values": pixel_values, "labels": labels}


def train(args) -> None:
    import torch
    from torch.utils.data import DataLoader
    from torch.cuda.amp import GradScaler, autocast

    _check_gpu(args.device)

    logger.info("Loading train JSONL: %s", args.train_jsonl)
    train_records = _load_jsonl(args.train_jsonl)
    val_records = _load_jsonl(args.val_jsonl)
    logger.info("Train: %d clips | Val: %d clips", len(train_records), len(val_records))

    label_map = _build_label_map(train_records + val_records, args.task)
    num_labels = len(set(label_map.values()))
    logger.info("Task: %s | Labels (%d): %s", args.task, num_labels, label_map)

    # Load model
    logger.info("Loading model: %s", args.model_name)
    try:
        from transformers import VideoMAEForVideoClassification, VideoMAEConfig

        local_model_path = Path("models/anomaly/pretrained") / args.model_name.split("/")[-1].lower().replace("-", "_")
        model_path = str(local_model_path) if local_model_path.exists() else args.model_name

        model = VideoMAEForVideoClassification.from_pretrained(
            model_path,
            num_labels=num_labels,
            ignore_mismatched_sizes=True,
        )
    except Exception as exc:
        logger.error("Failed to load model '%s': %s", args.model_name, exc)
        logger.error("Download it first: python scripts/download_pretrained_anomaly_models.py --models videomae_kinetics")
        sys.exit(1)

    model = model.to(args.device)
    model.train()

    train_ds = AnomalyClipDataset(
        train_records, label_map, clip_len=args.clip_len,
        frame_sample_rate=args.frame_sample_rate, task=args.task
    )
    val_ds = AnomalyClipDataset(
        val_records, label_map, clip_len=args.clip_len,
        frame_sample_rate=args.frame_sample_rate, task=args.task
    )

    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        num_workers=2, collate_fn=_collate, pin_memory=True,
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch_size, shuffle=False,
        num_workers=2, collate_fn=_collate, pin_memory=True,
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    scaler = GradScaler(enabled=args.fp16)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Training — epochs=%d batch=%d fp16=%s device=%s clips=%d",
        args.epochs, args.batch_size, args.fp16, args.device, len(train_records),
    )

    best_val_loss = float("inf")
    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        t0 = time.time()
        for step, batch in enumerate(train_loader):
            pixel_values = batch["pixel_values"].to(args.device)
            labels = batch["labels"].to(args.device)
            optimizer.zero_grad()
            with autocast(enabled=args.fp16):
                outputs = model(pixel_values=pixel_values, labels=labels)
                loss = outputs.loss
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            epoch_loss += loss.item()
            if step % 20 == 0:
                logger.info(
                    "Epoch %d/%d | Step %d/%d | loss=%.4f",
                    epoch, args.epochs, step, len(train_loader), loss.item(),
                )

        avg_train_loss = epoch_loss / max(len(train_loader), 1)
        epoch_sec = time.time() - t0
        logger.info("Epoch %d done | train_loss=%.4f | %.1fs", epoch, avg_train_loss, epoch_sec)

        # Validation
        model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        with torch.no_grad():
            for batch in val_loader:
                pixel_values = batch["pixel_values"].to(args.device)
                labels = batch["labels"].to(args.device)
                with autocast(enabled=args.fp16):
                    outputs = model(pixel_values=pixel_values, labels=labels)
                val_loss += outputs.loss.item()
                preds = outputs.logits.argmax(dim=-1)
                correct += (preds == labels).sum().item()
                total += len(labels)
        avg_val_loss = val_loss / max(len(val_loader), 1)
        val_acc = correct / max(total, 1)
        logger.info("Epoch %d | val_loss=%.4f | val_acc=%.4f", epoch, avg_val_loss, val_acc)

        if args.save_every_epoch or avg_val_loss < best_val_loss:
            ckpt_path = out_dir / f"epoch_{epoch:02d}"
            model.save_pretrained(str(ckpt_path))
            logger.info("Checkpoint saved: %s", ckpt_path)
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                best_path = out_dir / "best"
                model.save_pretrained(str(best_path))
                logger.info("Best model updated: %s (val_loss=%.4f)", best_path, best_val_loss)

    # Save final
    final_path = out_dir / "final"
    model.save_pretrained(str(final_path))
    logger.info("Training complete. Final model: %s", final_path)

    # Save label map
    with open(out_dir / "label_map.json", "w") as fh:
        json.dump(label_map, fh, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune VideoMAE for anomaly detection")
    parser.add_argument("--train-jsonl", required=True)
    parser.add_argument("--val-jsonl", required=True)
    parser.add_argument("--model-name", default="MCG-NJU/videomae-base-finetuned-kinetics")
    parser.add_argument("--output-dir", default="models/anomaly/videomae_ucf_xd_binary")
    parser.add_argument("--task", default="binary", choices=["binary", "multiclass"])
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--clip-len", type=int, default=16)
    parser.add_argument("--frame-sample-rate", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--save-every-epoch", action="store_true")
    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
