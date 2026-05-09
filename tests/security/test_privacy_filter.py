from app.models.security_models import PrivacyPolicy, UserAccount
from app.services.privacy_filter import PrivacyFilter


def _user(role: str) -> UserAccount:
    return UserAccount(
        user_id=f"user-{role}",
        username=role,
        display_name=role,
        role=role,
        status="active",
        password_hash="hash",
        created_at=1.0,
        updated_at=1.0,
    )


def test_viewer_identity_display_masking():
    flt = PrivacyFilter(PrivacyPolicy(mask_identity_display_for_viewer=True))
    payload = {"identity_id": "abcdef123456", "display_name": "Sensitive Name"}
    filtered = flt.filter_identity_payload(payload, _user("viewer"))
    assert filtered["display_name"] == "Identity 123456"


def test_operator_watchlist_reason_hidden():
    flt = PrivacyFilter(PrivacyPolicy(hide_watchlist_reason_for_operator=True))
    payload = {"items": [{"watchlist_id": "w1", "reason": "confidential"}]}
    filtered = flt.filter_watchlist_payload(payload, _user("operator"))
    assert "reason" not in filtered["items"][0]


def test_embeddings_removed():
    flt = PrivacyFilter(PrivacyPolicy())
    payload = {"embedding": [1, 2, 3], "metadata": {"embedding_vector_ref": "emb:1"}}
    filtered = flt.filter_identity_payload(payload, _user("analyst"))
    assert "embedding" not in filtered
    assert "embedding_vector_ref" not in filtered["metadata"]


def test_absolute_paths_removed():
    flt = PrivacyFilter(PrivacyPolicy())
    payload = {"image_path": "C:\\secret\\face.png", "notes": "/var/private/file.jpg"}
    filtered = flt.filter_identity_payload(payload, _user("analyst"))
    assert "image_path" not in filtered
    assert "notes" not in filtered
