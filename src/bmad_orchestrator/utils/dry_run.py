from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def skip_if_dry_run(fake_return: Any = None) -> Callable[[F], F]:
    """
    Decorator for service methods that have side effects.

    When settings.dry_run is True:
    - Logs the would-be call with its arguments.
    - Returns fake_return instead of executing the function body.

    Usage::

        class JiraService:
            @skip_if_dry_run(fake_return={"key": "DRY-001", "id": "0"})
            def create_epic(self, summary: str, description: str) -> dict:
                ...
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            if getattr(getattr(self, "settings", None), "dry_run", False):
                logger.info(
                    "dry_run_skip",
                    method=fn.__qualname__,
                    args=args,
                    kwargs=kwargs,
                    fake_return=fake_return,
                )
                return fake_return
            return fn(self, *args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
