import sys
from pathlib import Path


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
    splits: tuple[str, ...] = ("train", "val", "test"),
) -> bool:
    """
    Validate label files for multiple dataset splits under dataset_root/labels/.

    Skips any split directory that does not exist (e.g. no test split).
    Calls check_labels() for each present split — exits with code 1 on first
    failure found inside a split.

    Returns True only when all present splits pass.
    """
    root = Path(dataset_root)
    validated = 0

    for split in splits:
        label_dir = root / "labels" / split
        if not label_dir.exists():
            print(f"[SKIP] Split not found, skipping: {label_dir}")
            continue
        check_labels(str(label_dir))
        validated += 1

    if validated == 0:
        print(f"[ERROR] No split label directories found under: {root / 'labels'}")
        sys.exit(1)

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python utils/data_check.py <label_dir_or_dataset_root> [--splits]")
        sys.exit(1)
    check_labels(sys.argv[1])
