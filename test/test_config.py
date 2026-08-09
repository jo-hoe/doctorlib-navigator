import pytest
from pydantic import ValidationError

from app.config import AppConfig, BookingStep, DateWindow, DoctorConfig, EmailConfig, NotificationConfig


def _make_doctor(**kwargs) -> dict:
    base = {
        "name": "Test Doctor",
        "profile_slug": "test-doctor",
        "insurance": "public",
        "booking_steps": [{"label": "visit_motive", "value": "Erstuntersuchung / Folgeuntersuchung"}],
    }
    base.update(kwargs)
    return base


def _make_notification() -> dict:
    return {
        "email": {
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "username": "user",
            "password": "secret",
            "from_address": "from@example.com",
            "to_addresses": ["to@example.com"],
            "use_tls": True,
        }
    }


def test_valid_config_parses():
    config = AppConfig.model_validate(
        {"doctors": [_make_doctor()], "notification": _make_notification()}
    )
    assert len(config.doctors) == 1
    assert config.doctors[0].insurance == "public"
    assert config.check_interval_seconds == 300


def test_doctor_requires_booking_steps():
    with pytest.raises(ValidationError, match="booking_step"):
        DoctorConfig.model_validate(_make_doctor(booking_steps=[]))


def test_config_requires_at_least_one_doctor():
    with pytest.raises(ValidationError, match="doctor"):
        AppConfig.model_validate({"doctors": [], "notification": _make_notification()})


def test_invalid_insurance_rejected():
    with pytest.raises(ValidationError):
        DoctorConfig.model_validate(_make_doctor(insurance="unknown"))


def test_defaults():
    config = AppConfig.model_validate(
        {"doctors": [_make_doctor()], "notification": _make_notification()}
    )
    assert config.availability_limit == 5
    assert config.check_interval_seconds == 300


def test_email_config_invalid_address():
    with pytest.raises(ValidationError):
        EmailConfig.model_validate(
            {
                "smtp_host": "smtp.example.com",
                "username": "user",
                "password": "secret",
                "from_address": "not-an-email",
                "to_addresses": ["to@example.com"],
            }
        )


def test_notification_config_no_channel():
    config = NotificationConfig.model_validate({})
    assert config.email is None


def test_email_config_env_vars_override_credentials(monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "env-user")
    monkeypatch.setenv("SMTP_PASSWORD", "env-secret")
    config = EmailConfig.model_validate(
        {
            "smtp_host": "smtp.example.com",
            "username": "file-user",
            "password": "file-secret",
            "from_address": "from@example.com",
            "to_addresses": ["to@example.com"],
        }
    )
    assert config.username == "env-user"
    assert config.password.get_secret_value() == "env-secret"


def test_email_config_file_credentials_used_when_no_env_vars(monkeypatch):
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    config = EmailConfig.model_validate(
        {
            "smtp_host": "smtp.example.com",
            "username": "file-user",
            "password": "file-secret",
            "from_address": "from@example.com",
            "to_addresses": ["to@example.com"],
        }
    )
    assert config.username == "file-user"
    assert config.password.get_secret_value() == "file-secret"


# --- DateWindow edge cases ---

def test_email_config_missing_credentials_rejected(monkeypatch):
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    with pytest.raises(ValidationError, match="username and password"):
        EmailConfig.model_validate(
            {
                "smtp_host": "smtp.example.com",
                "from_address": "from@example.com",
                "to_addresses": ["to@example.com"],
            }
        )


def test_date_window_only_end_date():
    w = DateWindow.model_validate({"end_date": "2026-08-28"})
    assert w.start_date is None
    assert str(w.end_date) == "2026-08-28"


def test_date_window_only_start_date():
    w = DateWindow.model_validate({"start_date": "2026-08-01"})
    assert w.end_date is None


def test_date_window_both_dates_valid():
    w = DateWindow.model_validate({"start_date": "2026-08-01", "end_date": "2026-08-28"})
    assert w.start_date < w.end_date


def test_date_window_same_start_and_end():
    w = DateWindow.model_validate({"start_date": "2026-08-10", "end_date": "2026-08-10"})
    assert w.start_date == w.end_date


def test_date_window_end_before_start_rejected():
    with pytest.raises(ValidationError, match="end_date"):
        DateWindow.model_validate({"start_date": "2026-08-28", "end_date": "2026-08-01"})


def test_date_window_empty_is_valid():
    w = DateWindow.model_validate({})
    assert w.start_date is None
    assert w.end_date is None


def test_doctor_config_multiple_windows():
    config = DoctorConfig.model_validate(_make_doctor(windows=[
        {"end_date": "2026-08-28"},
        {"start_date": "2026-11-01", "end_date": "2026-11-07"},
    ]))
    assert len(config.windows) == 2


def test_doctor_config_no_windows_defaults_empty():
    config = DoctorConfig.model_validate(_make_doctor())
    assert config.windows == []

