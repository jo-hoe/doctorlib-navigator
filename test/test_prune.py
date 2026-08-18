from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.state.duration import parse_duration
from app.state.prune import (
    ImmediatePruneStrategy,
    TTLFileStateStore,
    TTLPruneStrategy,
)


@pytest.mark.parametrize(
    "text,seconds",
    [
        ("1s", 1),
        ("23m", 23 * 60),
        ("2h", 2 * 3600),
        ("1h30m", 90 * 60),
        ("1d", 86400),
        ("500ms", 0.5),
        (" 5m ", 5 * 60),
    ],
)
def test_parse_duration_valid(text: str, seconds: float):
    assert parse_duration(text) == timedelta(seconds=seconds)


@pytest.mark.parametrize("text", ["", "  ", "abc", "5", "5x", "5m3", "-5m"])
def test_parse_duration_invalid(text: str):
    with pytest.raises(ValueError):
        parse_duration(text)


def _at(minute: int) -> datetime:
    return datetime(2026, 8, 10, 12, minute, 0, tzinfo=timezone.utc)


def test_immediate_strategy_keeps_only_current():
    strategy = ImmediatePruneStrategy()
    last_seen = {"a": _at(0), "b": _at(5)}
    current = frozenset(["a"])
    assert strategy.live_slots(last_seen, current, _at(10)) == {"a"}


def test_immediate_strategy_empty_current():
    strategy = ImmediatePruneStrategy()
    last_seen = {"a": _at(0)}
    assert strategy.live_slots(last_seen, frozenset(), _at(10)) == set()


def test_ttl_strategy_keeps_within_ttl():
    strategy = TTLPruneStrategy(timedelta(minutes=10))
    last_seen = {"fresh": _at(5), "stale": _at(0)}
    # now=12:11 → cutoff=12:01 → "stale" (12:00) expired, "fresh" (12:05) live
    assert strategy.live_slots(last_seen, frozenset(), _at(11)) == {"fresh"}


def test_ttl_strategy_ignores_current():
    # TTLPruneStrategy decides solely from timestamps, not from current
    strategy = TTLPruneStrategy(timedelta(minutes=10))
    last_seen = {"a": _at(5)}
    assert strategy.live_slots(last_seen, frozenset(), _at(10)) == {"a"}
    assert strategy.live_slots(last_seen, frozenset(["a"]), _at(10)) == {"a"}


def _ttl_store(tmp_path: Path, ttl_minutes: int, clock) -> TTLFileStateStore:
    return TTLFileStateStore(
        tmp_path / "state.json",
        TTLPruneStrategy(timedelta(minutes=ttl_minutes)),
        clock=clock,
    )


def test_ttl_store_roundtrip(tmp_path: Path):
    store = _ttl_store(tmp_path, 10, lambda: _at(0))
    store.save("k", frozenset(["s1", "s2"]))
    assert store.load("k") == frozenset(["s1", "s2"])


def test_ttl_store_absent_slots_not_dropped_within_ttl(tmp_path: Path):
    """Slots that disappear within the TTL remain in stored state — no re-notification.

    Mirrors the real-world case: 7 slots seen at hour 0, 6 get booked away by hour 1,
    only s1 remains. With a 2-hour TTL the booked-away slots are still within TTL and
    should remain in the stored set so no spurious re-notification fires.
    """
    t0 = datetime(2026, 8, 10, 5, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 10, 6, 30, 0, tzinfo=timezone.utc)
    now = {"t": t0}
    store = TTLFileStateStore(
        tmp_path / "state.json",
        TTLPruneStrategy(timedelta(hours=2)),
        clock=lambda: now["t"],
    )
    store.save("k", frozenset(["s1", "s2", "s3", "s4", "s5", "s6", "s7"]))
    now["t"] = t1  # 90 min later, 6 slots booked away
    store.save("k", frozenset(["s1"]))
    # s2..s7 last seen at t0, TTL=2h, cutoff=t1-2h=03:30 → all still live
    assert store.load("k") == frozenset(["s1", "s2", "s3", "s4", "s5", "s6", "s7"])


def test_ttl_store_absorbs_jitter(tmp_path: Path):
    """A slot that vanishes then reappears within the TTL stays 'live' throughout."""
    now = {"t": _at(0)}
    store = _ttl_store(tmp_path, 10, lambda: now["t"])

    store.save("k", frozenset(["slot"]))
    now["t"] = _at(5)
    store.save("k", frozenset())  # vanished at 12:05, within TTL
    assert store.load("k") == frozenset(["slot"])


def test_ttl_store_evicts_after_ttl(tmp_path: Path):
    now = {"t": _at(0)}
    store = _ttl_store(tmp_path, 10, lambda: now["t"])

    store.save("k", frozenset(["slot"]))
    now["t"] = _at(5)
    store.save("k", frozenset())  # vanished at 12:05
    now["t"] = _at(16)  # 12:16 → last_seen 12:00, cutoff 12:06 → expired
    assert store.load("k") == frozenset()


def test_ttl_store_reappearance_refreshes_timestamp(tmp_path: Path):
    now = {"t": _at(0)}
    store = _ttl_store(tmp_path, 10, lambda: now["t"])

    store.save("k", frozenset(["slot"]))  # 12:00
    now["t"] = _at(8)
    store.save("k", frozenset(["slot"]))  # reappeared at 12:08, refreshed
    now["t"] = _at(15)  # only 7m since refresh → still live
    assert store.load("k") == frozenset(["slot"])


def test_ttl_store_corrupt_file_returns_empty(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text("not json", encoding="utf-8")
    store = TTLFileStateStore(path, TTLPruneStrategy(timedelta(minutes=10)), clock=lambda: _at(0))
    assert store.load("k") == frozenset()


def test_immediate_store_drops_absent_slots(tmp_path: Path):
    """ImmediatePruneStrategy still drops absent slots on save()."""
    from app.state.prune import ImmediatePruneStrategy
    now = {"t": _at(0)}
    store = TTLFileStateStore(
        tmp_path / "state.json",
        ImmediatePruneStrategy(),
        clock=lambda: now["t"],
    )
    store.save("k", frozenset(["s1", "s2"]))
    now["t"] = _at(5)
    store.save("k", frozenset(["s1"]))  # s2 gone
    assert store.load("k") == frozenset(["s1"])
