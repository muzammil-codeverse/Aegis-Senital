from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_REGISTRY_FILE = _PROJECT_ROOT / "models" / "registry.json"


class ModelRegistry:
    """
    Immutable model artifact registry backed by models/registry.json.

    Design rules enforced:
      - Every training run produces a new version; the version key is the run_id.
      - Artifacts are never overwritten: register_model() raises if the version
        already exists at a *different* path.
      - get_latest_model() returns the highest lexicographic version so callers
        that format versions as YYYYMMDD_HHMMSS or vN naturally get the newest.
    """

    def __init__(self, registry_path: Path | str | None = None) -> None:
        self._path = Path(registry_path) if registry_path else _REGISTRY_FILE
        self._data: dict[str, dict[str, dict]] = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        logger.debug(f"model registry saved: {self._path}")

    # ── write API ───────────────────────────────────────────────────────────────

    def register_model(
        self,
        model_name: str,
        version: str,
        path: str,
        classes: list[str] | None = None,
        mAP50: float | None = None,
        training_dataset: str | None = None,
        framework: str = "YOLOv8",
        extra: dict | None = None,
    ) -> dict:
        """
        Register a model artifact.

        Raises ValueError if the version already exists at a different path
        (no silent overwrite).  Re-registering at the same path is a no-op.
        Raises FileNotFoundError if the artifact file is missing.
        """
        versions = self._data.setdefault(model_name, {})

        if version in versions:
            existing = versions[version]
            if existing["path"] != path:
                raise ValueError(
                    f"Model '{model_name}' version '{version}' is already registered "
                    f"at '{existing['path']}'. Create a new version instead of overwriting."
                )
            logger.debug(f"registry: re-registered existing {model_name}:{version}")
            return existing

        model_path = Path(path)
        if not model_path.exists():
            # Try relative to project root
            model_path = _PROJECT_ROOT / path
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Model artifact not found: {path}. Register only committed artifacts."
                )

        entry: dict = {
            "model_name": model_name,
            "version": version,
            "path": str(path),
            "classes": classes or [],
            "mAP50": mAP50,
            "training_dataset": training_dataset,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "framework": framework,
        }
        if extra:
            entry.update(extra)

        versions[version] = entry
        self._save()

        logger.info(json.dumps({
            "event": "model_registered",
            "model_name": model_name,
            "version": version,
            "path": str(path),
        }))
        return entry

    # ── read API ─────────────────────────────────────────────────────────────────

    def get_latest_model(self, model_name: str) -> dict:
        """Return metadata for the most recent version (highest lex sort key)."""
        versions = self._data.get(model_name)
        if not versions:
            raise KeyError(f"No registered versions for model '{model_name}'.")
        latest_key = sorted(versions)[-1]
        return versions[latest_key]

    def load_model_by_version(self, model_name: str, version: str) -> dict:
        """Return metadata for a specific version; raises KeyError if absent."""
        versions = self._data.get(model_name, {})
        if version not in versions:
            raise KeyError(
                f"Model '{model_name}' version '{version}' not found. "
                f"Available: {sorted(versions)}"
            )
        return versions[version]

    def list_versions(self, model_name: str) -> list[str]:
        return sorted(self._data.get(model_name, {}))

    def list_models(self) -> list[str]:
        return sorted(self._data)

    def validate_model_compatibility(self, path: str) -> bool:
        """
        Check that the artifact exists and has a supported extension (.pt or .onnx).
        Does NOT load the model — safe to call from any context.
        """
        p = Path(path)
        if not p.exists():
            p = _PROJECT_ROOT / path
        if not p.exists():
            logger.warning(f"validate_model_compatibility: missing: {path}")
            return False
        if p.is_dir():
            return any(candidate.suffix.lower() in (".pt", ".onnx") for candidate in p.rglob("*"))
        if p.suffix.lower() not in (".pt", ".onnx"):
            logger.warning(f"validate_model_compatibility: unsupported format '{p.suffix}': {path}")
            return False
        return True


# ── module-level singleton ──────────────────────────────────────────────────────

_registry: ModelRegistry | None = None


def get_registry(registry_path: Path | str | None = None) -> ModelRegistry:
    """Return (or create) the module-level ModelRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry(registry_path)
    return _registry


# Convenience wrappers so callers don't need to hold a reference to the instance

def register_model(model_name: str, version: str, path: str, **kwargs) -> dict:
    return get_registry().register_model(model_name, version, path, **kwargs)


def get_latest_model(model_name: str) -> dict:
    return get_registry().get_latest_model(model_name)


def load_model_by_version(model_name: str, version: str) -> dict:
    return get_registry().load_model_by_version(model_name, version)


def validate_model_compatibility(path: str) -> bool:
    return get_registry().validate_model_compatibility(path)
