"""همه مدل‌ها اینجا جمع می‌شوند تا Alembic آن‌ها را ببیند."""
from app.db.base import Base  # noqa: F401
from app.db.models.monitoring import (  # noqa: F401
    Alert,
    AlertRule,
    Metric,
    MetricAggregate,
    Notification,
    TrafficRecord,
)
from app.db.models.ops import (  # noqa: F401
    AuditLog,
    Backup,
    Deployment,
    DeploymentLog,
    Job,
    LogEntry,
    Setting,
)
from app.db.models.server import Event, Server, ServerAgent, ServerGroup  # noqa: F401
from app.db.models.tunnel import Tunnel, TunnelConfig, TunnelTemplate, TunnelType  # noqa: F401
from app.db.models.user import (  # noqa: F401
    ApiToken,
    Permission,
    Role,
    RolePermission,
    SecurityEvent,
    User,
    UserSession,
)

__all__ = [
    "Base",
    "User",
    "UserSession",
    "ApiToken",
    "Role",
    "Permission",
    "RolePermission",
    "SecurityEvent",
    "Server",
    "ServerAgent",
    "ServerGroup",
    "Event",
    "Tunnel",
    "TunnelConfig",
    "TunnelTemplate",
    "TunnelType",
    "Metric",
    "MetricAggregate",
    "TrafficRecord",
    "Alert",
    "AlertRule",
    "Notification",
    "AuditLog",
    "Deployment",
    "DeploymentLog",
    "Job",
    "Setting",
    "Backup",
    "LogEntry",
]
