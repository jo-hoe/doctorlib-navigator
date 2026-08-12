import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

from app.config import DateWindow, DoctorConfig
from app.doctolib.client import DoctolibAPIError, DoctolibClient
from app.doctolib.models import AvailabilityResult, ProfileInfo, day_in_any_window
from app.notification.notifier import Notifier
from app.state.store import InMemoryStateStore, StateStore, sanitise_key

logger = logging.getLogger(__name__)

_VISIT_MOTIVE_LABEL = "visit_motive"
_NOTIFICATION_SLOTS_LIMIT = 10


@dataclass(frozen=True)
class CheckResult:
    doctor_name: str
    has_slots: bool
    result: AvailabilityResult


class AppointmentChecker:
    def __init__(
        self,
        client: DoctolibClient,
        notifier: Notifier,
        state: Optional[StateStore] = None,
    ) -> None:
        self._client = client
        self._notifier = notifier
        self._state: StateStore = state or InMemoryStateStore()

    def check_all(self, doctors: list[DoctorConfig]) -> list[CheckResult]:
        results = []
        failures = 0
        for doctor in doctors:
            try:
                result = self._check_doctor(doctor)
            except (httpx.HTTPStatusError, httpx.RequestError, DoctolibAPIError, ValueError) as exc:
                failures += 1
                self._log_check_failure(doctor, exc)
                continue
            results.append(result)
            self._notify_if_changed(doctor, result)
        if doctors and failures == len(doctors):
            raise RuntimeError(
                f"All {failures} doctor check(s) failed; see logs for details"
            )
        return results

    def _log_check_failure(self, doctor: DoctorConfig, exc: Exception) -> None:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 410:
            logger.warning(
                "%s: profile not found (HTTP 410) — check profile_slug '%s'",
                doctor.name,
                doctor.profile_slug,
            )
        else:
            logger.warning("%s: check failed — %s", doctor.name, exc)

    def _notify_if_changed(self, doctor: DoctorConfig, result: CheckResult) -> None:
        key = sanitise_key(doctor.name)
        current = frozenset(
            slot.start_date
            for day in result.result.availabilities
            for slot in day.slots
        )
        stored = self._state.load(key)
        if current == stored:
            logger.debug("%s: slots unchanged, skipping notification", doctor.name)
            return
        self._send_notification(result)
        self._state.save(key, current)

    def _check_doctor(self, doctor: DoctorConfig) -> CheckResult:
        logger.info("Checking appointments for %s", doctor.name)
        profile = self._client.fetch_profile_info(doctor.profile_slug)
        motive_id, agenda_ids, practice_ids = _resolve_booking_params(doctor, profile)
        api_start = _earliest_start(doctor.windows)
        # Query each agenda individually and merge, rather than sending all agenda_ids
        # in one request. Doctolib "poisons" a multi-agenda request: if ANY agenda in
        # the set is closed for online booking it returns reason=not_opened_availability
        # with next_slot=null for the WHOLE response, masking the agendas that do have
        # slots. info.json is no help for pre-filtering — it marks every agenda
        # online_booking_status=enabled_for_all even when the availabilities layer
        # reports them closed. The website avoids this by requesting one agenda at a
        # time (confirmed via HAR); ssn_draft_info.json is just a 204 session-primer,
        # not an agenda selector. So we scan per agenda and union the results.
        per_agenda = [
            self._scan_agenda(doctor, motive_id, agenda, practice_ids, api_start)
            for agenda in agenda_ids
        ]
        result = AvailabilityResult.merge(per_agenda)
        window_desc = _window_description(doctor.windows)
        logger.info(
            "%s: %d slot(s) within window(s) %s",
            doctor.name,
            result.total,
            window_desc,
        )
        return CheckResult(doctor_name=doctor.name, has_slots=result.has_slots, result=result)

    def _scan_agenda(
        self,
        doctor: DoctorConfig,
        motive_id: int,
        agenda_id: int,
        practice_ids: list[int],
        start_date: Optional[date],
    ) -> AvailabilityResult:
        result = self._fetch_filtered(
            doctor, motive_id, [agenda_id], practice_ids, start_date=start_date
        )
        # Doctolib's `limit` is a days-forward window, not a slot count. When the
        # scanned window is empty it still reports the first later availability via
        # `next_slot`; re-query around that date to fetch the concrete slots.
        if result.total == 0 and result.next_slot:
            result = self._probe_next_slot(
                doctor, motive_id, [agenda_id], practice_ids, result
            )
        return result

    def _fetch_filtered(
        self,
        doctor: DoctorConfig,
        motive_id: int,
        agenda_ids: list[int],
        practice_ids: list[int],
        start_date: Optional[date],
    ) -> AvailabilityResult:
        result = self._client.fetch_availabilities(
            visit_motive_id=motive_id,
            agenda_ids=agenda_ids,
            practice_ids=practice_ids,
            insurance_sector=doctor.insurance,
            start_date=start_date,
        )
        return result.with_date_filter(windows=doctor.windows, logger=logger)

    def _probe_next_slot(
        self,
        doctor: DoctorConfig,
        motive_id: int,
        agenda_ids: list[int],
        practice_ids: list[int],
        result: AvailabilityResult,
    ) -> AvailabilityResult:
        assert result.next_slot is not None
        try:
            next_date = date.fromisoformat(result.next_slot[:10])
        except ValueError:
            logger.debug("%s: unparseable next_slot %r", doctor.name, result.next_slot)
            return result
        if not day_in_any_window(next_date, doctor.windows):
            logger.debug(
                "%s: next_slot %s outside all configured windows",
                doctor.name,
                next_date,
            )
            return result
        logger.debug("%s: re-querying availabilities at next_slot %s", doctor.name, next_date)
        return self._fetch_filtered(
            doctor, motive_id, agenda_ids, practice_ids, start_date=next_date
        )

    def _send_notification(self, result: CheckResult) -> None:
        subject = f"Doctolib: Appointment available – {result.doctor_name}"
        slots = [slot for day in result.result.availabilities for slot in day.slots]
        lines = [f"Appointments are now available for {result.doctor_name}!", ""]
        for slot in slots[:_NOTIFICATION_SLOTS_LIMIT]:
            lines.append(f"  • {slot.start_date}")
        if len(slots) > _NOTIFICATION_SLOTS_LIMIT:
            lines.append(f"  … and {len(slots) - _NOTIFICATION_SLOTS_LIMIT} more")
        lines += ["", "Book now: https://www.doctolib.de"]
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
        # Profiles without per-motive insurance configurations expose the
        # motive→agenda mapping on the agendas list instead.
        agenda_ids = profile.agenda_ids_for_motive(motive.id)
    if not agenda_ids:
        raise ValueError(
            f"No enabled agendas for motive '{motive_name}' "
            f"with insurance '{doctor.insurance}'"
        )

    practice_ids = profile.practice_ids()
    return motive.id, agenda_ids, practice_ids


def _get_motive_name(doctor: DoctorConfig) -> str:
    for step in doctor.booking_steps:
        if step.label.lower() == _VISIT_MOTIVE_LABEL:
            return step.value
    raise ValueError(
        f"No booking step with label '{_VISIT_MOTIVE_LABEL}' found for {doctor.name}"
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
