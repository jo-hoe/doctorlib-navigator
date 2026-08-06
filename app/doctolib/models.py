from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Slot:
    start_date: str
    end_date: str
    agenda_id: int
    practice_id: int


@dataclass(frozen=True)
class AvailabilityDay:
    date: str
    slots: list[Slot] = field(default_factory=list)


@dataclass(frozen=True)
class AvailabilityResult:
    availabilities: list[AvailabilityDay]
    total: int
    reason: Optional[str]
    message: Optional[str]

    @property
    def has_slots(self) -> bool:
        return self.total > 0


@dataclass(frozen=True)
class AgendaConfiguration:
    insurance: str
    agenda_id: Optional[int]
    online_booking_status: Optional[str]
    disabled: Optional[bool]


@dataclass(frozen=True)
class VisitMotive:
    id: int
    name: str
    configurations: list[AgendaConfiguration] = field(default_factory=list)

    def agenda_ids_for_insurance(self, insurance: str) -> list[int]:
        return [
            c.agenda_id
            for c in self.configurations
            if c.insurance == insurance
            and c.agenda_id is not None
            and not c.disabled
            and c.online_booking_status == "enabled_for_all"
        ]


@dataclass(frozen=True)
class Agenda:
    id: int
    practice_id: int
    visit_motive_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    practice_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class ProfileInfo:
    visit_motives: list[VisitMotive]
    agendas: list[Agenda]
    places: list[Place]

    def find_motive_by_name(self, name: str) -> Optional[VisitMotive]:
        name_lower = name.lower()
        for motive in self.visit_motives:
            if motive.name.lower() == name_lower:
                return motive
        return None

    def practice_ids(self) -> list[int]:
        return [pid for place in self.places for pid in place.practice_ids]
