from app.security.permissions import has_permission


RBAC = {
    "admin": ["*"],
    "viewer": ["camera:read", "alert:read", "incident:read", "map:read"],
    "operator": ["camera:read", "camera:control", "alert:read", "alert:write"],
    "analyst": ["identity:read", "incident:read", "watchlist:read"],
}


def test_admin_wildcard_allows_all():
    assert has_permission("admin", "model:write", RBAC)


def test_viewer_cannot_write_sensitive_resources():
    assert not has_permission("viewer", "alert:write", RBAC)
    assert not has_permission("viewer", "watchlist:write", RBAC)
    assert not has_permission("viewer", "model:write", RBAC)


def test_operator_alert_permissions_but_not_watchlist():
    assert has_permission("operator", "alert:write", RBAC)
    assert not has_permission("operator", "watchlist:write", RBAC)


def test_analyst_identity_read_but_not_model_write():
    assert has_permission("analyst", "identity:read", RBAC)
    assert not has_permission("analyst", "model:write", RBAC)
