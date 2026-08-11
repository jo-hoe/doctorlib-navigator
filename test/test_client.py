from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.doctolib.client import (
    DoctolibAPIError,
    DoctolibClient,
    _get_with_retry,
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

# Real doctolib.de shape: slots are plain ISO strings and reason/message are absent.
_AVAILABILITY_STRING_SLOTS = {
    "availabilities": [
        {
            "date": "2026-08-12",
            "slots": [
                "2026-08-12T08:00:00.000+02:00",
                "2026-08-12T08:20:00.000+02:00",
            ],
        }
    ],
    "total": 2,
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


def test_parse_availability_result_string_slots():
    result = _parse_availability_result(_AVAILABILITY_STRING_SLOTS)
    assert result.has_slots is True
    assert result.total == 2
    slot = result.availabilities[0].slots[0]
    assert slot.start_date == "2026-08-12T08:00:00.000+02:00"
    assert slot.end_date is None
    assert slot.agenda_id is None


def _make_client(mock_get_return: dict) -> DoctolibClient:
    http = MagicMock(spec=httpx.Client)
    response = MagicMock()
    response.status_code = 200
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


def test_parse_availability_error_shape_raises():
    with pytest.raises(DoctolibAPIError):
        _parse_availability_result({"error": "bad request"})


def test_parse_availability_status_shape_raises():
    with pytest.raises(DoctolibAPIError):
        _parse_availability_result({"status": 404, "error": "Not Found"})


def test_parse_availability_missing_key_raises():
    with pytest.raises(DoctolibAPIError):
        _parse_availability_result({"total": 0})


def test_parse_profile_info_errors_shape_raises():
    with pytest.raises(DoctolibAPIError):
        _parse_profile_info({"errors": [{"error_code": "profile_not_found"}]})


def _response(status_code: int, headers: dict | None = None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    return resp


def test_retry_retries_on_429_then_succeeds():
    http = MagicMock(spec=httpx.Client)
    http.get.side_effect = [_response(429), _response(200)]
    slept: list[float] = []
    resp = _get_with_retry(http, "http://x", {}, sleep=slept.append)
    assert resp.status_code == 200
    assert http.get.call_count == 2
    assert len(slept) == 1


def test_retry_retries_on_503_then_succeeds():
    http = MagicMock(spec=httpx.Client)
    http.get.side_effect = [_response(503), _response(200)]
    resp = _get_with_retry(http, "http://x", {}, sleep=lambda _: None)
    assert resp.status_code == 200
    assert http.get.call_count == 2


def test_retry_does_not_retry_on_410():
    http = MagicMock(spec=httpx.Client)
    http.get.side_effect = [_response(410)]
    resp = _get_with_retry(http, "http://x", {}, sleep=lambda _: None)
    assert resp.status_code == 410
    assert http.get.call_count == 1


def test_retry_retries_on_request_error_then_raises():
    http = MagicMock(spec=httpx.Client)
    http.get.side_effect = httpx.ConnectError("boom")
    with pytest.raises(httpx.ConnectError):
        _get_with_retry(http, "http://x", {}, sleep=lambda _: None)
    assert http.get.call_count == 3


def test_retry_honors_retry_after_header():
    http = MagicMock(spec=httpx.Client)
    http.get.side_effect = [_response(429, {"Retry-After": "7"}), _response(200)]
    slept: list[float] = []
    _get_with_retry(http, "http://x", {}, sleep=slept.append)
    assert slept == [7.0]


def test_retry_exhausts_and_returns_last_status():
    http = MagicMock(spec=httpx.Client)
    http.get.side_effect = [_response(503), _response(503), _response(503)]
    resp = _get_with_retry(http, "http://x", {}, sleep=lambda _: None)
    assert resp.status_code == 503
    assert http.get.call_count == 3


def test_fetch_availabilities_clamps_limit():
    client = _make_client(_AVAILABILITY_RESPONSE)
    client.fetch_availabilities(
        visit_motive_id=14010219,
        agenda_ids=[2210330],
        practice_ids=[670660],
        insurance_sector="public",
        limit=0,
    )
    params = client._http.get.call_args[1]["params"]
    assert params["limit"] == 1
