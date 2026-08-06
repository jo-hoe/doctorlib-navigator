import smtplib
from email.mime.multipart import MIMEMultipart
from unittest.mock import MagicMock, patch

import pytest

from app.config import EmailConfig
from app.notification.email_notifier import EmailNotifier, _build_message


def _make_email_config(**kwargs) -> EmailConfig:
    base = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "username": "user",
        "password": "secret",
        "from_address": "from@example.com",
        "to_addresses": ["to@example.com"],
        "use_tls": True,
    }
    base.update(kwargs)
    return EmailConfig.model_validate(base)


def test_build_message_sets_headers():
    config = _make_email_config()
    msg = _build_message(config, "Test Subject", "Test Body")
    assert msg["Subject"] == "Test Subject"
    assert msg["From"] == "from@example.com"
    assert "to@example.com" in msg["To"]


def test_build_message_multiple_recipients():
    config = _make_email_config(to_addresses=["a@example.com", "b@example.com"])
    msg = _build_message(config, "Subject", "Body")
    assert "a@example.com" in msg["To"]
    assert "b@example.com" in msg["To"]


def test_notify_sends_via_smtp():
    config = _make_email_config()
    notifier = EmailNotifier(config)

    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp

        notifier.notify("Subject", "Body")

        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user", "secret")
        mock_smtp.sendmail.assert_called_once()
        from_arg, to_arg, _ = mock_smtp.sendmail.call_args[0]
        assert from_arg == "from@example.com"
        assert to_arg == ["to@example.com"]


def test_notify_no_tls_skips_starttls():
    config = _make_email_config(use_tls=False)
    notifier = EmailNotifier(config)

    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp
        notifier.notify("Subject", "Body")
        mock_smtp.starttls.assert_not_called()
