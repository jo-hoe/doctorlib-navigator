from app.config import NotificationConfig
from app.notification.email_notifier import EmailNotifier
from app.notification.notifier import Notifier


def create_notifier(config: NotificationConfig) -> Notifier:
    if config.email is not None:
        return EmailNotifier(config.email)
    raise ValueError("No notification channel configured")


__all__ = ["Notifier", "EmailNotifier", "create_notifier"]
