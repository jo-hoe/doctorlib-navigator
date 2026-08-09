import pytest

from datetime import date
from unittest.mock import MagicMock

from app.config import DateWindow
from app.doctolib.models import (
    AgendaConfiguration,
    Agenda,
    AvailabilityDay,
    AvailabilityResult,
    Place,
    ProfileInfo,
    Slot,
    VisitMotive,
)


def _make_result(days: list[tuple[str, int]]) -> AvailabilityResult:
    """Build a result with (date_str, slot_count) pairs."""
    availabilities = [
        AvailabilityDay(
            date=d,
            slots=[
                Slot(start_date=f"{d}T09:00:00+02:00", end_date=f"{d}T09:20:00+02:00", agenda_id=1, practice_id=1)
                for _ in range(n)
            ],
        )
        for d, n in days
    ]
    total = sum(n for _, n in days)
    return AvailabilityResult(availabilities=availabilities, total=total, reason=None, message=None)


def _make_config(insurance: str, agenda_id: int, disabled: bool = False, status: str = "enabled_for_all") -> AgendaConfiguration:
    return AgendaConfiguration(
        insurance=insurance,
        agenda_id=agenda_id,
        online_booking_status=status,
        disabled=disabled,
    )


def test_visit_motive_agenda_ids_for_insurance():
    motive = VisitMotive(
        id=1,
        name="Test",
        configurations=[
            _make_config("public", 100),
            _make_config("public", 101, disabled=True),
            _make_config("private", 200),
        ],
    )
    assert motive.agenda_ids_for_insurance("public") == [100]
    assert motive.agenda_ids_for_insurance("private") == [200]


def test_visit_motive_excludes_none_agenda_id():
    motive = VisitMotive(
        id=1,
        name="Test",
        configurations=[
            AgendaConfiguration(
                insurance="public",
                agenda_id=None,
                online_booking_status="enabled_for_all",
                disabled=False,
            )
        ],
    )
    assert motive.agenda_ids_for_insurance("public") == []


def test_visit_motive_excludes_non_enabled():
    motive = VisitMotive(
        id=1,
        name="Test",
        configurations=[_make_config("public", 100, status="disabled")],
    )
    assert motive.agenda_ids_for_insurance("public") == []


def test_profile_info_find_motive_by_name():
    motive = VisitMotive(id=1, name="Erstuntersuchung / Folgeuntersuchung")
    profile = ProfileInfo(visit_motives=[motive], agendas=[], places=[])
    assert profile.find_motive_by_name("erstuntersuchung / folgeuntersuchung") == motive
    assert profile.find_motive_by_name("nonexistent") is None


def test_profile_info_practice_ids():
    place = Place(id="practice-1", name="Test", practice_ids=[101, 102])
    profile = ProfileInfo(visit_motives=[], agendas=[], places=[place])
    assert profile.practice_ids() == [101, 102]


def test_availability_result_has_slots_true():
    result = AvailabilityResult(
        availabilities=[],
        total=3,
        reason=None,
        message=None,
    )
    assert result.has_slots is True


def test_availability_result_has_slots_false():
    result = AvailabilityResult(
        availabilities=[],
        total=0,
        reason="no_availabilities",
        message="Keine Termine online verfügbar",
    )
    assert result.has_slots is False


def test_with_date_filter_no_windows_returns_self():
    result = _make_result([("2026-08-10", 2)])
    assert result.with_date_filter([]) is result


def test_with_date_filter_end_date_excludes_later_days():
    result = _make_result([("2026-08-10", 1), ("2026-08-29", 1)])
    filtered = result.with_date_filter([DateWindow(end_date=date(2026, 8, 28))])
    assert filtered.total == 1
    assert filtered.availabilities[0].date == "2026-08-10"


def test_with_date_filter_start_date_excludes_earlier_days():
    result = _make_result([("2026-08-10", 1), ("2026-08-20", 1)])
    filtered = result.with_date_filter([DateWindow(start_date=date(2026, 8, 15))])
    assert filtered.total == 1
    assert filtered.availabilities[0].date == "2026-08-20"


def test_with_date_filter_multiple_windows():
    result = _make_result([("2026-08-10", 1), ("2026-09-15", 1), ("2026-11-03", 1)])
    windows = [
        DateWindow(end_date=date(2026, 8, 31)),
        DateWindow(start_date=date(2026, 11, 1), end_date=date(2026, 11, 7)),
    ]
    filtered = result.with_date_filter(windows)
    assert filtered.total == 2
    dates = [d.date for d in filtered.availabilities]
    assert "2026-08-10" in dates
    assert "2026-11-03" in dates
    assert "2026-09-15" not in dates


def test_with_date_filter_logs_skipped_days():
    result = _make_result([("2026-08-10", 1), ("2026-09-01", 2)])
    mock_logger = MagicMock()
    filtered = result.with_date_filter([DateWindow(end_date=date(2026, 8, 28))], logger=mock_logger)
    assert filtered.total == 1
    mock_logger.debug.assert_called_once()
    call_args = mock_logger.debug.call_args[0]
    assert "2026-09-01" in call_args[1]
    assert 2 == call_args[2]

