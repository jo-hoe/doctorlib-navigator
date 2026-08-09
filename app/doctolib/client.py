import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

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
_PROFILE_INFO_PATH = "/online_booking/api/slot_selection_funnel/v1/info.json"
_AVAILABILITIES_PATH = "/availabilities.json"
_LOCALE = "de"
_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Referer": _BASE_URL + "/",
}

_KEY_PROFILE_SLUG = "profile_slug"
_KEY_LOCALE = "locale"
_KEY_VISIT_MOTIVE_IDS = "visit_motive_ids"
_KEY_AGENDA_IDS = "agenda_ids"
_KEY_PRACTICE_IDS = "practice_ids"
_KEY_INSURANCE_SECTOR = "insurance_sector"
_KEY_TELEHEALTH = "telehealth"
_KEY_START_DATE = "start_date"
_KEY_LIMIT = "limit"
_KEY_DATA = "data"
_KEY_VISIT_MOTIVES = "visit_motives"
_KEY_AGENDAS = "agendas"
_KEY_PLACES = "places"
_KEY_CONFIGURATIONS = "configurations"
_KEY_AVAILABILITIES = "availabilities"
_KEY_TOTAL = "total"
_KEY_REASON = "reason"
_KEY_MESSAGE = "message"
_KEY_SLOTS = "slots"
_KEY_INSURANCE = "insurance"
_KEY_AGENDA_ID = "agenda_id"
_KEY_ONLINE_BOOKING_STATUS = "online_booking_status"
_KEY_DISABLED = "disabled"
_KEY_PRACTICE_ID = "practice_id"
_KEY_ID = "id"
_KEY_NAME = "name"
_KEY_DATE = "date"
_KEY_START_DATE_SLOT = "start_date"
_KEY_END_DATE = "end_date"


@dataclass(frozen=True)
class DoctolibClient:
    _http: httpx.Client

    def fetch_profile_info(self, profile_slug: str) -> ProfileInfo:
        url = _BASE_URL + _PROFILE_INFO_PATH
        logger.debug("Fetching profile info for slug=%s", profile_slug)
        response = self._http.get(url, params={_KEY_PROFILE_SLUG: profile_slug, _KEY_LOCALE: _LOCALE})
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
        if start_date is None:
            start_date = date.today()

        params = {
            _KEY_VISIT_MOTIVE_IDS: visit_motive_id,
            _KEY_AGENDA_IDS: agenda_ids,
            _KEY_PRACTICE_IDS: practice_ids,
            _KEY_INSURANCE_SECTOR: insurance_sector,
            _KEY_TELEHEALTH: "false",
            _KEY_START_DATE: start_date.isoformat(),
            _KEY_LIMIT: limit,
        }
        url = _BASE_URL + _AVAILABILITIES_PATH
        logger.debug("Fetching availabilities: motive=%d start=%s", visit_motive_id, start_date)
        response = self._http.get(url, params=params)
        response.raise_for_status()
        result = _parse_availability_result(response.json())
        logger.debug("Availabilities response: total=%d", result.total)
        return result


def create_client(timeout: float = 30.0) -> DoctolibClient:
    http = httpx.Client(headers=_DEFAULT_HEADERS, timeout=timeout, follow_redirects=True)
    return DoctolibClient(http)


def _parse_profile_info(data: dict[str, object]) -> ProfileInfo:
    raw = data.get(_KEY_DATA, data)
    assert isinstance(raw, dict)
    motives = [_parse_visit_motive(m) for m in raw.get(_KEY_VISIT_MOTIVES, [])]  # type: ignore[union-attr]
    agendas = [_parse_agenda(a) for a in raw.get(_KEY_AGENDAS, [])]  # type: ignore[union-attr]
    places = [_parse_place(p) for p in raw.get(_KEY_PLACES, [])]  # type: ignore[union-attr]
    return ProfileInfo(visit_motives=motives, agendas=agendas, places=places)


def _parse_visit_motive(raw: dict[str, object]) -> VisitMotive:
    configs = [
        _parse_agenda_configuration(c)
        for c in (raw.get(_KEY_CONFIGURATIONS) or [])
    ]
    return VisitMotive(id=raw[_KEY_ID], name=raw[_KEY_NAME], configurations=configs)  # type: ignore[arg-type]


def _parse_agenda_configuration(raw: dict[str, object]) -> AgendaConfiguration:
    return AgendaConfiguration(
        insurance=raw[_KEY_INSURANCE],  # type: ignore[arg-type]
        agenda_id=raw.get(_KEY_AGENDA_ID),  # type: ignore[arg-type]
        online_booking_status=raw.get(_KEY_ONLINE_BOOKING_STATUS),  # type: ignore[arg-type]
        disabled=raw.get(_KEY_DISABLED),  # type: ignore[arg-type]
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
    )


def _parse_availability_result(raw: dict[str, object]) -> AvailabilityResult:
    days = [_parse_availability_day(d) for d in raw.get(_KEY_AVAILABILITIES, [])]  # type: ignore[union-attr]
    return AvailabilityResult(
        availabilities=days,
        total=raw.get(_KEY_TOTAL, 0),  # type: ignore[arg-type]
        reason=raw.get(_KEY_REASON),  # type: ignore[arg-type]
        message=raw.get(_KEY_MESSAGE),  # type: ignore[arg-type]
    )


def _parse_availability_day(raw: dict[str, object]) -> AvailabilityDay:
    slots = [_parse_slot(s) for s in raw.get(_KEY_SLOTS, [])]  # type: ignore[union-attr]
    return AvailabilityDay(date=raw[_KEY_DATE], slots=slots)  # type: ignore[arg-type]


def _parse_slot(raw: dict[str, object]) -> Slot:
    return Slot(
        start_date=raw[_KEY_START_DATE_SLOT],  # type: ignore[arg-type]
        end_date=raw[_KEY_END_DATE],  # type: ignore[arg-type]
        agenda_id=raw[_KEY_AGENDA_ID],  # type: ignore[arg-type]
        practice_id=raw[_KEY_PRACTICE_ID],  # type: ignore[arg-type]
    )
