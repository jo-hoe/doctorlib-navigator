import json
import logging
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

_KEY_MAX_LEN = 253
_KEY_SANITISE = re.compile(r"[^a-zA-Z0-9._-]")


@runtime_checkable
class StateStore(Protocol):
    def load(self, key: str) -> frozenset[str]: ...
    def save(self, key: str, slots: frozenset[str]) -> None: ...


class InMemoryStateStore:
    def __init__(self, initial: dict[str, frozenset[str]] | None = None) -> None:
        self._data: dict[str, frozenset[str]] = dict(initial or {})

    def load(self, key: str) -> frozenset[str]:
        return self._data.get(key, frozenset())

    def save(self, key: str, slots: frozenset[str]) -> None:
        self._data[key] = slots


class FileStateStore:
    """Stores slot fingerprints as a JSON file on a PersistentVolume."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def _read(self) -> dict[str, list[str]]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("State file %s unreadable, starting fresh", self._path)
            return {}

    def _write(self, data: dict[str, list[str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self, key: str) -> frozenset[str]:
        return frozenset(self._read().get(key, []))

    def save(self, key: str, slots: frozenset[str]) -> None:
        data = self._read()
        data[key] = sorted(slots)
        self._write(data)


def sanitise_key(name: str) -> str:
    key = _KEY_SANITISE.sub("_", name)
    return key[:_KEY_MAX_LEN]


def create_file_store(state_path: str) -> FileStateStore:
    return FileStateStore(Path(state_path))
