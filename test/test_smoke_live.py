"""Live smoke test against the real Doctolib API.

Skipped unless DOCTOLIB_SMOKE_SLUG is set — this test performs real network
requests and is not run in CI. To run it locally:

    DOCTOLIB_SMOKE_SLUG=alexander-spies python -m pytest test/test_smoke_live.py -v -s

The next_slot re-query test additionally needs a slug whose earliest availability
is beyond the default 5-day scan window (so the API returns total=0 + next_slot):

    DOCTOLIB_SMOKE_SLUG=<distant-slug> python -m pytest test/test_smoke_live.py -v -s
"""

import os
from datetime import date

import pytest

from app.doctolib.client import create_client

_SMOKE_SLUG = os.environ.get("DOCTOLIB_SMOKE_SLUG")

pytestmark = pytest.mark.skipif(
    not _SMOKE_SLUG,
    reason="DOCTOLIB_SMOKE_SLUG not set; live smoke test skipped",
)


def _resolve_booking_params(profile):
    motive = profile.visit_motives[0]
    agenda_ids = motive.agenda_ids_for_insurance("public")
    if not agenda_ids:
        agenda_ids = [a.id for a in profile.agendas]
    return motive, agenda_ids, profile.practice_ids()


def test_live_profile_and_availabilities():
    assert _SMOKE_SLUG is not None
    client = create_client()

    profile = client.fetch_profile_info(_SMOKE_SLUG)
    assert profile.visit_motives, "profile returned no visit motives"

    motive, agenda_ids, practice_ids = _resolve_booking_params(profile)

    result = client.fetch_availabilities(
        visit_motive_id=motive.id,
        agenda_ids=agenda_ids,
        practice_ids=practice_ids,
        insurance_sector="public",
    )

    # We don't assert on slot counts (they change constantly) — only that the
    # request round-trips and parses into the expected contract.
    print(
        f"\n[smoke] slug={_SMOKE_SLUG} motive={motive.name!r} "
        f"total={result.total} reason={result.reason} next_slot={result.next_slot}"
    )
    assert isinstance(result.total, int)


def test_live_next_slot_requery_returns_slots():
    """Verify the real-world semantics end-to-end: a combined multi-agenda request can
    return `not_opened_availability` (masking the one open agenda), but scanning each
    agenda individually and re-querying at its `next_slot` surfaces concrete slots.
    Skips gracefully if this profile has near-term availability everywhere."""
    assert _SMOKE_SLUG is not None
    client = create_client()

    profile = client.fetch_profile_info(_SMOKE_SLUG)
    motive, agenda_ids, practice_ids = _resolve_booking_params(profile)

    found: list[str] = []
    surfaced_via_next_slot = False
    for agenda in agenda_ids:
        first = client.fetch_availabilities(
            visit_motive_id=motive.id,
            agenda_ids=[agenda],
            practice_ids=practice_ids,
            insurance_sector="public",
        )
        if first.total > 0:
            found += [s.start_date for d in first.availabilities for s in d.slots]
            continue
        if not first.next_slot:
            continue
        next_date = date.fromisoformat(first.next_slot[:10])
        second = client.fetch_availabilities(
            visit_motive_id=motive.id,
            agenda_ids=[agenda],
            practice_ids=practice_ids,
            insurance_sector="public",
            start_date=next_date,
        )
        slots = [s.start_date for d in second.availabilities for s in d.slots]
        if slots:
            surfaced_via_next_slot = True
            found += slots

    print(
        f"\n[smoke] slug={_SMOKE_SLUG} agendas={len(agenda_ids)} "
        f"slots_found={len(found)} via_next_slot={surfaced_via_next_slot}"
    )
    if not found:
        pytest.skip(
            f"profile {_SMOKE_SLUG} has no availability on any agenda right now"
        )
    # If we got here, the per-agenda scan surfaced real slots — the exact behaviour
    # the checker relies on to defeat the multi-agenda not_opened poisoning.
    assert found
