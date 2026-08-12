import logging
import random
import time
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

import httpx
import ua_generator

from app.doctolib.models import (
    Agenda,
    AgendaConfiguration,
    AvailabilityDay,
    AvailabilityResult,
    Place,
    ProfileInfo,
    Slot,
    VisitMotive,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.doctolib.de"

_KEY_VISIT_MOTIVE_IDS = "visit_motive_ids"
_KEY_PRACTICE_IDS = "practice_ids"
_KEY_AGENDA_ID = "agenda_id"
_KEY_PRACTICE_ID = "practice_id"
_KEY_ID = "id"
_KEY_NAME = "name"
_KEY_NEXT_SLOT = "next_slot"

_MAX_ATTEMPTS = 3
_BACKOFF_BASE_SECONDS = 1.0


class DoctolibAPIError(Exception):
    """Raised when Doctolib returns an error-shaped payload instead of the expected data."""


def _get_with_retry(
    http: httpx.Client,
    url: str,
    params: dict[str, object],
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    last_exc: Optional[Exception] = None
    last_response: Optional[httpx.Response] = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = http.get(url, params=params)
        except httpx.RequestError as exc:
            last_exc = exc
            last_response = None
            logger.warning("Request error (attempt %d/%d): %s", attempt, _MAX_ATTEMPTS, exc)
        else:
            if response.status_code != 429 and response.status_code < 500:
                return response
            last_exc = None
            last_response = response
            logger.warning(
                "Retryable status %d (attempt %d/%d)",
                response.status_code,
                attempt,
                _MAX_ATTEMPTS,
            )
        if attempt < _MAX_ATTEMPTS:
            sleep(_retry_delay(attempt, last_response))
    if last_exc is not None:
        raise last_exc
    # Exhausted retries on a retryable status — return it so raise_for_status surfaces it.
    assert last_response is not None
    return last_response


def _retry_delay(attempt: int, response: Optional[httpx.Response]) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            return float(retry_after)
    return _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 0.5)


@dataclass(frozen=True)
class DoctolibClient:
    _http: httpx.Client

    def fetch_profile_info(self, profile_slug: str) -> ProfileInfo:
        url = _BASE_URL + "/online_booking/api/slot_selection_funnel/v1/info.json"
        logger.debug("Fetching profile info for slug=%s", profile_slug)
        response = _get_with_retry(
            self._http, url, {"profile_slug": profile_slug, "locale": "de"}
        )
        response.raise_for_status()
        logger.debug("Profile info response: %d bytes", len(response.content))
        return _parse_profile_info(response.json())

    def fetch_availabilities(
        self,
        visit_motive_id: int,
        agenda_ids: list[int],
        practice_ids: list[int],
        insurance_sector: str,
        start_date: Optional[date] = None,
        limit: int = 5,
    ) -> AvailabilityResult:
        # NOTE: `limit` is a days-forward window, NOT a slot count. limit=5 scans only
        # the 5 days from start_date. When that window is empty the response carries a
        # `next_slot` datetime pointing at the first later availability — re-query with
        # start_date=next_slot to fetch the concrete slots (see AppointmentChecker).
        if start_date is None:
            start_date = date.today()

        params = {
            _KEY_VISIT_MOTIVE_IDS: visit_motive_id,
            "agenda_ids": agenda_ids,
            _KEY_PRACTICE_IDS: practice_ids,
            "insurance_sector": insurance_sector,
            "telehealth": "false",
            "start_date": start_date.isoformat(),
            "limit": max(1, limit),
        }
        url = _BASE_URL + "/availabilities.json"
        logger.debug("Fetching availabilities: motive=%d start=%s", visit_motive_id, start_date)
        response = _get_with_retry(self._http, url, params)
        response.raise_for_status()
        result = _parse_availability_result(response.json())
        logger.debug("Availabilities response: total=%d", result.total)
        return result


def create_client(timeout: float = 30.0) -> DoctolibClient:
    ua = ua_generator.generate(
        device="desktop",
        browser=("chrome", "firefox"),
        platform=("windows", "macos", "linux"),
    )
    headers = {
        **ua.headers.get(),
        "Accept": "application/json",
        "Referer": _BASE_URL + "/",
    }
    logger.debug("Using User-Agent: %s", ua.text)
    http = httpx.Client(headers=headers, timeout=timeout, follow_redirects=True)
    return DoctolibClient(http)


def _parse_profile_info(data: dict[str, object]) -> ProfileInfo:
    _raise_if_error(data)
    raw = data.get("data", data)
    assert isinstance(raw, dict)
    motives = [_parse_visit_motive(m) for m in raw.get("visit_motives", [])]  # type: ignore[union-attr]
    agendas = [_parse_agenda(a) for a in raw.get("agendas", [])]  # type: ignore[union-attr]
    places = [_parse_place(p) for p in raw.get("places", [])]  # type: ignore[union-attr]
    specialities = raw.get("specialities") or []
    speciality_slug: Optional[str] = specialities[0]["slug"] if specialities else None  # type: ignore[index]
    speciality_id: Optional[int] = specialities[0]["id"] if specialities else None  # type: ignore[index]
    return ProfileInfo(visit_motives=motives, agendas=agendas, places=places, speciality_slug=speciality_slug, speciality_id=speciality_id)


def _parse_visit_motive(raw: dict[str, object]) -> VisitMotive:
    configs = [
        _parse_agenda_configuration(c)
        for c in (raw.get("configurations") or [])
    ]
    return VisitMotive(id=raw[_KEY_ID], name=raw[_KEY_NAME], configurations=configs)  # type: ignore[arg-type]


def _parse_agenda_configuration(raw: dict[str, object]) -> AgendaConfiguration:
    return AgendaConfiguration(
        insurance=raw["insurance"],  # type: ignore[arg-type]
        agenda_id=raw.get(_KEY_AGENDA_ID),  # type: ignore[arg-type]
        online_booking_status=raw.get("online_booking_status"),  # type: ignore[arg-type]
        disabled=raw.get("disabled"),  # type: ignore[arg-type]
    )


def _parse_agenda(raw: dict[str, object]) -> Agenda:
    return Agenda(
        id=raw[_KEY_ID],  # type: ignore[arg-type]
        practice_id=raw[_KEY_PRACTICE_ID],  # type: ignore[arg-type]
        visit_motive_ids=raw.get(_KEY_VISIT_MOTIVE_IDS, []),  # type: ignore[arg-type]
    )


def _parse_place(raw: dict[str, object]) -> Place:
    return Place(
        id=raw[_KEY_ID],  # type: ignore[arg-type]
        name=raw[_KEY_NAME],  # type: ignore[arg-type]
        practice_ids=raw.get(_KEY_PRACTICE_IDS, []),  # type: ignore[arg-type]
        slug=raw.get("slug"),  # type: ignore[arg-type]
    )


def _parse_availability_result(raw: dict[str, object]) -> AvailabilityResult:
    _raise_if_error(raw)
    if "availabilities" not in raw:
        raise DoctolibAPIError(f"Unexpected availabilities response: {raw}")
    days = [_parse_availability_day(d) for d in raw.get("availabilities", [])]  # type: ignore[union-attr]
    return AvailabilityResult(
        availabilities=days,
        total=raw.get("total", 0),  # type: ignore[arg-type]
        reason=raw.get("reason"),  # type: ignore[arg-type]
        message=raw.get("message"),  # type: ignore[arg-type]
        next_slot=raw.get(_KEY_NEXT_SLOT),  # type: ignore[arg-type]
    )


def _raise_if_error(raw: dict[str, object]) -> None:
    for key in ("error", "errors", "status"):
        if key in raw:
            raise DoctolibAPIError(f"Doctolib API error response: {raw}")


def _parse_availability_day(raw: dict[str, object]) -> AvailabilityDay:
    slots = [_parse_slot(s) for s in raw.get("slots", [])]  # type: ignore[union-attr]
    return AvailabilityDay(date=raw["date"], slots=slots)  # type: ignore[arg-type]


def _parse_slot(raw: object) -> Slot:
    # Doctolib returns slots either as plain ISO datetime strings (most profiles)
    # or as objects with start/end/agenda/practice fields.
    if isinstance(raw, str):
        return Slot(start_date=raw)
    assert isinstance(raw, dict)
    return Slot(
        start_date=raw["start_date"],  # type: ignore[arg-type]
        end_date=raw.get("end_date"),  # type: ignore[arg-type]
        agenda_id=raw.get(_KEY_AGENDA_ID),  # type: ignore[arg-type]
        practice_id=raw.get(_KEY_PRACTICE_ID),  # type: ignore[arg-type]
    )
