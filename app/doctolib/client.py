import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

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

_BASE_URL = "https://www.doctolib.de"
_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Referer": _BASE_URL + "/",
}


@dataclass(frozen=True)
class DoctolibClient:
    _http: httpx.Client

    def fetch_profile_info(self, profile_slug: str) -> ProfileInfo:
        url = f"{_BASE_URL}/online_booking/api/slot_selection_funnel/v1/info.json"
        logger.debug("Fetching profile info for slug=%s", profile_slug)
        response = self._http.get(url, params={"profile_slug": profile_slug, "locale": "de"})
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
            "visit_motive_ids": visit_motive_id,
            "agenda_ids": agenda_ids,
            "practice_ids": practice_ids,
            "insurance_sector": insurance_sector,
            "telehealth": "false",
            "start_date": start_date.isoformat(),
            "limit": limit,
        }
        url = f"{_BASE_URL}/availabilities.json"
        logger.debug("Fetching availabilities: motive=%d start=%s", visit_motive_id, start_date)
        response = self._http.get(url, params=params)
        response.raise_for_status()
        result = _parse_availability_result(response.json())
        logger.debug("Availabilities response: total=%d", result.total)
        return result


def create_client(timeout: float = 30.0) -> DoctolibClient:
    http = httpx.Client(headers=_DEFAULT_HEADERS, timeout=timeout, follow_redirects=True)
    return DoctolibClient(http)


def _parse_profile_info(data: dict) -> ProfileInfo:
    raw = data.get("data", data)

    motives = [_parse_visit_motive(m) for m in raw.get("visit_motives", [])]
    agendas = [_parse_agenda(a) for a in raw.get("agendas", [])]
    places = [_parse_place(p) for p in raw.get("places", [])]
    return ProfileInfo(visit_motives=motives, agendas=agendas, places=places)


def _parse_visit_motive(raw: dict) -> VisitMotive:
    configs = [
        _parse_agenda_configuration(c)
        for c in (raw.get("configurations") or [])
    ]
    return VisitMotive(id=raw["id"], name=raw["name"], configurations=configs)


def _parse_agenda_configuration(raw: dict) -> AgendaConfiguration:
    return AgendaConfiguration(
        insurance=raw["insurance"],
        agenda_id=raw.get("agenda_id"),
        online_booking_status=raw.get("online_booking_status"),
        disabled=raw.get("disabled"),
    )


def _parse_agenda(raw: dict) -> Agenda:
    return Agenda(
        id=raw["id"],
        practice_id=raw["practice_id"],
        visit_motive_ids=raw.get("visit_motive_ids", []),
    )


def _parse_place(raw: dict) -> Place:
    return Place(
        id=raw["id"],
        name=raw["name"],
        practice_ids=raw.get("practice_ids", []),
    )


def _parse_availability_result(raw: dict) -> AvailabilityResult:
    days = [_parse_availability_day(d) for d in raw.get("availabilities", [])]
    return AvailabilityResult(
        availabilities=days,
        total=raw.get("total", 0),
        reason=raw.get("reason"),
        message=raw.get("message"),
    )


def _parse_availability_day(raw: dict) -> AvailabilityDay:
    slots = [_parse_slot(s) for s in raw.get("slots", [])]
    return AvailabilityDay(date=raw["date"], slots=slots)


def _parse_slot(raw: dict) -> Slot:
    return Slot(
        start_date=raw["start_date"],
        end_date=raw["end_date"],
        agenda_id=raw["agenda_id"],
        practice_id=raw["practice_id"],
    )
