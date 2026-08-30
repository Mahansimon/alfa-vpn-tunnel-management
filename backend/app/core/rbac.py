"""RBAC: نقش‌ها و دسترسی‌های granular."""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Perm(StrEnum):
    SERVERS_READ = "servers.read"
    SERVERS_WRITE = "servers.write"
    SERVERS_DELETE = "servers.delete"
    TUNNELS_READ = "tunnels.read"
    TUNNELS_CREATE = "tunnels.create"
    TUNNELS_MODIFY = "tunnels.modify"
    TUNNELS_DELETE = "tunnels.delete"
    METRICS_READ = "metrics.read"
    TRAFFIC_READ = "traffic.read"
    LOGS_READ = "logs.read"
    ALERTS_MANAGE = "alerts.manage"
    SETTINGS_READ = "settings.read"
    SETTINGS_WRITE = "settings.write"
    USERS_MANAGE = "users.manage"
    BACKUP_MANAGE = "backup.manage"
    UPDATE_MANAGE = "update.manage"
    AUDIT_READ = "audit.read"
    TOKENS_MANAGE = "tokens.manage"


VIEWER_PERMS: set[Perm] = {
    Perm.SERVERS_READ,
    Perm.TUNNELS_READ,
    Perm.METRICS_READ,
    Perm.TRAFFIC_READ,
    Perm.LOGS_READ,
    Perm.SETTINGS_READ,
}

OPERATOR_PERMS: set[Perm] = VIEWER_PERMS | {
    Perm.SERVERS_WRITE,
    Perm.TUNNELS_CREATE,
    Perm.TUNNELS_MODIFY,
    Perm.TUNNELS_DELETE,
    Perm.ALERTS_MANAGE,
}

ADMIN_PERMS: set[Perm] = OPERATOR_PERMS | {
    Perm.SERVERS_DELETE,
    Perm.SETTINGS_WRITE,
    Perm.USERS_MANAGE,
    Perm.BACKUP_MANAGE,
    Perm.UPDATE_MANAGE,
    Perm.AUDIT_READ,
    Perm.TOKENS_MANAGE,
}

OWNER_PERMS: set[Perm] = set(Perm)

ROLE_PERMISSIONS: dict[Role, set[Perm]] = {
    Role.VIEWER: VIEWER_PERMS,
    Role.OPERATOR: OPERATOR_PERMS,
    Role.ADMIN: ADMIN_PERMS,
    Role.OWNER: OWNER_PERMS,
}

ROLE_LABELS_FA: dict[Role, str] = {
    Role.OWNER: "مالک",
    Role.ADMIN: "مدیر",
    Role.OPERATOR: "اپراتور",
    Role.VIEWER: "بازدیدکننده",
}


def permissions_for(role: str) -> set[str]:
    try:
        return {p.value for p in ROLE_PERMISSIONS[Role(role)]}
    except ValueError:
        return set()


def has_permission(role: str, permission: str, extra: list[str] | None = None) -> bool:
    if extra and permission in extra:
        return True
    return permission in permissions_for(role)
