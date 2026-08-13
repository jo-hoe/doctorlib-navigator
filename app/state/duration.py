import re
from datetime import timedelta

# Kubernetes-style compact durations: "1s", "23m", "2h", "1h30m", "500ms".
_DURATION_TOKEN = re.compile(r"(\d+)(ms|s|m|h|d)")
_UNIT_SECONDS = {
    "ms": 0.001,
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}


def parse_duration(value: str) -> timedelta:
    """Parse a k8s-style duration string (e.g. "1s", "23m", "1h30m") into a timedelta.

    Raises ValueError on empty or malformed input.
    """
    text = value.strip()
    if not text:
        raise ValueError("duration must not be empty")
    matches = _DURATION_TOKEN.findall(text)
    consumed = "".join(f"{n}{u}" for n, u in matches)
    if not matches or consumed != text:
        raise ValueError(f"invalid duration: {value!r}")
    seconds = sum(int(n) * _UNIT_SECONDS[u] for n, u in matches)
    return timedelta(seconds=seconds)
