import os
import sys
from pathlib import Path

_IMAGE_EXTS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}
)


def check_labels(label_dir: str) -> bool:
    """
    Validate YOLO-format label files in label_dir.

    Checks:
      - Directory exists and contains at least one .txt file
      - Each .txt file is non-empty
      - Every annotation line has exactly 5 whitespace-separated values
      - All values are parseable as floats

    Returns True on success; exits with code 1 on any failure.
    """
    label_path = Path(label_dir)
    if not label_path.exists():
        print(f"[ERROR] Label directory not found: {label_dir}")
        sys.exit(1)

    txt_files = list(label_path.rglob("*.txt"))
    if not txt_files:
        print(f"[ERROR] No .txt label files found in: {label_dir}")
        sys.exit(1)

    errors: list[str] = []

    for fpath in txt_files:
        if fpath.stat().st_size == 0:
            errors.append(f"[EMPTY]   {fpath}")
            continue

        with open(fpath, "r") as f:
            lines = f.readlines()

        for lineno, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 5:
                errors.append(
                    f"[CORRUPT] {fpath}:{lineno} — expected 5 values, "
                    f"got {len(parts)}: {line!r}"
                )
                continue
            for val in parts:
                try:
                    float(val)
                except ValueError:
                    errors.append(
                        f"[CORRUPT] {fpath}:{lineno} — non-numeric value "
                        f"{val!r}: {line!r}"
                    )
                    break

    if errors:
        print(f"\n[FAIL] {len(errors)} issue(s) found in {label_dir}:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    print(f"[OK] {len(txt_files)} label file(s) validated in {label_dir}")
    return True


def validate_splits(
    dataset_root: str,
    splits: tuple[str, ...] = ("train", "valid", "test"),
) -> bool:
    """
    Validate label files for all splits in dataset_root.

    Supports two layouts and auto-detects which one is present:
      Roboflow: {root}/{split}/labels/   (e.g. train/labels, valid/labels)
      YOLO:     {root}/labels/{split}/   (e.g. labels/train, labels/val)

    Skips splits whose label directory does not exist.
    Raises SystemExit(1) if no splits are found at all, or if any label
    file fails validation.
    """
    root = Path(dataset_root)

    # Auto-detect layout by probing the first candidate split directory
    _probe_rf = any((root / s / "labels").exists() for s in splits)
    _probe_yolo = any((root / "labels" / s).exists() for s in splits)

    if not _probe_rf and not _probe_yolo:
        print(
            f"[ERROR] Cannot locate label directories under: {root}\n"
            f"        Checked Roboflow layout  ({splits[0]}/labels) "
            f"and YOLO layout (labels/{splits[0]})"
        )
        sys.exit(1)

    # Prefer Roboflow layout when both are detected (won't happen in practice)
    use_roboflow = _probe_rf
    validated = 0

    for split in splits:
        label_dir = (
            root / split / "labels"
            if use_roboflow
            else root / "labels" / split
        )
        if not label_dir.exists():
            print(f"[SKIP] Split '{split}' not found: {label_dir}")
            continue
        check_labels(str(label_dir))
        validated += 1

    if validated == 0:
        print(f"[ERROR] No valid split label directories found under: {root}")
        sys.exit(1)

    return True


def count_images(root_dir: str) -> int:
    """
    Recursively counts image files in dataset directory.
    Returns 0 if directory does not exist (safe fail).
    """

    if not os.path.exists(root_dir):
        print(f"[WARN] Missing directory: {root_dir}")
        return 0

    exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    total = 0

    for r, _, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith(exts):
                total += 1

    return total


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python utils/data_check.py <label_dir>")
        sys.exit(1)
    check_labels(sys.argv[1])
