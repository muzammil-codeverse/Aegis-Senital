from __future__ import annotations


def has_permission(role: str, permission: str, rbac_config: dict) -> bool:
    if not role:
        return False
    allowed = rbac_config.get(str(role).lower(), [])
    if "*" in allowed:
        return True
    return permission in allowed


def require_permission(permission: str):
    def checker(role: str, rbac_config: dict) -> bool:
        if not has_permission(role, permission, rbac_config):
            raise PermissionError(f"Permission required: {permission}")
        return True

    return checker


def permissions_for_role(role: str, rbac_config: dict) -> list[str]:
    return list(rbac_config.get(str(role).lower(), []))
