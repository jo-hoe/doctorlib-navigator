from unittest.mock import MagicMock, call

import httpx
import pytest

from app.checker import AppointmentChecker, CheckResult, _get_motive_name, _resolve_booking_params
from app.config import BookingStep, DateWindow, DoctorConfig
from app.doctolib.client import DoctolibAPIError, DoctolibClient
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
from app.notification.notifier import Notifier


def _make_doctor(
    name: str = "Test Doctor",
    profile_slug: str = "test-doctor",
    insurance: str = "public",
    motive: str = "Erstuntersuchung / Folgeuntersuchung",
) -> DoctorConfig:
    return DoctorConfig(
        name=name,
        profile_slug=profile_slug,
        insurance=insurance,
        booking_steps=[BookingStep(label="visit_motive", value=motive)],
    )


def _make_profile(motive_name: str = "Erstuntersuchung / Folgeuntersuchung") -> ProfileInfo:
    motive = VisitMotive(
        id=14010219,
        name=motive_name,
        configurations=[
            AgendaConfiguration(
                insurance="public",
                agenda_id=2210330,
                online_booking_status="enabled_for_all",
                disabled=False,
            )
        ],
    )
    place = Place(id="practice-670660", name="Test", practice_ids=[670660])
    return ProfileInfo(visit_motives=[motive], agendas=[], places=[place])


def _make_empty_result() -> AvailabilityResult:
    return AvailabilityResult(
        availabilities=[AvailabilityDay(date="2026-08-06", slots=[])],
        total=0,
        reason="no_availabilities",
        message="Keine Termine online verfügbar",
    )


def _make_result_with_slots() -> AvailabilityResult:
    slot = Slot(
        start_date="2026-08-10T09:00:00+02:00",
        end_date="2026-08-10T09:20:00+02:00",
        agenda_id=2210330,
        practice_id=670660,
    )
    return AvailabilityResult(
        availabilities=[AvailabilityDay(date="2026-08-10", slots=[slot])],
        total=1,
        reason=None,
        message=None,
    )


def _make_checker(profile: ProfileInfo, avail: AvailabilityResult) -> tuple[AppointmentChecker, MagicMock]:
    client = MagicMock(spec=DoctolibClient)
    client.fetch_profile_info.return_value = profile
    client.fetch_availabilities.return_value = avail
    notifier = MagicMock(spec=Notifier)
    return AppointmentChecker(client=client, notifier=notifier), notifier


def test_check_all_no_slots_does_not_notify():
    checker, notifier = _make_checker(_make_profile(), _make_empty_result())
    results = checker.check_all([_make_doctor()])
    assert len(results) == 1
    assert results[0].has_slots is False
    notifier.notify.assert_not_called()


def test_check_all_with_slots_notifies():
    checker, notifier = _make_checker(_make_profile(), _make_result_with_slots())
    results = checker.check_all([_make_doctor()])
    assert results[0].has_slots is True
    notifier.notify.assert_called_once()
    subject, body = notifier.notify.call_args[1]["subject"], notifier.notify.call_args[1]["body"]
    assert "Test Doctor" in subject
    assert "2026-08-10" in body


def test_check_all_multiple_doctors():
    profile = _make_profile()
    client = MagicMock(spec=DoctolibClient)
    client.fetch_profile_info.return_value = profile
    client.fetch_availabilities.side_effect = [_make_empty_result(), _make_result_with_slots()]
    notifier = MagicMock(spec=Notifier)
    checker = AppointmentChecker(client=client, notifier=notifier)

    doctors = [_make_doctor(name="Doc A"), _make_doctor(name="Doc B")]
    results = checker.check_all(doctors)

    assert len(results) == 2
    assert results[0].has_slots is False
    assert results[1].has_slots is True
    notifier.notify.assert_called_once()


def test_resolve_booking_params_unknown_motive_raises():
    doctor = _make_doctor(motive="Unknown Motive")
    profile = _make_profile()
    with pytest.raises(ValueError, match="not found"):
        _resolve_booking_params(doctor, profile)


def test_resolve_booking_params_no_enabled_agendas_raises():
    doctor = _make_doctor(insurance="private")
    profile = _make_profile()
    with pytest.raises(ValueError, match="No enabled agendas"):
        _resolve_booking_params(doctor, profile)


def test_resolve_booking_params_falls_back_to_agendas_list():
    # Real profiles (e.g. alexander-spies) expose motives with null configurations;
    # the motive→agenda mapping lives on the agendas list instead.
    motive = VisitMotive(id=1271364, name="Akupunktur", configurations=[])
    agenda = Agenda(id=208211, practice_id=82596, visit_motive_ids=[1271364])
    place = Place(id="practice-82596", name="Praxis", practice_ids=[82596])
    profile = ProfileInfo(visit_motives=[motive], agendas=[agenda], places=[place])
    doctor = _make_doctor(motive="Akupunktur")

    motive_id, agenda_ids, practice_ids = _resolve_booking_params(doctor, profile)

    assert motive_id == 1271364
    assert agenda_ids == [208211]
    assert practice_ids == [82596]


def test_get_motive_name_raises_when_missing():
    doctor = DoctorConfig(
        name="X",
        profile_slug="x",
        booking_steps=[BookingStep(label="insurance", value="public")],
    )
    with pytest.raises(ValueError, match="visit_motive"):
        _get_motive_name(doctor)


def test_get_motive_name_returns_value():
    doctor = _make_doctor(motive="Erstuntersuchung / Folgeuntersuchung")
    assert _get_motive_name(doctor) == "Erstuntersuchung / Folgeuntersuchung"


def test_check_all_skips_failed_doctor_and_keeps_success():
    profile = _make_profile()
    client = MagicMock(spec=DoctolibClient)
    client.fetch_profile_info.return_value = profile
    request = httpx.Request("GET", "https://www.doctolib.de/availabilities.json")
    client.fetch_availabilities.side_effect = [
        httpx.HTTPStatusError("410", request=request, response=httpx.Response(410, request=request)),
        _make_result_with_slots(),
    ]
    notifier = MagicMock(spec=Notifier)
    checker = AppointmentChecker(client=client, notifier=notifier)

    results = checker.check_all([_make_doctor(name="Doc A"), _make_doctor(name="Doc B")])

    assert len(results) == 1
    assert results[0].doctor_name == "Doc B"
    notifier.notify.assert_called_once()


def test_check_all_raises_when_all_doctors_fail():
    client = MagicMock(spec=DoctolibClient)
    client.fetch_profile_info.side_effect = DoctolibAPIError("profile_not_found")
    notifier = MagicMock(spec=Notifier)
    checker = AppointmentChecker(client=client, notifier=notifier)

    with pytest.raises(RuntimeError, match="All 2 doctor check"):
        checker.check_all([_make_doctor(name="Doc A"), _make_doctor(name="Doc B")])
    notifier.notify.assert_not_called()


def test_check_all_does_not_notify_failed_doctor():
    client = MagicMock(spec=DoctolibClient)
    client.fetch_profile_info.side_effect = [DoctolibAPIError("boom"), _make_profile()]
    client.fetch_availabilities.return_value = _make_result_with_slots()
    notifier = MagicMock(spec=Notifier)
    checker = AppointmentChecker(client=client, notifier=notifier)

    results = checker.check_all([_make_doctor(name="Doc A"), _make_doctor(name="Doc B")])

    assert len(results) == 1
    notifier.notify.assert_called_once()
