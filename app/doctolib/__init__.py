from app.doctolib.client import DoctolibAPIError, DoctolibClient, create_client
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

__all__ = [
    "DoctolibAPIError",
    "DoctolibClient",
    "create_client",
    "Agenda",
    "AgendaConfiguration",
    "AvailabilityDay",
    "AvailabilityResult",
    "Place",
    "ProfileInfo",
    "Slot",
    "VisitMotive",
]
