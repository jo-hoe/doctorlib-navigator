import logging
import os
import sys

from app.checker import AppointmentChecker
from app.config import AppConfig, load_config
from app.doctolib import create_client
from app.notification import create_notifier
from app.state.store import InMemoryStateStore, StateStore, create_file_store

_ENV_STATE_PATH = "STATE_FILE_PATH"

logger = logging.getLogger(__name__)


def _build_state_store() -> StateStore:
    path = os.environ.get(_ENV_STATE_PATH)
    if not path:
        logger.warning("STATE_FILE_PATH not set; deduplication disabled (in-memory only)")
        return InMemoryStateStore()
    return create_file_store(path)


def build_checker(config: AppConfig, state: StateStore | None = None) -> AppointmentChecker:
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


def main(
    config_path: str = os.environ.get("CONFIG_PATH", "/run/config/config.yaml"),
    log_level: str = os.environ.get("LOG_LEVEL", "INFO").upper(),
) -> int:
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        return execute_once(config_path)
    except Exception:
        logger.exception("Job failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
