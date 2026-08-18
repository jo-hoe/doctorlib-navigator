import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class PruneStrategy(Protocol):
    """Decides which previously-seen slots stay 'live' between runs.

    ``last_seen`` maps each known slot to the timestamp it was last observed
    as available. ``current`` is the set of slots reported in this run.
    ``now`` is the current time. Returns the subset of slots that should
    still be considered present.
    """

    def live_slots(
        self,
        last_seen: dict[str, datetime],
        current: frozenset[str],
        now: datetime,
    ) -> set[str]: ...


class ImmediatePruneStrategy:
    """Drops a slot the instant it stops being reported (original behaviour)."""

    def live_slots(
        self,
        last_seen: dict[str, datetime],
        current: frozenset[str],
        now: datetime,
    ) -> set[str]:
        return set(current)


class TTLPruneStrategy:
    """Keeps a vanished slot 'live' until it has been absent longer than the TTL.

    This absorbs both Doctolib jitter (slot briefly disappears and reappears
    across consecutive runs) and spurious "slots got booked" re-notifications:
    slots are only evicted once they have been continuously absent for longer
    than the TTL.
    """

    def __init__(self, ttl: timedelta) -> None:
        self._ttl = ttl

    def live_slots(
        self,
        last_seen: dict[str, datetime],
        current: frozenset[str],
        now: datetime,
    ) -> set[str]:
        cutoff = now - self._ttl
        return {slot for slot, seen in last_seen.items() if seen >= cutoff}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TTLFileStateStore:
    """State store that persists per-slot last-seen timestamps and applies a
    :class:`PruneStrategy` so that transient absences do not immediately reset
    the deduplication state.

    On disk the state is ``{key: {slot: last_seen_iso}}``. ``load`` and ``save``
    still speak ``frozenset[str]`` so callers are unaffected.

    Absent slots are never dropped from the persisted map by ``save()`` —
    their ``last_seen`` timestamp is simply left unchanged. Eviction is
    delegated entirely to the strategy's ``live_slots()``.
    """

    def __init__(
        self,
        path: Path,
        strategy: PruneStrategy,
        clock=_utcnow,
    ) -> None:
        self._path = path
        self._strategy = strategy
        self._clock = clock

    def _read(self) -> dict[str, dict[str, str]]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("State file %s unreadable, starting fresh", self._path)
            return {}

    def _write(self, data: dict[str, dict[str, str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _parse(stamps: dict[str, str]) -> dict[str, datetime]:
        parsed: dict[str, datetime] = {}
        for slot, iso in stamps.items():
            try:
                parsed[slot] = datetime.fromisoformat(iso)
            except ValueError:
                logger.debug("Ignoring unparseable timestamp %r for slot %s", iso, slot)
        return parsed

    def load(self, key: str) -> frozenset[str]:
        last_seen = self._parse(self._read().get(key, {}))
        # Pass an empty frozenset: load() has no knowledge of the current run's
        # slots, so ImmediatePruneStrategy returns everything in last_seen here.
        # That is intentional — load() reflects what was live as of the last save.
        return frozenset(self._strategy.live_slots(last_seen, frozenset(last_seen.keys()), self._clock()))

    def save(self, key: str, slots: frozenset[str]) -> None:
        now = self._clock()
        data = self._read()
        last_seen = self._parse(data.get(key, {}))
        # Only refresh last_seen for currently-present slots.
        # Absent slots keep their existing timestamp — the strategy decides
        # when they are actually evicted based on TTL.
        for slot in slots:
            last_seen[slot] = now
        live = self._strategy.live_slots(last_seen, slots, now)
        data[key] = {
            slot: seen.isoformat()
            for slot, seen in last_seen.items()
            if slot in live
        }
        self._write(data)


def create_ttl_file_store(state_path: str, strategy: PruneStrategy) -> TTLFileStateStore:
    return TTLFileStateStore(Path(state_path), strategy)
