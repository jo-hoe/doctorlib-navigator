import pytest

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
