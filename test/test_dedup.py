import pytest
from unittest.mock import MagicMock

from app.checker import AppointmentChecker
from app.config import BookingStep, DoctorConfig
from app.doctolib.client import DoctolibClient
from app.doctolib.models import (
    AgendaConfiguration,
    AvailabilityDay,
    AvailabilityResult,
    Place,
    ProfileInfo,
    Slot,
    VisitMotive,
)
from app.notification.notifier import Notifier
from app.state.store import InMemoryStateStore


def _make_doctor() -> DoctorConfig:
    return DoctorConfig(
        name="Test Doctor",
        profile_slug="test-doctor",
        insurance="public",
        booking_steps=[BookingStep(label="visit_motive", value="Erstuntersuchung")],
    )


def _make_profile() -> ProfileInfo:
    motive = VisitMotive(
        id=1,
        name="Erstuntersuchung",
        configurations=[
            AgendaConfiguration(
                insurance="public",
                agenda_id=100,
                online_booking_status="enabled_for_all",
                disabled=False,
            )
        ],
    )
    return ProfileInfo(visit_motives=[motive], agendas=[], places=[Place(id="p1", name="P", practice_ids=[1])])


def _make_result(slot_dates: list[str]) -> AvailabilityResult:
    slots = [
        Slot(start_date=d, end_date=d, agenda_id=100, practice_id=1)
        for d in slot_dates
    ]
    day = AvailabilityDay(date="2026-08-10", slots=slots)
    return AvailabilityResult(
        availabilities=[day] if slots else [],
        total=len(slots),
        reason=None,
        message=None,
    )


def _make_checker(avail: AvailabilityResult, state: InMemoryStateStore) -> tuple[AppointmentChecker, MagicMock]:
    client = MagicMock(spec=DoctolibClient)
    client.fetch_profile_info.return_value = _make_profile()
    client.fetch_availabilities.return_value = avail
    notifier = MagicMock(spec=Notifier)
    return AppointmentChecker(client=client, notifier=notifier, state=state), notifier


def test_notification_on_first_run():
    state = InMemoryStateStore()
    checker, notifier = _make_checker(_make_result(["2026-08-10T09:00:00"]), state)
    checker.check_all([_make_doctor()])
    notifier.notify.assert_called_once()


def test_no_notification_when_slots_unchanged():
    state = InMemoryStateStore()
    result = _make_result(["2026-08-10T09:00:00"])
    checker, notifier = _make_checker(result, state)
    checker.check_all([_make_doctor()])
    checker.check_all([_make_doctor()])
    assert notifier.notify.call_count == 1


def test_notification_on_new_slots():
    state = InMemoryStateStore()
    checker, notifier = _make_checker(_make_result(["2026-08-10T09:00:00"]), state)
    checker.check_all([_make_doctor()])

    client2 = MagicMock(spec=DoctolibClient)
    client2.fetch_profile_info.return_value = _make_profile()
    client2.fetch_availabilities.return_value = _make_result(["2026-08-10T09:00:00", "2026-08-11T09:00:00"])
    checker._client = client2
    checker.check_all([_make_doctor()])
    assert notifier.notify.call_count == 2


def test_no_notification_when_slots_disappear():
    # Slots going away is not news — an empty result has no *new* slots, so the
    # second run must stay silent. (State is still pruned; see
    # test_state_cleared_after_slots_disappear.)
    state = InMemoryStateStore()
    checker, notifier = _make_checker(_make_result(["2026-08-10T09:00:00"]), state)
    checker.check_all([_make_doctor()])

    checker._client.fetch_availabilities.return_value = _make_result([])
    checker.check_all([_make_doctor()])
    assert notifier.notify.call_count == 1


def test_no_notification_when_still_no_slots():
    state = InMemoryStateStore()
    checker, notifier = _make_checker(_make_result([]), state)
    checker.check_all([_make_doctor()])
    checker.check_all([_make_doctor()])
    notifier.notify.assert_not_called()


def test_state_cleared_after_slots_disappear():
    state = InMemoryStateStore()
    checker, _ = _make_checker(_make_result(["2026-08-10T09:00:00"]), state)
    checker.check_all([_make_doctor()])

    checker._client.fetch_availabilities.return_value = _make_result([])
    checker.check_all([_make_doctor()])

    assert state.load("Test_Doctor") == frozenset()
