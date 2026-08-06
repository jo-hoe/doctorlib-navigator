import logging
import os
import signal
import sys
import time

from app.checker import AppointmentChecker
from app.config import load_config
from app.doctolib import create_client
from app.notification import create_notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/run/config/config.yaml")
RUN_MODE = os.environ.get("RUN_MODE", "daemon")

_running = True


def signal_handler(signum: int, frame: object) -> None:
    global _running
    logger.info("Received signal %d, shutting down", signum)
    _running = False


def build_checker(config_path: str) -> AppointmentChecker:
    config = load_config(config_path)
    client = create_client()
    notifier = create_notifier(config.notification)
    return AppointmentChecker(client=client, notifier=notifier)


def execute_once(config_path: str) -> int:
    config = load_config(config_path)
    checker = build_checker(config_path)
    results = checker.check_all(config.doctors)
    found = sum(1 for r in results if r.has_slots)
    logger.info("Check complete: %d/%d doctors with available slots", found, len(results))
    return 0


def start_with_schedule(config_path: str) -> None:
    config = load_config(config_path)
    checker = build_checker(config_path)
    interval = config.check_interval_seconds

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("Starting daemon, checking every %ds", interval)
    while _running:
        try:
            checker.check_all(config.doctors)
        except Exception:
            logger.exception("Error during availability check")
        for _ in range(interval):
            if not _running:
                break
            time.sleep(1)

    logger.info("Daemon stopped")


def main() -> int:
    if RUN_MODE == "job":
        try:
            return execute_once(CONFIG_PATH)
        except Exception:
            logger.exception("Job failed")
            return 1
    elif RUN_MODE == "daemon":
        try:
            start_with_schedule(CONFIG_PATH)
            return 0
        except Exception:
            logger.exception("Daemon failed")
            return 1
    else:
        logger.error("Unknown RUN_MODE: %s (expected: job, daemon)", RUN_MODE)
        return 1


if __name__ == "__main__":
    sys.exit(main())
