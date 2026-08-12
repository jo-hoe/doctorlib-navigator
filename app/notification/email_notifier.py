import logging
import smtplib
from email.charset import QP, Charset
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import EmailConfig
from app.notification.notifier import Notifier

logger = logging.getLogger(__name__)

# Force quoted-printable (not the stdlib default of base64) for the text body.
# Some relays (observed with Mailjet) fail to decode a base64-encoded text/plain
# part before re-templating the message: they embed the raw base64 as literal
# body text, so the recipient sees an undecoded base64 blob. Quoted-printable
# keeps the body human-readable on the wire, which such relays pass through
# intact, while remaining a standards-compliant transfer encoding.
_UTF8_QP = Charset("utf-8")
_UTF8_QP.body_encoding = QP


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
    message.attach(MIMEText(body, "plain", _UTF8_QP))
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
            message.as_bytes(),
        )
    logger.info("Email sent to %s", config.to_addresses)
