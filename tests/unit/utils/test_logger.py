from __future__ import annotations

from bmad_orchestrator.utils.logger import (
    _log_buffer,
    _log_lock,
    _TeeFileRenderer,
    configure_logging,
    get_log_contents,
)


def test_get_log_contents_returns_and_clears() -> None:
    """get_log_contents should return accumulated text and clear the buffer."""
    with _log_lock:
        _log_buffer.write("line one\nline two\n")

    contents = get_log_contents()
    assert "line one" in contents
    assert "line two" in contents

    # Buffer should be empty after retrieval
    assert get_log_contents() == ""


def test_tee_file_renderer_writes_to_buffer() -> None:
    """_TeeFileRenderer should append plain-text output to _log_buffer."""
    # Clear any prior state
    get_log_contents()

    def fake_console(logger: object, method: str, ed: dict) -> str:
        return f"[console] {ed.get('event', '')}"

    def fake_file(logger: object, method: str, ed: dict) -> str:
        return f"[file] {ed.get('event', '')}"

    renderer = _TeeFileRenderer(
        console_renderer=fake_console,  # type: ignore[arg-type]
        file_renderer=fake_file,  # type: ignore[arg-type]
    )
    result = renderer(None, "info", {"event": "hello"})

    assert result == "[console] hello"
    buf = get_log_contents()
    assert "[file] hello" in buf


def test_configure_logging_does_not_raise() -> None:
    """configure_logging should complete without error."""
    configure_logging(json_logs=False, verbose=True)
    configure_logging(json_logs=True, verbose=False)


def test_non_verbose_does_not_write_to_buffer() -> None:
    """When verbose=False, log messages should NOT be tee'd to the buffer."""
    get_log_contents()  # clear
    configure_logging(json_logs=False, verbose=False)

    import structlog

    logger = structlog.get_logger("test")
    logger.info("should_not_appear_in_buffer")

    buf = get_log_contents()
    assert buf == ""


def test_verbose_writes_to_buffer() -> None:
    """When verbose=True, log messages SHOULD be tee'd to the buffer."""
    get_log_contents()  # clear
    configure_logging(json_logs=False, verbose=True)

    import structlog

    logger = structlog.get_logger("test")
    logger.info("should_appear_in_buffer")

    buf = get_log_contents()
    assert "should_appear_in_buffer" in buf
