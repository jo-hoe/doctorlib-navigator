from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.doctolib.client import (
    DoctolibClient,
    _parse_availability_result,
    _parse_profile_info,
    create_client,
)
from app.doctolib.models import AvailabilityResult, ProfileInfo


_INFO_RESPONSE = {
    "data": {
        "visit_motives": [
            {
                "id": 14010219,
                "name": "Erstuntersuchung / Folgeuntersuchung",
                "configurations": [
                    {
                        "insurance": "public",
                        "agenda_id": 2210330,
                        "online_booking_status": "enabled_for_all",
                        "disabled": False,
                    }
                ],
            }
        ],
        "agendas": [
            {"id": 2210330, "practice_id": 670660, "visit_motive_ids": [14010219]}
        ],
        "places": [
            {"id": "practice-670660", "name": "MVZ Test", "practice_ids": [670660]}
        ],
    }
}

_AVAILABILITY_RESPONSE = {
    "availabilities": [{"date": "2026-08-06", "slots": []}],
    "total": 0,
    "reason": "no_availabilities",
    "message": "Keine Termine online verfügbar",
}

_AVAILABILITY_WITH_SLOTS = {
    "availabilities": [
        {
            "date": "2026-08-10",
            "slots": [
                {
                    "start_date": "2026-08-10T09:00:00.000+02:00",
                    "end_date": "2026-08-10T09:20:00.000+02:00",
                    "agenda_id": 2210330,
                    "practice_id": 670660,
                }
            ],
        }
    ],
    "total": 1,
    "reason": None,
    "message": None,
}


def test_parse_profile_info():
    info = _parse_profile_info(_INFO_RESPONSE)
    assert len(info.visit_motives) == 1
    assert info.visit_motives[0].name == "Erstuntersuchung / Folgeuntersuchung"
    assert info.practice_ids() == [670660]


def test_parse_availability_result_empty():
    result = _parse_availability_result(_AVAILABILITY_RESPONSE)
    assert result.has_slots is False
    assert result.total == 0
    assert result.reason == "no_availabilities"


def test_parse_availability_result_with_slots():
    result = _parse_availability_result(_AVAILABILITY_WITH_SLOTS)
    assert result.has_slots is True
    assert result.total == 1
    assert result.availabilities[0].slots[0].agenda_id == 2210330


def _make_client(mock_get_return: dict) -> DoctolibClient:
    http = MagicMock(spec=httpx.Client)
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = mock_get_return
    http.get.return_value = response
    return DoctolibClient(http)


def test_fetch_profile_info_calls_correct_url():
    client = _make_client(_INFO_RESPONSE)
    info = client.fetch_profile_info("test-slug")
    client._http.get.assert_called_once()
    call_kwargs = client._http.get.call_args
    assert "info.json" in call_kwargs[0][0]
    assert isinstance(info, ProfileInfo)


def test_fetch_availabilities_calls_correct_url():
    client = _make_client(_AVAILABILITY_RESPONSE)
    result = client.fetch_availabilities(
        visit_motive_id=14010219,
        agenda_ids=[2210330],
        practice_ids=[670660],
        insurance_sector="public",
    )
    client._http.get.assert_called_once()
    call_kwargs = client._http.get.call_args
    assert "availabilities.json" in call_kwargs[0][0]
    assert isinstance(result, AvailabilityResult)


def test_create_client_returns_doctolib_client():
    client = create_client()
    assert isinstance(client, DoctolibClient)
