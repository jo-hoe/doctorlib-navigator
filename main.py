import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

from app.checker import AppointmentChecker
from app.config import AppConfig, load_config
from app.doctolib import create_client
from app.notification import create_notifier
from app.state.store import InMemoryStateStore, StateStore, create_file_store

_RUN_MODE_JOB = "job"
_RUN_MODE_DAEMON = "daemon"
_ENV_STATE_PATH = "STATE_FILE_PATH"

logger = logging.getLogger(__name__)


def _build_state_store() -> StateStore:
    path = os.environ.get(_ENV_STATE_PATH)
    if not path:
        logger.warning("STATE_FILE_PATH not set; deduplication disabled (in-memory only)")
        return InMemoryStateStore()
    return create_file_store(path)


def build_checker(config: AppConfig, state: Optional[StateStore] = None) -> AppointmentChecker:
    client = create_client()
    notifier = create_notifier(config.notification)
    return AppointmentChecker(client=client, notifier=notifier, state=state)


def execute_once(config_path: str) -> int:
    config = load_config(config_path)
    checker = build_checker(config, _build_state_store())
    results = checker.check_all(config.doctors)
    found = sum(1 for r in results if r.has_slots)
    logger.info("Check complete: %d/%d doctors with available slots", found, len(results))
    return 0


def start_with_schedule(
    config_path: str,
    stop_event: Optional[threading.Event] = None,
) -> None:
    if stop_event is None:
        stop_event = threading.Event()
        signal.signal(signal.SIGTERM, lambda _s, _f: stop_event.set())
        signal.signal(signal.SIGINT, lambda _s, _f: stop_event.set())

    config = load_config(config_path)
    checker = build_checker(config, _build_state_store())
    interval = config.check_interval_seconds

    logger.info("Starting daemon, checking every %ds", interval)
    while not stop_event.is_set():
        try:
            checker.check_all(config.doctors)
        except Exception:
            logger.exception("Error during availability check")
        for _ in range(interval):
            if stop_event.wait(timeout=1):
                break

    logger.info("Daemon stopped")


def main(
    config_path: str = os.environ.get("CONFIG_PATH", "/run/config/config.yaml"),
    run_mode: str = os.environ.get("RUN_MODE", "daemon"),
    log_level: str = os.environ.get("LOG_LEVEL", "INFO").upper(),
) -> int:
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if run_mode == _RUN_MODE_JOB:
        try:
            return execute_once(config_path)
        except Exception:
            logger.exception("Job failed")
            return 1
    if run_mode == _RUN_MODE_DAEMON:
        try:
            start_with_schedule(config_path)
            return 0
        except Exception:
            logger.exception("Daemon failed")
            return 1
    logger.error("Unknown RUN_MODE: %s (expected: %s, %s)", run_mode, _RUN_MODE_JOB, _RUN_MODE_DAEMON)
    return 1


if __name__ == "__main__":
    sys.exit(main())
