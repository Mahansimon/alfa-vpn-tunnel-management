"""مدیریت انواع تونل، تونل‌ها، قالب‌ها، استقرار و توپولوژی شبکه."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Principal, client_ip, require
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.rbac import Perm
from app.db.models.monitoring import TrafficRecord
from app.db.models.ops import Deployment
from app.db.models.server import Event, Server
from app.db.models.tunnel import Tunnel, TunnelConfig, TunnelTemplate, TunnelType
from app.db.session import get_db
from app.schemas.common import BulkAction, OkResponse, Page, PageParams, paginate
from app.schemas.tunnels import (
    TopologyEdge,
    TopologyNode,
    TopologyOut,
    TunnelCreate,
    TunnelOut,
    TunnelTemplateCreate,
    TunnelTemplateOut,
    TunnelTypeConfigure,
    TunnelTypeOut,
    TunnelUpdate,
    TunnelValidateResult,
)
from app.services import deployment as deploy_service
from app.services.agent_client import agent_client
from app.services.audit import record_audit, record_event
from app.services.realtime import hub
from app.tunnel_adapters.registry import ADAPTERS, adapter_class, build_adapter, sync_registry

router = APIRouter(tags=["tunnels"])


async def _out(db: AsyncSession, tunnel: Tunnel) -> TunnelOut:
    config, _ = await deploy_service.load_config(db, tunnel)
    source = await db.get(Server, tunnel.source_server_id)
    destination = await db.get(Server, tunnel.destination_server_id)
    data = TunnelOut.model_validate(tunnel)
    data.config = config
    data.source_server_name = source.name if source else None
    data.destination_server_name = destination.name if destination else None
    return data


# ---------------- انواع تونل ----------------


@router.get("/tunnel-types", response_model=list[TunnelTypeOut])
async def list_tunnel_types(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(require(Perm.TUNNELS_READ.value))
):
    await sync_registry(db)
    rows = {r.key: r for r in (await db.execute(select(TunnelType))).scalars()}
    out: list[TunnelTypeOut] = []
    for key, cls in ADAPTERS.items():
        meta = cls.describe()
        row = rows.get(key)
        adapter = cls(agent_client, row)
        out.append(
            TunnelTypeOut(
                key=key,
                display_name=meta.display_name,
                display_name_fa=meta.display_name_fa,
                source_kind=meta.source_kind,
                configured=adapter.is_configured(),
                requires=meta.requires,
                capabilities=meta.capabilities,
                config_schema=adapter.config_schema(),
                notes_fa=(row.notes_fa if row else meta.summary_fa) or meta.summary_fa,
                version=(row.version if row else "") or "",
            )
        )
    return out


@router.patch("/tunnel-types/{type_key}", response_model=TunnelTypeOut)
async def configure_tunnel_type(
    type_key: str,
    payload: TunnelTypeConfigure,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.SETTINGS_WRITE.value)),
):
    """محل ورود مسیر Binary یا آدرس Repository هر تونل."""
    cls = adapter_class(type_key)
    row = (await db.execute(select(TunnelType).where(TunnelType.key == type_key))).scalar_one_or_none()
    if row is None:
        raise NotFound("این نوع تونل ثبت نشده است.")
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "repository_url" in data and data["repository_url"]:
        from app.services.update_service import validate_repository

        if not validate_repository(data["repository_url"]):
            raise ValidationFailed("آدرس Repository معتبر نیست (باید با https:// یا git@ شروع شود).")
    for field, value in data.items():
        setattr(row, field, value)
    meta = cls.describe()
    row.configured = bool(row.binary_path if meta.source_kind == "binary" else row.repository_url)
    await db.flush()
    await record_audit(
        db,
        action="tunnel_type_configured",
        user=actor.user,
        target=type_key,
        ip=client_ip(request),
        payload={k: v for k, v in data.items() if k != "binary_checksum"},
    )
    adapter = cls(agent_client, row)
    return TunnelTypeOut(
        key=type_key,
        display_name=meta.display_name,
        display_name_fa=meta.display_name_fa,
        source_kind=meta.source_kind,
        configured=adapter.is_configured(),
        requires=meta.requires,
        capabilities=meta.capabilities,
        config_schema=adapter.config_schema(),
        notes_fa=row.notes_fa or meta.summary_fa,
        version=row.version or "",
    )


# ---------------- تونل‌ها ----------------


@router.get("/tunnels", response_model=Page[TunnelOut])
async def list_tunnels(
    params: PageParams = Depends(),
    type_key: str | None = Query(default=None),
    state: str | None = Query(default=None),
    health: str | None = Query(default=None),
    server_id: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TUNNELS_READ.value)),
):
    query = select(Tunnel)
    if params.search:
        term = f"%{params.search}%"
        query = query.where(or_(Tunnel.name.ilike(term), Tunnel.type_key.ilike(term)))
    if type_key:
        query = query.where(Tunnel.type_key == type_key)
    if state:
        query = query.where(Tunnel.state == state)
    if health:
        query = query.where(Tunnel.health == health)
    if server_id:
        query = query.where(
            (Tunnel.source_server_id == server_id) | (Tunnel.destination_server_id == server_id)
        )
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(Tunnel.created_at.desc()).offset(params.offset).limit(params.per_page)
        )
    ).scalars().all()
    if tag:
        rows = [r for r in rows if tag in (r.tags or [])]
    items = [await _out(db, r) for r in rows]
    return paginate(items, total, params)


@router.post("/tunnels/validate", response_model=TunnelValidateResult)
async def validate_tunnel(
    payload: TunnelCreate,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TUNNELS_CREATE.value)),
):
    """مرحله Review ویزارد: اعتبارسنجی کامل بدون هیچ تغییری روی سرورها."""
    source = await db.get(Server, payload.source_server_id)
    destination = await db.get(Server, payload.destination_server_id)
    errors: list[str] = []
    warnings: list[str] = []
    if source is None or destination is None:
        errors.append("سرور مبدأ یا مقصد یافت نشد.")
    elif source.id == destination.id:
        errors.append("سرور مبدأ و مقصد نمی‌توانند یکی باشند.")
    else:
        for server in (source, destination):
            if not server.agent or not server.agent.enrolled:
                errors.append(f"Agent روی سرور «{server.name}» نصب/ثبت نشده است.")
            elif server.status == "offline":
                warnings.append(f"سرور «{server.name}» در حال حاضر آفلاین است.")
    adapter = await build_adapter(db, payload.type_key, agent_client)
    adapter_errors, adapter_warnings = adapter.validate_config({**payload.config, **payload.secrets})
    errors += adapter_errors
    warnings += adapter_warnings
    summary = {
        "type": adapter.metadata.display_name_fa,
        "source": source.name if source else None,
        "destination": destination.name if destination else None,
        "protocol": payload.config.get("protocol"),
        "listen_port": payload.config.get("listen_port"),
        "remote_port": payload.config.get("remote_port"),
        "requires": adapter.metadata.requires,
    }
    return TunnelValidateResult(valid=not errors, errors=errors, warnings=warnings, summary=summary)


@router.post("/tunnels", response_model=TunnelOut, status_code=201)
async def create_tunnel(
    payload: TunnelCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.TUNNELS_CREATE.value)),
):
    source = await db.get(Server, payload.source_server_id)
    destination = await db.get(Server, payload.destination_server_id)
    if source is None or destination is None:
        raise NotFound("سرور مبدأ یا مقصد یافت نشد.")
    if source.id == destination.id:
        raise ValidationFailed("سرور مبدأ و مقصد نمی‌توانند یکی باشند.")
    adapter = await build_adapter(db, payload.type_key, agent_client)
    errors, _warnings = adapter.validate_config({**payload.config, **payload.secrets})
    if errors:
        raise ValidationFailed("تنظیمات تونل کامل نیست.", details=errors)

    tunnel = Tunnel(
        name=payload.name,
        type_key=payload.type_key,
        source_server_id=source.id,
        destination_server_id=destination.id,
        tags=payload.tags,
        description=payload.description,
        state="draft",
        health="unknown",
    )
    db.add(tunnel)
    await db.flush()
    tunnel.service_name = f"alfa-tunnel-{tunnel.id[:8]}"
    await deploy_service.save_config_revision(
        db, tunnel, {**payload.config, **payload.secrets}, actor.id, "ایجاد اولیه"
    )
    await record_audit(
        db,
        action="tunnel_created",
        user=actor.user,
        tunnel_id=tunnel.id,
        target=tunnel.name,
        ip=client_ip(request),
        payload={"type": payload.type_key},
    )
    await record_event(
        db,
        target_type="tunnel",
        target_id=tunnel.id,
        kind="created",
        title=f"تونل «{tunnel.name}» ساخته شد",
    )
    await db.flush()

    if payload.deploy_now:
        dep = await deploy_service.create_deployment(
            db,
            kind="tunnel_install",
            tunnel=tunnel,
            server=source,
            user_id=actor.id,
            dry_run=payload.dry_run,
        )
        tunnel.state = "deploying"
        await db.commit()
        asyncio.create_task(deploy_service.run_tunnel_deployment(dep.id))
    await hub.publish("tunnels", "tunnel.created", {"id": tunnel.id, "name": tunnel.name})
    return await _out(db, tunnel)


@router.get("/tunnels/{tunnel_id}", response_model=TunnelOut)
async def get_tunnel(
    tunnel_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TUNNELS_READ.value)),
):
    tunnel = await db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise NotFound("تونل یافت نشد.")
    return await _out(db, tunnel)


@router.patch("/tunnels/{tunnel_id}", response_model=TunnelOut)
async def update_tunnel(
    tunnel_id: str,
    payload: TunnelUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.TUNNELS_MODIFY.value)),
):
    tunnel = await db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise NotFound("تونل یافت نشد.")
    if payload.version is not None and payload.version != tunnel.version:
        raise Conflict(
            "این تونل توسط کاربر دیگری تغییر کرده است. صفحه را بازخوانی کنید و دوباره تلاش کنید."
        )
    data = payload.model_dump(exclude_unset=True, exclude={"config", "secrets", "version"})
    for field, value in data.items():
        setattr(tunnel, field, value)
    if payload.config is not None or payload.secrets is not None:
        current_config, current_secrets = await deploy_service.load_config(db, tunnel)
        merged = {
            **current_config,
            **current_secrets,
            **(payload.config or {}),
            **(payload.secrets or {}),
        }
        adapter = await build_adapter(db, tunnel.type_key, agent_client)
        errors, _ = adapter.validate_config(merged)
        if errors:
            raise ValidationFailed("تنظیمات جدید معتبر نیست.", details=errors)
        # نسخه قبلی به عنوان Backup نگه داشته می‌شود
        await deploy_service.save_config_revision(db, tunnel, merged, actor.id, "ویرایش از پنل")
    tunnel.version += 1
    await db.flush()
    await record_audit(
        db,
        action="tunnel_updated",
        user=actor.user,
        tunnel_id=tunnel.id,
        target=tunnel.name,
        ip=client_ip(request),
    )
    await hub.publish("tunnels", "tunnel.updated", {"id": tunnel.id})
    return await _out(db, tunnel)


@router.delete("/tunnels/{tunnel_id}", response_model=OkResponse)
async def delete_tunnel(
    tunnel_id: str,
    request: Request,
    remove_from_servers: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.TUNNELS_DELETE.value)),
):
    tunnel = await db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise NotFound("تونل یافت نشد.")
    name = tunnel.name
    errors: list[str] = []
    if remove_from_servers and tunnel.state in ("deployed", "stopped", "failed"):
        adapter = await build_adapter(db, tunnel.type_key, agent_client)
        for server_id in (tunnel.source_server_id, tunnel.destination_server_id):
            server = await db.get(Server, server_id)
            if server is None:
                continue
            try:
                await adapter.stop(server, tunnel)
                await adapter.uninstall(server, tunnel)
            except Exception as exc:
                errors.append(f"{server.name}: {exc}")
    await db.delete(tunnel)
    await record_audit(
        db,
        action="tunnel_deleted",
        user=actor.user,
        target=name,
        ip=client_ip(request),
        result="success" if not errors else "failure",
        error="؛ ".join(errors),
    )
    await hub.publish("tunnels", "tunnel.deleted", {"id": tunnel_id})
    message = f"تونل «{name}» حذف شد."
    if errors:
        message += " اما حذف از برخی سرورها ناموفق بود: " + "؛ ".join(errors)
    return OkResponse(message=message)


@router.post("/tunnels/{tunnel_id}/deploy")
async def deploy_tunnel(
    tunnel_id: str,
    request: Request,
    dry_run: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.TUNNELS_MODIFY.value)),
):
    tunnel = await db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise NotFound("تونل یافت نشد.")
    running = (
        await db.execute(
            select(Deployment).where(
                Deployment.tunnel_id == tunnel.id, Deployment.status.in_(["pending", "running"])
            )
        )
    ).scalars().first()
    if running:
        raise Conflict("یک استقرار برای این تونل در حال اجراست.")
    source = await db.get(Server, tunnel.source_server_id)
    dep = await deploy_service.create_deployment(
        db, kind="tunnel_install", tunnel=tunnel, server=source, user_id=actor.id, dry_run=dry_run
    )
    if not dry_run:
        tunnel.state = "deploying"
    await record_audit(
        db,
        action="tunnel_deploy" + ("_dry_run" if dry_run else ""),
        user=actor.user,
        tunnel_id=tunnel.id,
        target=tunnel.name,
        ip=client_ip(request),
    )
    await db.commit()
    asyncio.create_task(deploy_service.run_tunnel_deployment(dep.id))
    return {"deployment_id": dep.id, "dry_run": dry_run}


@router.post("/tunnels/{tunnel_id}/actions/{action}")
async def tunnel_action(
    tunnel_id: str,
    action: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.TUNNELS_MODIFY.value)),
):
    tunnel = await db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise NotFound("تونل یافت نشد.")
    outputs = await deploy_service.run_action(db, tunnel, action)
    await record_audit(
        db,
        action=f"tunnel_{action}",
        user=actor.user,
        tunnel_id=tunnel.id,
        target=tunnel.name,
        ip=client_ip(request),
    )
    return {"ok": True, "outputs": outputs}


@router.get("/tunnels/{tunnel_id}/logs")
async def tunnel_logs(
    tunnel_id: str,
    lines: int = Query(default=200, ge=10, le=2000),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.LOGS_READ.value)),
):
    tunnel = await db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise NotFound("تونل یافت نشد.")
    adapter = await build_adapter(db, tunnel.type_key, agent_client)
    output: dict[str, str] = {}
    for server_id in (tunnel.source_server_id, tunnel.destination_server_id):
        server = await db.get(Server, server_id)
        if server is None:
            continue
        try:
            result = await adapter.logs(server, tunnel, lines)
            output[server.name] = result.output or result.error
        except Exception as exc:
            output[server.name] = f"دریافت لاگ ناموفق بود: {exc}"
    return {"logs": output}


@router.get("/tunnels/{tunnel_id}/config-revisions")
async def config_revisions(
    tunnel_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TUNNELS_READ.value)),
):
    rows = (
        await db.execute(
            select(TunnelConfig)
            .where(TunnelConfig.tunnel_id == tunnel_id)
            .order_by(TunnelConfig.revision.desc())
        )
    ).scalars().all()
    return [
        {
            "revision": r.revision,
            "is_active": r.is_active,
            "note": r.note,
            "created_at": r.created_at,
            "payload": r.payload,
            "has_secrets": bool(r.secrets_enc),
        }
        for r in rows
    ]


@router.post("/tunnels/{tunnel_id}/clone", response_model=TunnelOut, status_code=201)
async def clone_tunnel(
    tunnel_id: str,
    request: Request,
    name: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.TUNNELS_CREATE.value)),
):
    origin = await db.get(Tunnel, tunnel_id)
    if origin is None:
        raise NotFound("تونل یافت نشد.")
    config, secrets = await deploy_service.load_config(db, origin)
    clone = Tunnel(
        name=name or f"{origin.name} (کپی)",
        type_key=origin.type_key,
        source_server_id=origin.source_server_id,
        destination_server_id=origin.destination_server_id,
        tags=list(origin.tags or []),
        description=origin.description,
        state="draft",
        health="unknown",
    )
    db.add(clone)
    await db.flush()
    clone.service_name = f"alfa-tunnel-{clone.id[:8]}"
    await deploy_service.save_config_revision(db, clone, {**config, **secrets}, actor.id, "کپی از تونل دیگر")
    await record_audit(
        db, action="tunnel_cloned", user=actor.user, tunnel_id=clone.id, target=clone.name,
        ip=client_ip(request)
    )
    return await _out(db, clone)


@router.post("/tunnels/bulk", response_model=OkResponse)
async def bulk_tunnels(
    payload: BulkAction,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.TUNNELS_MODIFY.value)),
):
    tunnels = (await db.execute(select(Tunnel).where(Tunnel.id.in_(payload.ids)))).scalars().all()
    if not tunnels:
        raise NotFound("تونلی یافت نشد.")
    if payload.action == "delete" and not actor.can(Perm.TUNNELS_DELETE.value):
        raise Conflict("برای حذف تونل دسترسی لازم را ندارید.")
    done, failed = 0, []
    for tunnel in tunnels:
        try:
            if payload.action in ("start", "stop", "restart"):
                await deploy_service.run_action(db, tunnel, payload.action)
            elif payload.action in ("enable", "disable"):
                tunnel.enabled = payload.action == "enable"
            elif payload.action in ("maintenance_on", "maintenance_off"):
                tunnel.maintenance = payload.action == "maintenance_on"
            elif payload.action == "delete":
                await db.delete(tunnel)
            done += 1
        except Exception as exc:
            failed.append(f"{tunnel.name}: {exc}")
    await record_audit(
        db, action=f"tunnels_bulk_{payload.action}", user=actor.user, target=f"{done} تونل",
        ip=client_ip(request), error="؛ ".join(failed), result="success" if not failed else "failure"
    )
    message = f"عملیات روی {done} تونل انجام شد."
    if failed:
        message += " خطاها: " + "؛ ".join(failed[:3])
    return OkResponse(message=message)


# ---------------- قالب‌ها ----------------


@router.get("/tunnel-templates", response_model=list[TunnelTemplateOut])
async def list_templates(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(require(Perm.TUNNELS_READ.value))
):
    rows = (await db.execute(select(TunnelTemplate).order_by(TunnelTemplate.name))).scalars().all()
    return [TunnelTemplateOut.model_validate(r) for r in rows]


@router.post("/tunnel-templates", response_model=TunnelTemplateOut, status_code=201)
async def create_template(
    payload: TunnelTemplateCreate,
    db: AsyncSession = Depends(get_db),
    actor: Principal = Depends(require(Perm.TUNNELS_CREATE.value)),
):
    exists = (
        await db.execute(select(TunnelTemplate).where(TunnelTemplate.name == payload.name))
    ).scalar_one_or_none()
    if exists:
        raise Conflict("قالبی با این نام وجود دارد.")
    from app.tunnel_adapters.base import SECRET_KEYS

    clean = {k: v for k, v in payload.payload.items() if k not in SECRET_KEYS}
    row = TunnelTemplate(
        name=payload.name,
        type_key=payload.type_key,
        payload=clean,
        description=payload.description,
        created_by=actor.id,
    )
    db.add(row)
    await db.flush()
    return TunnelTemplateOut.model_validate(row)


@router.delete("/tunnel-templates/{template_id}", response_model=OkResponse)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TUNNELS_CREATE.value)),
):
    row = await db.get(TunnelTemplate, template_id)
    if row is None:
        raise NotFound("قالب یافت نشد.")
    await db.delete(row)
    return OkResponse(message="قالب حذف شد.")


# ---------------- توپولوژی ----------------


@router.get("/topology", response_model=TopologyOut)
async def topology(
    db: AsyncSession = Depends(get_db), _: Principal = Depends(require(Perm.TUNNELS_READ.value))
):
    servers = (await db.execute(select(Server))).scalars().all()
    tunnels = (await db.execute(select(Tunnel))).scalars().all()
    traffic = {
        row[0]: int(row[1] or 0)
        for row in (
            await db.execute(
                select(
                    TrafficRecord.scope_id,
                    func.sum(TrafficRecord.bytes_rx + TrafficRecord.bytes_tx),
                )
                .where(TrafficRecord.scope == "tunnel", TrafficRecord.period == "day")
                .group_by(TrafficRecord.scope_id)
            )
        ).all()
    }
    counts: dict[str, int] = {}
    for tunnel in tunnels:
        counts[tunnel.source_server_id] = counts.get(tunnel.source_server_id, 0) + 1
        counts[tunnel.destination_server_id] = counts.get(tunnel.destination_server_id, 0) + 1
    nodes = [
        TopologyNode(
            id=s.id,
            label=s.name,
            country=s.country,
            status=s.status,
            health_score=s.health_score,
            tunnels=counts.get(s.id, 0),
        )
        for s in servers
    ]
    edges = [
        TopologyEdge(
            id=t.id,
            source=t.source_server_id,
            target=t.destination_server_id,
            label=t.name,
            type_key=t.type_key,
            health=t.health,
            state=t.state,
            latency_ms=t.latency_ms,
            bytes_total=traffic.get(t.id, 0),
        )
        for t in tunnels
    ]
    return TopologyOut(nodes=nodes, edges=edges)


@router.get("/tunnels/{tunnel_id}/events")
async def tunnel_events(
    tunnel_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TUNNELS_READ.value)),
):
    rows = (
        await db.execute(
            select(Event)
            .where(Event.target_type == "tunnel", Event.target_id == tunnel_id)
            .order_by(Event.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "title": r.title,
            "detail": r.detail,
            "severity": r.severity,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/tunnels/{tunnel_id}/health")
async def tunnel_health(
    tunnel_id: str,
    db: AsyncSession = Depends(get_db),
    _: Principal = Depends(require(Perm.TUNNELS_READ.value)),
):
    tunnel = await db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise NotFound("تونل یافت نشد.")
    outputs = await deploy_service.run_action(db, tunnel, "health")
    tunnel.last_health_at = datetime.now(timezone.utc)
    await db.flush()
    return {"health": tunnel.health, "outputs": outputs}
