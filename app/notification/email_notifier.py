import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import EmailConfig
from app.notification.notifier import Notifier


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
    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        if config.use_tls:
            server.starttls()
        server.login(config.username, config.password)
        server.sendmail(
            config.from_address,
            config.to_addresses,
            message.as_string(),
        )
