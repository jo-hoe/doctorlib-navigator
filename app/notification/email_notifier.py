import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import EmailConfig
from app.notification.notifier import Notifier

logger = logging.getLogger(__name__)


class EmailNotifier(Notifier):
    def __init__(self, config: EmailConfig) -> None:
        self._config = config

    def notify(self, subject: str, body: str) -> None:
        message = _build_message(self._config, subject, body)
        _send(self._config, message)


def _build_message(config: EmailConfig, subject: str, body: str) -> MIMEMultipart:
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = config.from_address
    message["To"] = ", ".join(config.to_addresses)
    message.attach(MIMEText(body, "plain", "utf-8"))
    return message


def _send(config: EmailConfig, message: MIMEMultipart) -> None:
    logger.debug("Connecting to SMTP %s:%d (tls=%s)", config.smtp_host, config.smtp_port, config.use_tls)
    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        if config.use_tls:
            server.starttls()
        if config.username:
            server.login(config.username, config.password.get_secret_value())
        server.sendmail(
            config.from_address,
            config.to_addresses,
            message.as_string(),
        )
    logger.info("Email sent to %s", config.to_addresses)
