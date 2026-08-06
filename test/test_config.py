import pytest
from pydantic import ValidationError

from app.config import AppConfig, BookingStep, DoctorConfig, EmailConfig, NotificationConfig


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
