from app.services.notifiers.base import Notifier  # noqa: F401
from app.services.notifiers.email import EmailNotifier
from app.services.notifiers.inapp import InAppNotifier
from app.services.notifiers.telegram import TelegramNotifier
from app.services.notifiers.webhook import WebhookNotifier

CHANNELS: dict[str, Notifier] = {
    InAppNotifier.key: InAppNotifier(),
    EmailNotifier.key: EmailNotifier(),
    TelegramNotifier.key: TelegramNotifier(),
    WebhookNotifier.key: WebhookNotifier(),
}


async def dispatch(db, *, title: str, body: str, severity: str = "info", channels=None, **kw) -> dict:
    """ارسال به کانال‌های خواسته‌شده. خروجی: وضعیت هر کانال."""
    result: dict[str, bool] = {}
    wanted = channels or ["inapp"]
    for key in wanted:
        notifier = CHANNELS.get(key)
        if not notifier:
            continue
        try:
            result[key] = await notifier.send(db, title=title, body=body, severity=severity, **kw)
        except Exception:
            result[key] = False
    return result
