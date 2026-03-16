from __future__ import annotations

from bmad_orchestrator.utils.logger import configure_logging, get_logger


def test_configure_logging_json_mode():
    configure_logging(json_logs=True)
    assert get_logger("test") is not None


def test_configure_logging_console_mode():
    configure_logging(json_logs=False)
    assert get_logger("test") is not None


def test_get_logger_returns_bound_logger():
    logger = get_logger("bmad_orchestrator.test")
    assert logger is not None
