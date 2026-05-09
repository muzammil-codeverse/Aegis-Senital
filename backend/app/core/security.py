from __future__ import annotations

import os
from pathlib import Path


def _resolve_allowed_roots() -> list[Path]:
    """Return absolute paths of every directory frame files may live in."""
    try:
        from inference.config_runtime import load_runtime_config
        cfg = load_runtime_config("camera_streaming")
        dirs = cfg.get("snapshot", {}).get("allowed_dirs") or []
    except Exception:
        dirs = []

    # Always include the default backend/output directory
    _project_root = Path(__file__).resolve().parents[3]
    defaults = [
        _project_root / "output",
        _project_root / "backend" / "output",
        _project_root / "storage" / "frames",
    ]
    resolved: list[Path] = list(defaults)
    for d in dirs:
        try:
            p = Path(d)
            if not p.is_absolute():
                p = (_project_root / p).resolve()
            else:
                p = p.resolve()
            if p not in resolved:
                resolved.append(p)
        except Exception:
            pass
    return resolved


_ALLOWED_ROOTS: list[Path] | None = None


def _get_allowed_roots() -> list[Path]:
    global _ALLOWED_ROOTS
    if _ALLOWED_ROOTS is None:
        _ALLOWED_ROOTS = _resolve_allowed_roots()
    return _ALLOWED_ROOTS


def safe_frame_path(frame_path: str) -> Path | None:
    """
    Resolve frame_path to an absolute Path only if it lives inside an
    allowed snapshot directory.  Returns None for anything that escapes
    or doesn't exist.

    Security properties:
    - Resolves symlinks before comparison.
    - Rejects absolute paths that are not inside an allowed root.
    - Rejects relative paths that escape via '..'.
    - Returns None rather than raising, so callers can return 404/400.
    """
    if not frame_path or not isinstance(frame_path, str):
        return None

    # Strip any leading path separators that could anchor to filesystem root
    cleaned = frame_path.lstrip("/\\")

    allowed_roots = _get_allowed_roots()

    # If the stored path is a bare filename (no directory component), search
    # all allowed dirs for the first match.
    candidate_name = Path(cleaned).name
    if cleaned == candidate_name:
        for root in allowed_roots:
            candidate = (root / candidate_name).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                continue
            if candidate.is_file():
                return candidate
        return None

    # Path has directory components — resolve and check containment.
    for root in allowed_roots:
        candidate = (root / cleaned).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            continue  # path escaped root — skip
        if candidate.is_file():
            return candidate

    return None


def is_safe_extension(path: Path, allowed: tuple[str, ...] = (".jpg", ".jpeg", ".png")) -> bool:
    return path.suffix.lower() in allowed
