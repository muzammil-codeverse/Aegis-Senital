from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.osint_models import CaseDocumentSummary, CaseExternalSource
from app.repositories.osint_repository import load_osint_config
from app.services.llm_provider import llm_output_as_json
from app.services.llm_service import get_llm_service


OSINT_OPERATOR_CAVEAT = (
    "This enrichment summary is based only on analyst-provided material. "
    "It does not independently verify identity, criminality, or external claims."
)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class OsintSummaryService:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._raw_config = config or load_osint_config()
        self._config = dict((self._raw_config.get("osint_enrichment") or {}).get("llm") or {})

    def summarize_sources(
        self,
        *,
        case_id: str,
        sources: list[CaseExternalSource],
        actor: str,
        operator_instructions: str = "",
        escalate: bool = False,
    ) -> CaseDocumentSummary:
        if not sources:
            raise ValueError("At least one enrichment source is required")
        llm_service = get_llm_service()
        selection = llm_service._select_model("evidence_summary", escalate=escalate, final_quality=False)
        provider = llm_service._get_provider(selection["provider"])
        material = [self._extract_material(source) for source in sources]
        prompt = {
            "task": "Summarize analyst-provided enrichment material only.",
            "operator_instructions": operator_instructions.strip(),
            "case_id": case_id,
            "sources": material,
            "required_caveat": OSINT_OPERATOR_CAVEAT,
            "required_output_schema": {
                "summary": "string",
                "key_points": ["string"],
                "limitations": ["string"],
            },
        }
        raw_output = provider.generate(
            json.dumps(prompt, ensure_ascii=True, sort_keys=True),
            context={
                "task_type": "osint_summary",
                "instructions": (
                    "You summarize only analyst-provided enrichment material. "
                    "Do not browse, scrape, or infer beyond the supplied sources. "
                    "Do not verify identity, criminality, or external claims. "
                    "Return JSON with summary, key_points, and limitations."
                ),
                "model": selection["model"],
                "reasoning_effort": selection["reasoning_effort"],
                "max_output_tokens": selection["max_output_tokens"],
            },
        )
        parsed = self._parse_or_fallback(raw_output, material)
        return CaseDocumentSummary(
            case_id=case_id,
            source_ids=[item.source_id for item in sources],
            summary=parsed["summary"],
            key_points=parsed["key_points"],
            source_references=[
                {
                    "type": "external_source",
                    "id": item.source_id,
                    "label": item.title or item.source_type,
                }
                for item in sources
            ],
            operator_review_caveat=OSINT_OPERATOR_CAVEAT,
            limitations=parsed["limitations"],
            provider=selection["provider"],
            model=selection["model"],
            created_by=actor,
            metadata={"source_count": len(sources)},
        )

    def _extract_material(self, source: CaseExternalSource) -> dict[str, Any]:
        material = {
            "source_id": source.source_id,
            "source_type": source.source_type,
            "title": source.title,
            "description": source.description,
            "source_reliability": source.source_reliability,
            "domain": str((source.metadata or {}).get("domain") or ""),
            "url_present": bool(source.url),
            "metadata": source.metadata,
            "uploaded_text_excerpt": "",
        }
        if source.storage_uri:
            path = self._resolve_local_path(source.storage_uri)
            if path.suffix.lower() in {".txt", ".md", ".json", ".csv"} and path.exists():
                try:
                    material["uploaded_text_excerpt"] = path.read_text(encoding="utf-8", errors="ignore")[:6000]
                except Exception:
                    material["uploaded_text_excerpt"] = ""
            elif path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}:
                material.setdefault("metadata", {})["binary_content_not_auto_parsed"] = True
        return material

    @staticmethod
    def _resolve_local_path(storage_uri: str) -> Path:
        path = Path(str(storage_uri or "").strip())
        if path.is_absolute():
            return path
        return (PROJECT_ROOT / path).resolve()

    def _parse_or_fallback(self, raw_output: str, material: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            parsed = llm_output_as_json(raw_output)
            return {
                "summary": str(parsed.get("summary") or "").strip() or self._fallback_summary(material),
                "key_points": [str(item).strip() for item in (parsed.get("key_points") or []) if str(item).strip()],
                "limitations": [str(item).strip() for item in (parsed.get("limitations") or []) if str(item).strip()] or self._default_limitations(material),
            }
        except Exception:
            return {
                "summary": self._fallback_summary(material),
                "key_points": self._fallback_key_points(material),
                "limitations": self._default_limitations(material),
            }

    @staticmethod
    def _fallback_summary(material: list[dict[str, Any]]) -> str:
        titles = ", ".join(item.get("title") or item.get("source_type") for item in material[:3])
        return f"Analyst-provided enrichment was reviewed from {len(material)} source(s): {titles}."

    @staticmethod
    def _fallback_key_points(material: list[dict[str, Any]]) -> list[str]:
        key_points: list[str] = []
        for item in material[:5]:
            point = item.get("description") or item.get("title") or item.get("source_type")
            if point:
                key_points.append(str(point).strip()[:240])
        return key_points or ["Analyst-provided enrichment material was available for review."]

    @staticmethod
    def _default_limitations(material: list[dict[str, Any]]) -> list[str]:
        limitations = [
            "Only analyst-provided material was reviewed.",
            "Remote pages were not fetched or independently verified.",
        ]
        if any(item.get("uploaded_text_excerpt") == "" and item.get("source_type") in {"uploaded_document", "uploaded_image"} for item in material):
            limitations.append("Binary documents or images were not automatically parsed beyond analyst-provided metadata.")
        return limitations
