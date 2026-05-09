from __future__ import annotations
import threading
import uuid
from typing import Any

VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_CATEGORIES = {
    "suspicious_object", "suspicious_behavior", "identity_obscuration",
    "forced_entry_tool", "weapon", "crowd_anomaly", "other",
}
MAX_PROMPTS = 200


class OpenVocabPromptLibrary:
    """Thread-safe prompt library. Config-loaded defaults, runtime additions."""

    def __init__(self, config: dict | None = None):
        self._lock = threading.RLock()
        self._prompts: dict[str, dict] = {}
        self._config = config or {}
        self._max_prompts = self._config.get("max_prompts", MAX_PROMPTS)

    def load_from_config(self) -> None:
        prompt_list = self._config.get("prompt_library", [])
        with self._lock:
            for entry in prompt_list:
                pid = entry.get("prompt_id") or str(uuid.uuid4())
                self._prompts[pid] = {
                    "prompt_id": pid,
                    "text": entry.get("text", ""),
                    "category": entry.get("category", "other"),
                    "severity": entry.get("severity", "medium"),
                    "enabled": entry.get("enabled", True),
                    "threshold": float(entry.get("threshold", 0.35)),
                    "metadata": entry.get("metadata", {}),
                }

    def list_prompts(self, category: str | None = None, enabled: bool | None = None) -> list[dict]:
        with self._lock:
            result = list(self._prompts.values())
        if category is not None:
            result = [p for p in result if p["category"] == category]
        if enabled is not None:
            result = [p for p in result if p["enabled"] == enabled]
        return result

    def get_prompt(self, prompt_id: str) -> dict | None:
        with self._lock:
            return self._prompts.get(prompt_id)

    def add_prompt(
        self,
        text: str,
        category: str,
        severity: str = "medium",
        threshold: float | None = None,
        metadata: dict | None = None,
        prompt_id: str | None = None,
    ) -> dict:
        if not text or not text.strip():
            raise ValueError("Prompt text must be non-empty")
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"Invalid severity: {severity}")
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")
        # No OS/system command injection
        if any(c in text for c in ["\x00", "\n", "\r", "$(", "`", "&&", "||", ";"]):
            raise ValueError("Prompt text contains invalid characters")

        with self._lock:
            if len(self._prompts) >= self._max_prompts:
                raise ValueError(f"Prompt library full (max {self._max_prompts})")
            pid = prompt_id or str(uuid.uuid4())
            prompt = {
                "prompt_id": pid,
                "text": text.strip(),
                "category": category,
                "severity": severity,
                "enabled": True,
                "threshold": threshold if threshold is not None else self._config.get("thresholds", {}).get("default_box_threshold", 0.35),
                "metadata": metadata or {},
            }
            self._prompts[pid] = prompt
            return dict(prompt)

    def update_prompt(self, prompt_id: str, updates: dict) -> dict | None:
        with self._lock:
            if prompt_id not in self._prompts:
                return None
            prompt = self._prompts[prompt_id]
            if "text" in updates:
                if not updates["text"] or not updates["text"].strip():
                    raise ValueError("Prompt text must be non-empty")
                if any(c in updates["text"] for c in ["\x00", "\n", "\r", "$(", "`", "&&", "||", ";"]):
                    raise ValueError("Prompt text contains invalid characters")
                prompt["text"] = updates["text"].strip()
            if "category" in updates:
                if updates["category"] not in VALID_CATEGORIES:
                    raise ValueError(f"Invalid category: {updates['category']}")
                prompt["category"] = updates["category"]
            if "severity" in updates:
                if updates["severity"] not in VALID_SEVERITIES:
                    raise ValueError(f"Invalid severity: {updates['severity']}")
                prompt["severity"] = updates["severity"]
            if "threshold" in updates:
                prompt["threshold"] = float(updates["threshold"])
            if "enabled" in updates:
                prompt["enabled"] = bool(updates["enabled"])
            if "metadata" in updates:
                prompt["metadata"] = updates["metadata"]
            return dict(prompt)

    def disable_prompt(self, prompt_id: str) -> bool:
        with self._lock:
            if prompt_id not in self._prompts:
                return False
            self._prompts[prompt_id]["enabled"] = False
            return True

    def get_enabled_prompts(self) -> list[dict]:
        return self.list_prompts(enabled=True)
