from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.models.osint_models import CaseExternalSource
from app.repositories.osint_repository import load_osint_config


class OsintLinkService:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._raw_config = config or load_osint_config()
        self._config = dict((self._raw_config.get("osint_enrichment") or {}).get("links") or {})

    def create_source(
        self,
        *,
        case_id: str,
        title: str,
        url: str,
        description: str,
        source_reliability: str,
        actor: str,
        metadata: dict[str, Any] | None = None,
    ) -> CaseExternalSource:
        if not bool(self._config.get("enabled", True)):
            self._increment_metric("osint_safety_blocks_total")
            raise RuntimeError("OSINT link enrichment is disabled")
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            self._increment_metric("osint_safety_blocks_total")
            raise ValueError("A valid http/https URL is required")
        return CaseExternalSource(
            case_id=case_id,
            source_type="external_link",
            title=str(title or "").strip(),
            url=parsed.geturl(),
            description=str(description or "").strip(),
            source_reliability=source_reliability,
            analyst_provided=True,
            created_by=actor,
            metadata={
                **dict(metadata or {}),
                "domain": parsed.netloc.lower(),
                "manual_entry_only": True,
                "fetch_preview": False,
                "fetch_full_page": False,
            },
            requires_review=True,
        )

    @staticmethod
    def _increment_metric(name: str, count: int = 1) -> None:
        try:
            from inference.monitoring.metrics import get_metrics

            get_metrics().increment(name, count)
        except Exception:
            pass
        try:
            from inference.metrics import metrics as system_metrics

            system_metrics.increment(name, count)
        except Exception:
            pass
