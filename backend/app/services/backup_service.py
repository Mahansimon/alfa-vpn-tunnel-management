"""پشتیبان‌گیری و بازگردانی: دیتابیس + تنظیمات + config تونل‌ها.

فایل پشتیبان یک آرشیو tar.gz است؛ در صورت فعال بودن رمزگذاری، آرشیو با کلید
SECRETS_ENCRYPTION_KEY رمز می‌شود (پسوند .enc) تا Secretهای رمزگذاری‌شده هم
قابل انتقال باشند.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import APP_VERSION, settings
from app.core.crypto import decrypt, encrypt, sha256_file
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models.ops import Backup, Setting
from app.db.models.tunnel import Tunnel, TunnelConfig

log = get_logger("backup")


def _ensure_dir() -> str:
    os.makedirs(settings.BACKUP_DIR, exist_ok=True)
    return settings.BACKUP_DIR


def _pg_dump(target: str) -> None:
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.POSTGRES_PASSWORD
    cmd = [
        "pg_dump",
        "-h",
        settings.POSTGRES_HOST,
        "-p",
        str(settings.POSTGRES_PORT),
        "-U",
        settings.POSTGRES_USER,
        "-d",
        settings.POSTGRES_DB,
        "-F",
        "c",
        "-f",
        target,
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise AppError(f"pg_dump ناموفق بود: {proc.stderr[-500:]}")


def _pg_restore(source: str) -> None:
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.POSTGRES_PASSWORD
    cmd = [
        "pg_restore",
        "-h",
        settings.POSTGRES_HOST,
        "-p",
        str(settings.POSTGRES_PORT),
        "-U",
        settings.POSTGRES_USER,
        "-d",
        settings.POSTGRES_DB,
        "--clean",
        "--if-exists",
        "--no-owner",
        source,
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=3600)
    if proc.returncode not in (0, 1):
        raise AppError(f"pg_restore ناموفق بود: {proc.stderr[-500:]}")


async def _export_json(db: AsyncSession) -> dict:
    tunnels = (await db.execute(select(Tunnel))).scalars().all()
    configs = (await db.execute(select(TunnelConfig).where(TunnelConfig.is_active.is_(True)))).scalars().all()
    rows = (await db.execute(select(Setting))).scalars().all()
    return {
        "panel_version": APP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "settings": [
            {"key": r.key, "value": r.value, "is_secret": r.is_secret, "category": r.category} for r in rows
        ],
        "tunnels": [
            {
                "id": t.id,
                "name": t.name,
                "type_key": t.type_key,
                "source_server_id": t.source_server_id,
                "destination_server_id": t.destination_server_id,
                "tags": t.tags,
            }
            for t in tunnels
        ],
        "tunnel_configs": [
            {"tunnel_id": c.tunnel_id, "revision": c.revision, "payload": c.payload,
             "secrets_enc": c.secrets_enc}
            for c in configs
        ],
    }


async def create_backup(
    db: AsyncSession, kind: str = "full", note: str = "", user_id: str | None = None
) -> Backup:
    directory = _ensure_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    encrypt_enabled = True
    from app.services import settings_service

    encrypt_enabled = bool(await settings_service.get(db, "backup_encrypt", True))
    payload = await _export_json(db)

    with tempfile.TemporaryDirectory() as tmp:
        members: list[str] = []
        meta_path = os.path.join(tmp, "panel-export.json")
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        members.append(meta_path)

        if kind in ("full", "database"):
            dump_path = os.path.join(tmp, "database.dump")
            await asyncio.to_thread(_pg_dump, dump_path)
            members.append(dump_path)

        archive = os.path.join(tmp, f"alfa-backup-{kind}-{stamp}.tar.gz")
        with tarfile.open(archive, "w:gz") as tar:
            for member in members:
                tar.add(member, arcname=os.path.basename(member))

        filename = os.path.basename(archive) + (".enc" if encrypt_enabled else "")
        final_path = os.path.join(directory, filename)
        if encrypt_enabled:
            import base64

            with open(archive, "rb") as fh:
                blob = base64.b64encode(fh.read()).decode()
            with open(final_path, "w", encoding="utf-8") as fh:
                fh.write(encrypt(blob) or "")
        else:
            shutil.copy2(archive, final_path)

    row = Backup(
        filename=filename,
        path=final_path,
        size_bytes=os.path.getsize(final_path),
        kind=kind,
        encrypted=encrypt_enabled,
        checksum=sha256_file(final_path),
        panel_version=APP_VERSION,
        created_by=user_id,
        note=note,
    )
    db.add(row)
    await db.flush()
    await prune(db)
    return row


async def prune(db: AsyncSession) -> int:
    from app.services import settings_service

    keep = int(await settings_service.get(db, "backup_keep", 14) or 14)
    rows = (await db.execute(select(Backup).order_by(Backup.created_at.desc()))).scalars().all()
    removed = 0
    for row in rows[keep:]:
        try:
            if os.path.exists(row.path):
                os.remove(row.path)
        except OSError:
            pass
        await db.delete(row)
        removed += 1
    await db.flush()
    return removed


async def restore_backup(db: AsyncSession, backup: Backup) -> None:
    if not os.path.exists(backup.path):
        raise AppError("فایل پشتیبان روی سرور پیدا نشد.")
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "restore.tar.gz")
        if backup.encrypted:
            import base64

            with open(backup.path, encoding="utf-8") as fh:
                blob = decrypt(fh.read())
            with open(archive, "wb") as fh:
                fh.write(base64.b64decode(blob or ""))
        else:
            shutil.copy2(backup.path, archive)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(tmp, filter="data")
        dump = os.path.join(tmp, "database.dump")
        if os.path.exists(dump):
            await asyncio.to_thread(_pg_restore, dump)
        else:
            raise AppError("این پشتیبان شامل دیتابیس نیست؛ فقط برای مرجع تنظیمات قابل استفاده است.")
