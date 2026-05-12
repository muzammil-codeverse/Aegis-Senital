from app.repositories.model_registry_repository import get_model_registry_repository, reset_model_registry_repository
from app.services.model_governance_service import list_registry_for_api


def test_active_models_have_known_limitations():
    reset_model_registry_repository()
    rows = list_registry_for_api()
    assert rows
    for row in rows:
        if str(row.get("status") or "").lower() != "active":
            continue
        lim = row.get("known_limitations")
        assert isinstance(lim, list) and len(lim) > 0, row.get("model_id")
