from __future__ import annotations

import io
import sys
import threading
from typing import Any

import structlog

# Shared buffer that accumulates ALL structlog output for the log file.
_log_buffer = io.StringIO()
_log_lock = threading.Lock()


class _TeeLoggerFactory:
    """Logger factory that writes to both stderr and an in-memory buffer."""

    def __call__(self, *args: object, **kwargs: object) -> _TeeLogger:
        return _TeeLogger()


class _TeeLogger:
    """Writes each log line to stderr AND the shared _log_buffer."""

    def msg(self, message: str) -> None:
        sys.stderr.write(message + "\n")
        sys.stderr.flush()
        with _log_lock:
            _log_buffer.write(message + "\n")

    log = debug = info = warn = warning = msg
    fatal = failure = err = error = critical = exception = msg


def get_log_contents() -> str:
    """Return all accumulated structlog output and clear the buffer."""
    with _log_lock:
        contents = _log_buffer.getvalue()
        _log_buffer.seek(0)
        _log_buffer.truncate()
    return contents


def configure_logging(
    json_logs: bool | None = None, *, verbose: bool = False,
) -> None:
    """
    Configure structlog.

    - In a non-TTY environment (CI, production): emit JSON.
    - In a TTY (developer terminal): emit colored key=value.
    - All log levels (DEBUG+) are always captured in the in-memory buffer
      for the .md log file, regardless of verbose setting.
    - When verbose=True, console output includes DEBUG; otherwise INFO+.
    """
    if json_logs is None:
        json_logs = not sys.stderr.isatty()

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        renderer: structlog.types.Processor = (
            structlog.processors.JSONRenderer()
        )
    else:
        renderer = structlog.dev.ConsoleRenderer()

    console_level = 10 if verbose else 20  # DEBUG vs INFO for console

    # Always tee log lines into an in-memory buffer for the .md log file.
    # The buffer captures ALL log levels (DEBUG+) so the log file has full
    # agent conversations.  Console output respects the verbose flag.
    file_renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer(colors=False)
    )
    final_renderer: Any = _TeeFileRenderer(
        console_renderer=renderer,
        file_renderer=file_renderer,
        console_level=console_level,
    )

    # Always set DEBUG (10) so all messages reach the tee renderer.
    # The tee renderer filters console output by console_level.
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            final_renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(10),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


_LOG_LEVEL_MAP: dict[str, int] = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
    "critical": 50,
}


class _TeeFileRenderer:
    """Processor that renders to console normally AND appends plain text to the buffer.

    All log levels are always written to the in-memory buffer (for the .md log
    file).  Console output is filtered by *console_level* so that ``--verbose``
    controls terminal noise without losing detail in the log file.
    """

    def __init__(
        self,
        console_renderer: structlog.types.Processor,
        file_renderer: structlog.types.Processor,
        console_level: int = 20,
    ) -> None:
        self._console = console_renderer
        self._file = file_renderer
        self._console_level = console_level

    def __call__(
        self,
        logger: object,
        method_name: str,
        event_dict: dict[str, object],
    ) -> str:
        # Render plain text for the file buffer (must use a copy — renderers mutate)
        file_line = str(self._file(logger, method_name, dict(event_dict)))
        with _log_lock:
            _log_buffer.write(file_line + "\n")

        # Filter console output by level
        level = _LOG_LEVEL_MAP.get(str(event_dict.get("level", "info")), 20)
        if level < self._console_level:
            raise structlog.DropEvent

        # Render for console (may include ANSI colors)
        return self._console(logger, method_name, event_dict)  # type: ignore[return-value]


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
