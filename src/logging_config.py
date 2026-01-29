"""
Structured Logging Configuration

Provides JSON-formatted logging for production use and text format for development.
Integrates with the application's settings to determine log format and level.

Usage:
    from src.logging_config import setup_logging

    # In application startup
    setup_logging()

    # Then use standard logging
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Message", extra={"key": "value"})
"""

import logging
import sys
from datetime import datetime, timedelta, timezone

try:
    from pythonjsonlogger import jsonlogger

    HAS_JSON_LOGGER = True
except ImportError:
    HAS_JSON_LOGGER = False

# Japan Standard Time
JST = timezone(timedelta(hours=9))


class JSTFormatter(logging.Formatter):
    """Formatter that uses JST timezone."""

    def formatTime(self, record, datefmt=None):
        ct = datetime.fromtimestamp(record.created, tz=JST)
        if datefmt:
            return ct.strftime(datefmt)
        return ct.isoformat()


class CustomJsonFormatter(jsonlogger.JsonFormatter if HAS_JSON_LOGGER else object):
    """
    Custom JSON formatter with JST timezone and additional fields.

    Output example:
    {
        "timestamp": "2025-01-30T15:00:00+09:00",
        "level": "INFO",
        "logger": "src.api.main",
        "message": "API started",
        "service": "keiba-yosou"
    }
    """

    def __init__(self, *args, **kwargs):
        if HAS_JSON_LOGGER:
            super().__init__(*args, **kwargs)
        self.service_name = "keiba-yosou"

    def add_fields(self, log_record, record, message_dict):
        if HAS_JSON_LOGGER:
            super().add_fields(log_record, record, message_dict)

        # Add timestamp in JST
        log_record["timestamp"] = datetime.fromtimestamp(record.created, tz=JST).isoformat()

        # Add standard fields
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["service"] = self.service_name

        # Add location info for errors
        if record.levelno >= logging.ERROR:
            log_record["file"] = record.pathname
            log_record["line"] = record.lineno
            log_record["function"] = record.funcName

        # Move message to end for readability
        if "message" in log_record:
            msg = log_record.pop("message")
            log_record["message"] = msg


def get_text_formatter() -> logging.Formatter:
    """Get text formatter for development."""
    return JSTFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_json_formatter() -> logging.Formatter:
    """Get JSON formatter for production."""
    if not HAS_JSON_LOGGER:
        logging.warning(
            "python-json-logger not installed, falling back to text format. "
            "Install with: pip install python-json-logger"
        )
        return get_text_formatter()

    return CustomJsonFormatter(fmt="%(timestamp)s %(level)s %(logger)s %(message)s")


def setup_logging(
    level: str | None = None,
    format_type: str | None = None,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to settings.log_level or INFO.
        format_type: Log format ('json' or 'text').
                     Defaults to settings.log_format or 'text'.

    Example:
        # Production (JSON logs)
        setup_logging(level="INFO", format_type="json")

        # Development (text logs)
        setup_logging(level="DEBUG", format_type="text")
    """
    # Try to get settings, fallback to defaults
    try:
        from src.settings import settings

        level = level or settings.log_level
        format_type = format_type or settings.log_format
    except Exception:
        level = level or "INFO"
        format_type = format_type or "text"

    # Get appropriate formatter
    if format_type.lower() == "json":
        formatter = get_json_formatter()
    else:
        formatter = get_text_formatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Add stdout handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Set level
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Convenience function that ensures logging is configured.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


if __name__ == "__main__":
    # Test logging configuration
    print("=== Text Format ===")
    setup_logging(level="DEBUG", format_type="text")
    logger = get_logger("test")
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")

    print("\n=== JSON Format ===")
    setup_logging(level="DEBUG", format_type="json")
    logger = get_logger("test")
    logger.info("JSON formatted message", extra={"user_id": 123, "action": "test"})
    logger.error("Error with context", extra={"error_code": "E001"})
