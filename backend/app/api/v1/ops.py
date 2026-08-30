"""Audit، استقرارها، تنظیمات، پشتیبان‌گیری، سلامت، نسخه‌ها و به‌روزرسانی."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import APP_VERSION, MIN_AGENT_VERSION, settings
from app.core.deps import Principal, client_ip, current_principal, require
from app.core.errors import Conflict, NotFound
from app.core.rbac import Perm
from app.db.models.ops import AuditLog, Backup, Deployment, DeploymentLog, Job
from app.db.models.server import Server
from app.db.session import get_db
from app.schemas.common import OkResponse, Page, PageParams, paginate
from app.schemas.monitoring import HealthOverview, SecurityOverview
from app.schemas.ops import (
    AuditLogOut,
    BackupCreate,
    BackupOut,
    DeploymentDetail,
    DeploymentLogOut,
    DeploymentOut,
    JobOut,
    RestoreRequest,
    SettingOut,
    SettingsUpdate,
    UpdateCheckOut,
    VersionInfo,
)
from app.services import backup_service, health_service, settings_service, update_service
from app.services.audit import record_audit

router = APIRouter(tags=["ops"])


# ---------------- Audit ----------------


@router.get("/audit-logs", response_model=Page[AuditLogOut])
async def list_audit(
    params: PageParams = Depends(),
    action: str | None = Query(default=None),
    username: str | None = Query(default=None),
    server_id: str | None = Query(default=None),
    tunnel_id: str | None = Query(default=None),
    result: str | None = Query(default=None, pattern="^(success|failure)$"),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.AUDIT_READ.value)),
):
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if username:
        query = query.where(AuditLog.username == username)
    if server_id:
        query = query.where(AuditLog.server_id == server_id)
    if tunnel_id:
        query = query.where(AuditLog.tunnel_id == tunnel_id)
    if result:
        query = query.where(AuditLog.result == result)
    if since:
        query = query.where(AuditLog.created_at >= since)
    if until:
        query = query.where(AuditLog.created_at <= until)
    if params.search:
        query = query.where(AuditLog.target.ilike(f"%{params.search}%"))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(AuditLog.created_at.desc()).offset(params.offset).limit(params.per_page)
        )
    ).scalars().all()
    return paginate([AuditLogOut.model_validate(r) for r in rows], total, params)


# ---------------- Deployments ----------------


@router.get("/deployments", response_model=Page[DeploymentOut])
async def list_deployments(
    params: PageParams = Depends(),
    status: str | None = Query(default=None),
    tunnel_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TUNNELS_READ.value)),
):
    query = select(Deployment)
    if status:
        query = query.where(Deployment.status == status)
    if tunnel_id:
        query = query.where(Deployment.tunnel_id == tunnel_id)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(Deployment.created_at.desc()).offset(params.offset).limit(params.per_page)
        )
    ).scalars().all()
    return paginate([DeploymentOut.model_validate(r) for r in rows], total, params)


@router.get("/deployments/{deployment_id}", response_model=DeploymentDetail)
async def get_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TUNNELS_READ.value)),
):
    dep = await db.get(Deployment, deployment_id)
    if dep is None:
        raise NotFound("استقرار یافت نشد.")
    logs = (
        await db.execute(
            select(DeploymentLog)
            .where(DeploymentLog.deployment_id == deployment_id)
            .order_by(DeploymentLog.seq.asc())
        )
    ).scalars().all()
    detail = DeploymentDetail.model_validate(dep)
    detail.logs = [DeploymentLogOut.model_validate(r) for r in logs]
    return detail


@router.post("/deployments/{deployment_id}/retry")
async def retry_deployment(
    deployment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.TUNNELS_MODIFY.value)),
):
    import asyncio

    from app.db.models.tunnel import Tunnel
    from app.services import deployment as deploy_service

    old = await db.get(Deployment, deployment_id)
    if old is None:
        raise NotFound("استقرار یافت نشد.")
    if old.status in ("pending", "running"):
        raise Conflict("این استقرار همچنان در حال اجراست.")
    tunnel = await db.get(Tunnel, old.tunnel_id) if old.tunnel_id else None
    if tunnel is None:
        raise NotFound("تونل مربوط به این استقرار وجود ندارد.")
    server = await db.get(Server, tunnel.source_server_id)
    dep = await deploy_service.create_deployment(
        db, kind=old.kind, tunnel=tunnel, server=server, user_id=actor.id, dry_run=old.dry_run
    )
    dep.retry_of = old.id
    tunnel.state = "deploying"
    await record_audit(
        db, action="deployment_retry", user=actor.user, tunnel_id=tunnel.id, ip=client_ip(request)
    )
    await db.commit()
    asyncio.create_task(deploy_service.run_tunnel_deployment(dep.id))
    return {"deployment_id": dep.id}


@router.post("/deployments/{deployment_id}/cancel", response_model=OkResponse)
async def cancel_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TUNNELS_MODIFY.value)),
):
    dep = await db.get(Deployment, deployment_id)
    if dep is None:
        raise NotFound("استقرار یافت نشد.")
    if dep.status not in ("pending", "running"):
        raise Conflict("این استقرار در حال اجرا نیست.")
    dep.status = "cancelled"
    dep.finished_at = datetime.now(timezone.utc)
    return OkResponse(message="درخواست لغو ثبت شد.")


@router.get("/jobs", response_model=Page[JobOut])
async def list_jobs(
    params: PageParams = Depends(),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(current_principal),
):
    query = select(Job)
    if status:
        query = query.where(Job.status == status)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(query.order_by(Job.created_at.desc()).offset(params.offset).limit(params.per_page))
    ).scalars().all()
    return paginate([JobOut.model_validate(r) for r in rows], total, params)


# ---------------- Settings ----------------


@router.get("/settings", response_model=list[SettingOut])
async def get_settings_list(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(require(Perm.SETTINGS_READ.value))
):
    rows = await settings_service.get_all(db, reveal=False)
    return [SettingOut(**row) for row in rows]


@router.put("/settings", response_model=OkResponse)
async def update_settings(
    payload: SettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.SETTINGS_WRITE.value)),
):
    changed = await settings_service.set_many(db, payload.values)
    await record_audit(
        db,
        action="settings_updated",
        user=actor.user,
        target=", ".join(changed),
        ip=client_ip(request),
        payload={"keys": changed},
    )
    return OkResponse(message=f"{len(changed)} تنظیم ذخیره شد.")


@router.get("/settings/export")
async def export_settings(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(require(Perm.SETTINGS_READ.value))
):
    """خروجی JSON تنظیمات؛ مقادیر حساس ماسک می‌شوند."""
    rows = await settings_service.get_all(db, reveal=False)
    return {
        "panel_version": APP_VERSION,
        "exported_at": datetime.now(timezone.utc),
        "settings": rows,
    }


# ---------------- Backup / Restore ----------------


@router.get("/backups", response_model=Page[BackupOut])
async def list_backups(
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.BACKUP_MANAGE.value)),
):
    query = select(Backup)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(Backup.created_at.desc()).offset(params.offset).limit(params.per_page)
        )
    ).scalars().all()
    return paginate([BackupOut.model_validate(r) for r in rows], total, params)


@router.post("/backups", response_model=BackupOut, status_code=201)
async def create_backup(
    payload: BackupCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.BACKUP_MANAGE.value)),
):
    row = await backup_service.create_backup(db, payload.kind, payload.note, actor.id)
    await record_audit(
        db, action="backup_created", user=actor.user, target=row.filename, ip=client_ip(request)
    )
    return BackupOut.model_validate(row)


@router.post("/backups/restore", response_model=OkResponse)
async def restore_backup(
    payload: RestoreRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.BACKUP_MANAGE.value)),
):
    if not payload.confirm:
        raise Conflict("برای بازگردانی باید تأیید نهایی را ارسال کنید.")
    backup = await db.get(Backup, payload.backup_id)
    if backup is None:
        raise NotFound("فایل پشتیبان یافت نشد.")
    if payload.backup_current_state:
        await backup_service.create_backup(db, "full", "پیش از بازگردانی", actor.id)
    await backup_service.restore_backup(db, backup)
    await record_audit(
        db, action="backup_restored", user=actor.user, target=backup.filename, ip=client_ip(request)
    )
    return OkResponse(message="بازگردانی انجام شد. برای اطمینان، پنل را یک بار ری‌استارت کنید.")


@router.delete("/backups/{backup_id}", response_model=OkResponse)
async def delete_backup(
    backup_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.BACKUP_MANAGE.value)),
):
    import os

    row = await db.get(Backup, backup_id)
    if row is None:
        raise NotFound("فایل پشتیبان یافت نشد.")
    try:
        if os.path.exists(row.path):
            os.remove(row.path)
    except OSError:
        pass
    await db.delete(row)
    return OkResponse(message="پشتیبان حذف شد.")


# ---------------- Health / Version / Update ----------------


@router.get("/health/overview", response_model=HealthOverview)
async def health_overview(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(current_principal)
):
    data = await health_service.overview(db)
    return HealthOverview(**data)


@router.get("/security/overview", response_model=SecurityOverview)
async def security_overview(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(require(Perm.SETTINGS_READ.value))
):
    data = await health_service.security_overview(db)
    return SecurityOverview(**data)


@router.get("/version", response_model=VersionInfo)
async def version_info(_: Principal = Depends(current_principal)):
    return VersionInfo(
        panel=APP_VERSION,
        backend=APP_VERSION,
        frontend=APP_VERSION,
        agent_min=MIN_AGENT_VERSION,
        database="PostgreSQL",
        environment=settings.ENVIRONMENT,
    )


@router.get("/updates/check", response_model=list[UpdateCheckOut])
async def check_updates(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(require(Perm.UPDATE_MANAGE.value))
):
    panel = await update_service.check_panel_update(db)
    agents = await update_service.check_agent_updates(db)
    return [UpdateCheckOut(**panel), *[UpdateCheckOut(**a) for a in agents]]


@router.post("/updates/panel")
async def update_panel(
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.UPDATE_MANAGE.value)),
):
    result = await update_service.update_panel(db, actor.id)
    await record_audit(db, action="panel_update_prepared", user=actor.user, ip=client_ip(request))
    return result


@router.post("/updates/agent/{server_id}")
async def update_agent(
    server_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.UPDATE_MANAGE.value)),
):
    server = await db.get(Server, server_id)
    if server is None:
        raise NotFound("سرور یافت نشد.")
    result = await update_service.update_agent(db, server, actor.id)
    await record_audit(
        db,
        action="agent_updated",
        user=actor.user,
        server_id=server.id,
        target=server.name,
        result="success" if result.get("ok") else "failure",
        error=str(result.get("error", "")),
        ip=client_ip(request),
    )
    return result
