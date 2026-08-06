from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, EmailStr, Field, model_validator


class EmailConfig(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    username: str
    password: str
    from_address: EmailStr
    to_addresses: list[EmailStr]
    use_tls: bool = True


class NotificationConfig(BaseModel):
    email: Optional[EmailConfig] = None


class BookingStep(BaseModel):
    label: str
    value: str


class DoctorConfig(BaseModel):
    name: str
    profile_slug: str
    insurance: Literal["public", "private"] = "public"
    booking_steps: list[BookingStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_at_least_one_step(self) -> "DoctorConfig":
        if not self.booking_steps:
            raise ValueError(f"Doctor '{self.name}' must have at least one booking_step")
        return self


class AppConfig(BaseModel):
    doctors: list[DoctorConfig]
    notification: NotificationConfig
    check_interval_seconds: int = 300
    availability_limit: int = 5

    @model_validator(mode="after")
    def require_at_least_one_doctor(self) -> "AppConfig":
        if not self.doctors:
            raise ValueError("At least one doctor must be configured")
        return self


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return AppConfig.model_validate(raw)
