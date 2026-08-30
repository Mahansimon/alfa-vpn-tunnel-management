"""CLI پنل: alfa

نمونه‌ها:
    alfa status
    alfa server list
    alfa tunnel list
    alfa logs --lines 50
    alfa create-admin --username admin
    alfa backup create
"""
from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from app.core.config import APP_VERSION, settings
from app.db.models.monitoring import Notification
from app.db.models.ops import LogEntry
from app.db.models.server import Server
from app.db.models.tunnel import Tunnel
from app.db.session import SessionLocal
from app.services import backup_service, bootstrap, health_service, traffic_service

cli = typer.Typer(help="ابزار خط فرمان Alfa VpnTunnel Managment", no_args_is_help=True)
server_app = typer.Typer(help="مدیریت سرورها")
tunnel_app = typer.Typer(help="مدیریت تونل‌ها")
backup_app = typer.Typer(help="پشتیبان‌گیری")
cli.add_typer(server_app, name="server")
cli.add_typer(tunnel_app, name="tunnel")
cli.add_typer(backup_app, name="backup")
console = Console()


def run(coro):
    return asyncio.run(coro)


@cli.command()
def status():
    """وضعیت کلی پنل."""

    async def _run():
        async with SessionLocal() as db:
            data = await health_service.overview(db)
            servers = (await db.execute(select(func.count()).select_from(Server))).scalar() or 0
            tunnels = (await db.execute(select(func.count()).select_from(Tunnel))).scalar() or 0
            unread = (
                await db.execute(
                    select(func.count()).select_from(Notification).where(Notification.read.is_(False))
                )
            ).scalar() or 0
            traffic = await traffic_service.summary(db, "server", None, "today")
        table = Table(title=f"Alfa VpnTunnel Managment {APP_VERSION} ({settings.ENVIRONMENT})")
        table.add_column("مورد")
        table.add_column("مقدار")
        table.add_row("وضعیت کلی", data["status"])
        table.add_row("سرورها", str(servers))
        table.add_row("تونل‌ها", str(tunnels))
        table.add_row("اعلان خوانده‌نشده", str(unread))
        table.add_row("ترافیک امروز", traffic_service.human_bytes(traffic["bytes_total"]))
        for component in data["components"]:
            table.add_row(component["name"], f"{component['status']} · {component['detail']}")
        console.print(table)

    run(_run())


@server_app.command("list")
def server_list():
    """لیست سرورها."""

    async def _run():
        async with SessionLocal() as db:
            rows = (await db.execute(select(Server).order_by(Server.name))).scalars().all()
        table = Table(title="سرورها")
        for column in ("نام", "IP", "کشور", "وضعیت", "سلامت", "Agent"):
            table.add_column(column)
        for row in rows:
            table.add_row(
                row.name,
                row.ip_address,
                row.country or "-",
                row.status,
                f"{row.health_score:.0f}",
                (row.agent.version if row.agent and row.agent.enrolled else "نصب‌نشده"),
            )
        console.print(table)

    run(_run())


@tunnel_app.command("list")
def tunnel_list():
    """لیست تونل‌ها."""

    async def _run():
        async with SessionLocal() as db:
            rows = (await db.execute(select(Tunnel).order_by(Tunnel.name))).scalars().all()
            names = {s.id: s.name for s in (await db.execute(select(Server))).scalars()}
        table = Table(title="تونل‌ها")
        for column in ("نام", "نوع", "مبدأ", "مقصد", "وضعیت", "سلامت", "تأخیر"):
            table.add_column(column)
        for row in rows:
            table.add_row(
                row.name,
                row.type_key,
                names.get(row.source_server_id, "?"),
                names.get(row.destination_server_id, "?"),
                row.state,
                row.health,
                f"{row.latency_ms:.0f} ms" if row.latency_ms else "-",
            )
        console.print(table)

    run(_run())


@cli.command()
def logs(lines: int = typer.Option(50, help="تعداد خطوط"), source: str = typer.Option("", help="منبع لاگ")):
    """آخرین لاگ‌های ثبت‌شده در پنل."""

    async def _run():
        async with SessionLocal() as db:
            query = select(LogEntry).order_by(LogEntry.ts.desc()).limit(lines)
            if source:
                query = query.where(LogEntry.source == source)
            rows = (await db.execute(query)).scalars().all()
        for row in reversed(rows):
            console.print(f"[dim]{row.ts:%Y-%m-%d %H:%M:%S}[/dim] [{row.level}] ({row.source}) {row.message}")

    run(_run())


@cli.command("create-admin")
def create_admin(username: str = typer.Option("admin", help="نام کاربری مدیر")):
    """ساخت کاربر مدیر با پسورد تصادفی امن (فقط اگر هیچ کاربری وجود نداشته باشد)."""

    async def _run():
        async with SessionLocal() as db:
            user, password = await bootstrap.ensure_admin(db, username)
            await db.commit()
        if password:
            console.print("[bold green]کاربر مدیر ساخته شد[/bold green]")
            console.print(f"username: {user.username}")
            console.print(f"password: {password}")
        else:
            console.print("[yellow]کاربر از قبل وجود دارد؛ پسورد جدیدی ساخته نشد.[/yellow]")

    run(_run())


@cli.command("init")
def init():
    """آماده‌سازی اولیه دیتابیس (نقش‌ها، تنظیمات، انواع تونل) و ساخت مدیر."""

    async def _run():
        async with SessionLocal() as db:
            password = await bootstrap.run(db, create_admin=True)
        if password:
            console.print("[bold green]نصب اولیه انجام شد[/bold green]")
            console.print(f"username: admin\npassword: {password}")
        else:
            console.print("[green]آماده‌سازی انجام شد.[/green]")

    run(_run())


@backup_app.command("create")
def backup_create(kind: str = typer.Option("full", help="full | database | config")):
    """ساخت فایل پشتیبان."""

    async def _run():
        async with SessionLocal() as db:
            row = await backup_service.create_backup(db, kind, "از طریق CLI")
            await db.commit()
        console.print(f"[green]پشتیبان ساخته شد:[/green] {row.path}")

    run(_run())


@backup_app.command("list")
def backup_list():
    """لیست پشتیبان‌ها."""

    async def _run():
        from app.db.models.ops import Backup

        async with SessionLocal() as db:
            rows = (await db.execute(select(Backup).order_by(Backup.created_at.desc()))).scalars().all()
        table = Table(title="پشتیبان‌ها")
        for column in ("فایل", "نوع", "حجم", "تاریخ"):
            table.add_column(column)
        for row in rows:
            table.add_row(
                row.filename,
                row.kind,
                traffic_service.human_bytes(row.size_bytes),
                f"{row.created_at:%Y-%m-%d %H:%M}",
            )
        console.print(table)

    run(_run())


if __name__ == "__main__":
    cli()
