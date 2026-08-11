"""
Discovery tool — prints bookable appointment types for a Doctolib profile.

Usage:
    python discover.py <profile_slug>

Example:
    python discover.py dr-example-berlin

The profile_slug is the last path segment of the doctor's Doctolib URL:
    https://www.doctolib.de/allgemeinmedizin/berlin/max-mustermann
                                                    ^^^^^^^^^^^^^^
                                                    profile_slug
"""

import sys
import logging

from app.doctolib import create_client
from app.doctolib.client import DoctolibClient

_INDENT = "  "

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def discover_profile(client: DoctolibClient, profile_slug: str) -> None:
    profile = client.fetch_profile_info(profile_slug)

    bookable = [
        m
        for m in profile.visit_motives
        if m.available_insurances() or profile.agenda_ids_for_motive(m.id)
    ]
    if not bookable:
        print(f"No bookable appointment types found for profile '{profile_slug}'.")
        return

    print(f"\nProfile slug: {profile_slug}")
    print(f"Bookable appointment types ({len(bookable)} found):\n")
    for motive in bookable:
        insurances = motive.available_insurances()
        insurance_str = " / ".join(insurances) if insurances else "unknown"
        print(f"{_INDENT}visit_motive: \"{motive.name}\"")
        print(f"{_INDENT}insurance:    {insurance_str}")
        print()

    first = bookable[0]
    insurances = first.available_insurances()
    print("Ready-to-paste values.yaml snippet:\n")
    print(f"{_INDENT}config:")
    print(f"{_INDENT}  doctors:")
    print(f"{_INDENT}    - name: \"<human readable name>\"")
    print(f"{_INDENT}      profile_slug: \"{profile_slug}\"")
    if len(insurances) == 1:
        print(f"{_INDENT}      insurance: \"{insurances[0]}\"")
    print(f"{_INDENT}      booking_steps:")
    print(f"{_INDENT}        - label: \"visit_motive\"")
    print(f"{_INDENT}          value: \"{first.name}\"")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    discover_profile(create_client(), sys.argv[1])
