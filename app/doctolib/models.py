from dataclasses import dataclass, field
from datetime import date
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.config import DateWindow


@dataclass(frozen=True)
class Slot:
    start_date: str
    end_date: Optional[str] = None
    agenda_id: Optional[int] = None
    practice_id: Optional[int] = None


@dataclass(frozen=True)
class AvailabilityDay:
    date: str
    slots: list[Slot] = field(default_factory=list)


def day_in_any_window(day_date: date, windows: "list[DateWindow]") -> bool:
    # An empty window list means "unrestricted" — every date qualifies.
    if not windows:
        return True
    return any(
        (w.start_date is None or day_date >= w.start_date)
        and (w.end_date is None or day_date <= w.end_date)
        for w in windows
    )


@dataclass(frozen=True)
class AvailabilityResult:
    availabilities: list[AvailabilityDay]
    total: int
    reason: Optional[str]
    message: Optional[str]
    next_slot: Optional[str] = None

    @property
    def has_slots(self) -> bool:
        return self.total > 0

    @staticmethod
    def merge(results: "list[AvailabilityResult]") -> "AvailabilityResult":
        # Combine per-agenda results into one, deduplicating slots by start_date
        # (the same physical slot can appear under multiple agendas) and keeping
        # the earliest next_slot so an out-of-window hint is still surfaced.
        by_date: dict[str, list[Slot]] = {}
        seen: set[str] = set()
        next_slot: Optional[str] = None
        for r in results:
            if r.next_slot is not None and (next_slot is None or r.next_slot < next_slot):
                next_slot = r.next_slot
            for day in r.availabilities:
                for slot in day.slots:
                    if slot.start_date in seen:
                        continue
                    seen.add(slot.start_date)
                    by_date.setdefault(day.date, []).append(slot)
        days = [
            AvailabilityDay(date=d, slots=by_date[d]) for d in sorted(by_date)
        ]
        return AvailabilityResult(
            availabilities=days,
            total=len(seen),
            reason=None,
            message=None,
            next_slot=next_slot,
        )

    def with_date_filter(
        self,
        windows: "list[DateWindow]",
        logger: Optional[logging.Logger] = None,
    ) -> "AvailabilityResult":
        if not windows:
            return self
        kept: list[AvailabilityDay] = []
        for day in self.availabilities:
            try:
                day_date = date.fromisoformat(day.date[:10])
            except ValueError:
                kept.append(day)
                continue
            if day_in_any_window(day_date, windows):
                kept.append(day)
            elif logger and day.slots:
                logger.debug(
                    "Skipping %s (%d slot(s)) — outside all configured windows",
                    day.date,
                    len(day.slots),
                )
        return AvailabilityResult(
            availabilities=kept,
            total=sum(len(d.slots) for d in kept),
            reason=self.reason,
            message=self.message,
            next_slot=self.next_slot,
        )


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

    def available_insurances(self) -> list[str]:
        return sorted({
            c.insurance
            for c in self.configurations
            if c.agenda_id is not None
            and not c.disabled
            and c.online_booking_status == "enabled_for_all"
        })


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
    slug: Optional[str] = None


@dataclass(frozen=True)
class ProfileInfo:
    visit_motives: list[VisitMotive]
    agendas: list[Agenda]
    places: list[Place]
    speciality_slug: Optional[str] = None
    speciality_id: Optional[int] = None

    def find_motive_by_name(self, name: str) -> Optional[VisitMotive]:
        name_lower = name.lower()
        for motive in self.visit_motives:
            if motive.name.lower() == name_lower:
                return motive
        return None

    def agenda_ids_for_motive(self, motive_id: int) -> list[int]:
        return [a.id for a in self.agendas if motive_id in a.visit_motive_ids]

    def practice_ids(self) -> list[int]:
        return [pid for place in self.places for pid in place.practice_ids]
