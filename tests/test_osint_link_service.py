import pytest

from app.services.osint_link_service import OsintLinkService


def _config():
    return {
        "osint_enrichment": {
            "links": {
                "enabled": True,
                "require_manual_entry": True,
                "fetch_preview": False,
                "fetch_full_page": False,
            }
        }
    }


def test_link_service_stores_manual_link_without_scraping():
    service = OsintLinkService(config=_config())
    source = service.create_source(
        case_id="case_1",
        title="Manual source",
        url="https://example.com/article",
        description="Analyst-provided context",
        source_reliability="medium",
        actor="operator",
        metadata={"label": "manual"},
    )

    assert source.metadata["manual_entry_only"] is True
    assert source.metadata["fetch_preview"] is False
    assert source.metadata["fetch_full_page"] is False
    assert source.metadata["domain"] == "example.com"


def test_link_service_rejects_invalid_url():
    service = OsintLinkService(config=_config())

    with pytest.raises(ValueError, match="valid http/https URL"):
        service.create_source(
            case_id="case_1",
            title="Bad",
            url="ftp://example.com",
            description="Invalid",
            source_reliability="low",
            actor="operator",
        )
