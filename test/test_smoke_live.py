"""Live smoke test against the real Doctolib API.

Skipped unless DOCTOLIB_SMOKE_SLUG is set — this test performs real network
requests and is not run in CI. To run it locally:

    DOCTOLIB_SMOKE_SLUG=alexander-spies python -m pytest test/test_smoke_live.py -v -s
"""

import os

import pytest

from app.doctolib.client import create_client

_SMOKE_SLUG = os.environ.get("DOCTOLIB_SMOKE_SLUG")

pytestmark = pytest.mark.skipif(
    not _SMOKE_SLUG,
    reason="DOCTOLIB_SMOKE_SLUG not set; live smoke test skipped",
)


def test_live_profile_and_availabilities():
    assert _SMOKE_SLUG is not None
    client = create_client()

    profile = client.fetch_profile_info(_SMOKE_SLUG)
    assert profile.visit_motives, "profile returned no visit motives"

    motive = profile.visit_motives[0]
    insurance = "public"
    agenda_ids = motive.agenda_ids_for_insurance(insurance)
    if not agenda_ids:
        agenda_ids = [a.id for a in profile.agendas]
    practice_ids = profile.practice_ids()

    result = client.fetch_availabilities(
        visit_motive_id=motive.id,
        agenda_ids=agenda_ids,
        practice_ids=practice_ids,
        insurance_sector=insurance,
    )

    # We don't assert on slot counts (they change constantly) — only that the
    # request round-trips and parses into the expected contract.
    print(
        f"\n[smoke] slug={_SMOKE_SLUG} motive={motive.name!r} "
        f"total={result.total} reason={result.reason}"
    )
    assert isinstance(result.total, int)
