import json
import pytest
from pathlib import Path

from app.state.store import FileStateStore, InMemoryStateStore, sanitise_key


def test_in_memory_load_empty():
    store = InMemoryStateStore()
    assert store.load("key") == frozenset()


def test_in_memory_save_and_load():
    store = InMemoryStateStore()
    store.save("key", frozenset(["a", "b"]))
    assert store.load("key") == frozenset(["a", "b"])


def test_in_memory_initial_state():
    store = InMemoryStateStore({"key": frozenset(["x"])})
    assert store.load("key") == frozenset(["x"])


def test_file_store_load_missing(tmp_path: Path):
    store = FileStateStore(tmp_path / "state.json")
    assert store.load("key") == frozenset()


def test_file_store_save_and_load(tmp_path: Path):
    store = FileStateStore(tmp_path / "state.json")
    store.save("dr_example", frozenset(["2026-08-10T09:00:00", "2026-08-11T09:00:00"]))
    assert store.load("dr_example") == frozenset(["2026-08-10T09:00:00", "2026-08-11T09:00:00"])


def test_file_store_multiple_keys(tmp_path: Path):
    store = FileStateStore(tmp_path / "state.json")
    store.save("doctor_a", frozenset(["slot1"]))
    store.save("doctor_b", frozenset(["slot2"]))
    assert store.load("doctor_a") == frozenset(["slot1"])
    assert store.load("doctor_b") == frozenset(["slot2"])


def test_file_store_update_key(tmp_path: Path):
    store = FileStateStore(tmp_path / "state.json")
    store.save("key", frozenset(["old"]))
    store.save("key", frozenset(["new"]))
    assert store.load("key") == frozenset(["new"])


def test_file_store_corrupt_file_returns_empty(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text("not json", encoding="utf-8")
    store = FileStateStore(path)
    assert store.load("key") == frozenset()


def test_file_store_sorted_on_disk(tmp_path: Path):
    store = FileStateStore(tmp_path / "state.json")
    store.save("key", frozenset(["c", "a", "b"]))
    data = json.loads((tmp_path / "state.json").read_text())
    assert data["key"] == ["a", "b", "c"]


def test_sanitise_key_replaces_spaces():
    assert sanitise_key("Dr. Example Berlin") == "Dr._Example_Berlin"


def test_sanitise_key_truncates():
    assert len(sanitise_key("a" * 300)) == 253
