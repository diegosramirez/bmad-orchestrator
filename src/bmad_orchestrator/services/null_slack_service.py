from __future__ import annotations

from typing import Any


class NullSlackService:
    """Silent no-op Slack service used when ``slack_notify=False``."""

    def post_message(
        self, text: str, blocks: list[dict[str, Any]] | None = None,
    ) -> str | None:
        return None

    def update_message(
        self, ts: str, text: str, blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        pass

    def post_thread_reply(self, thread_ts: str, text: str) -> None:
        pass
