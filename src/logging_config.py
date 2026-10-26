import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


_APP_LOGGER_NAME = "smart_invoice_parser"
_LOG_DIRECTORY = Path(__file__).resolve().parents[1] / "logs"


def _get_file_logger(name: str, file_name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        _LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            _LOG_DIRECTORY / file_name,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def get_app_logger() -> logging.Logger:
    logger = _get_file_logger(_APP_LOGGER_NAME, "app.log")
    for handler in logger.handlers:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        ))
    return logger


def log_activity(
    action: str,
    *,
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    status: str | None = None,
) -> None:
    """Write a minimal, non-secret user activity event to app.log."""
    event = {
        "action": action,
        "user_id": user_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "status": status,
    }
    get_app_logger().info(
        "ACTIVITY %s",
        json.dumps(
            {key: value for key, value in event.items() if value is not None},
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    )
