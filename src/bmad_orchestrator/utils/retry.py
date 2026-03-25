from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from typing import TypeVar

from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def retry_on_subprocess_error(
    fn: Callable[[], T],
    *,
    max_attempts: int = 2,
    delay_seconds: float = 3.0,
    label: str = "",
) -> T:
    """Call *fn* up to *max_attempts* times, retrying on CalledProcessError.

    Only retries once (max_attempts=2 means 1 retry).  Intended for
    transient network failures on git push / gh pr create.
    """
    last_exc: subprocess.CalledProcessError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except subprocess.CalledProcessError as exc:
            last_exc = exc
            if attempt < max_attempts:
                logger.warning(
                    "retrying_after_failure",
                    label=label,
                    attempt=attempt,
                    stderr=(exc.stderr or "")[:200],
                )
                time.sleep(delay_seconds)
    assert last_exc is not None  # noqa: S101 — for type checker
    raise last_exc
