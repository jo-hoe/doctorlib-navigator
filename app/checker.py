import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.config import DateWindow, DoctorConfig
from app.doctolib.client import DoctolibClient
from app.doctolib.models import AvailabilityResult, ProfileInfo
from app.notification.notifier import Notifier

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckResult:
    doctor_name: str
    has_slots: bool
    result: AvailabilityResult


class AppointmentChecker:
    def __init__(self, client: DoctolibClient, notifier: Notifier) -> None:
        self._client = client
        self._notifier = notifier

    def check_all(self, doctors: list[DoctorConfig]) -> list[CheckResult]:
        results = []
        for doctor in doctors:
            result = self._check_doctor(doctor)
            results.append(result)
            if result.has_slots:
                self._send_notification(result)
        return results

    def _check_doctor(self, doctor: DoctorConfig) -> CheckResult:
        logger.info("Checking appointments for %s", doctor.name)
        profile = self._client.fetch_profile_info(doctor.profile_slug)
        motive_id, agenda_ids, practice_ids = _resolve_booking_params(doctor, profile)
        api_start = _earliest_start(doctor.windows)
        result = self._client.fetch_availabilities(
            visit_motive_id=motive_id,
            agenda_ids=agenda_ids,
            practice_ids=practice_ids,
            insurance_sector=doctor.insurance,
            start_date=api_start,
        )
        result = result.with_date_filter(windows=doctor.windows, logger=logger)
        window_desc = _window_description(doctor.windows)
        logger.info(
            "%s: %d slot(s) within window(s) %s",
            doctor.name,
            result.total,
            window_desc,
        )
        return CheckResult(doctor_name=doctor.name, has_slots=result.has_slots, result=result)

    def _send_notification(self, result: CheckResult) -> None:
        subject = f"Doctolib: Appointment available – {result.doctor_name}"
        slots = [
            slot
            for day in result.result.availabilities
            for slot in day.slots
        ]
        lines = [f"Appointments are now available for {result.doctor_name}!", ""]
        for slot in slots[:10]:
            lines.append(f"  • {slot.start_date}")
        if len(slots) > 10:
            lines.append(f"  … and {len(slots) - 10} more")
        lines += [
            "",
            "Book now: https://www.doctolib.de",
        ]
        self._notifier.notify(subject=subject, body="\n".join(lines))


def _resolve_booking_params(
    doctor: DoctorConfig, profile: ProfileInfo
) -> tuple[int, list[int], list[int]]:
    motive_name = _get_motive_name(doctor)
    motive = profile.find_motive_by_name(motive_name)
    if motive is None:
        available = [m.name for m in profile.visit_motives]
        raise ValueError(
            f"Visit motive '{motive_name}' not found for {doctor.name}. "
            f"Available: {available}"
        )

    agenda_ids = motive.agenda_ids_for_insurance(doctor.insurance)
    if not agenda_ids:
        raise ValueError(
            f"No enabled agendas for motive '{motive_name}' "
            f"with insurance '{doctor.insurance}'"
        )

    practice_ids = profile.practice_ids()
    return motive.id, agenda_ids, practice_ids


def _get_motive_name(doctor: DoctorConfig) -> str:
    for step in doctor.booking_steps:
        if step.label.lower() == "visit_motive":
            return step.value
    raise ValueError(
        f"No booking step with label 'visit_motive' found for {doctor.name}"
    )


def _earliest_start(windows: list[DateWindow]) -> Optional[date]:
    starts = [w.start_date for w in windows if w.start_date is not None]
    return min(starts) if starts else None


def _window_description(windows: list[DateWindow]) -> str:
    if not windows:
        return "unrestricted"
    parts = []
    for w in windows:
        start = w.start_date.isoformat() if w.start_date else "today"
        end = w.end_date.isoformat() if w.end_date else "∞"
        parts.append(f"[{start} – {end}]")
    return ", ".join(parts)
