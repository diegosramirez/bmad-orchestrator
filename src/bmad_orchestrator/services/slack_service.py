from __future__ import annotations

import json
import urllib.request
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.dry_run import skip_if_dry_run
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

_SLACK_API = "https://slack.com/api"


class SlackService:
    """Post messages to Slack via the Web API (Bot Token).

    Supports threading: ``post_message`` returns the message ``ts``
    which can be passed to ``post_thread_reply`` for threaded replies.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        token = settings.slack_bot_token
        self._token: str = token.get_secret_value() if token else ""
        self._channel: str = settings.slack_channel or ""

    @skip_if_dry_run(fake_return=None)
    def post_message(
        self, text: str, blocks: list[dict[str, Any]] | None = None,
    ) -> str | None:
        """Post a new message to the channel. Returns the message ts for threading."""
        payload: dict[str, Any] = {
            "channel": self._channel,
            "text": text,
        }
        if blocks:
            payload["blocks"] = blocks
        data = self._api_call("chat.postMessage", payload)
        if data and data.get("ok"):
            return data.get("ts")
        return None

    @skip_if_dry_run(fake_return=None)
    def update_message(
        self, ts: str, text: str, blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        """Update an existing message by ts."""
        payload: dict[str, Any] = {
            "channel": self._channel,
            "ts": ts,
            "text": text,
        }
        if blocks:
            payload["blocks"] = blocks
        self._api_call("chat.update", payload)

    @skip_if_dry_run(fake_return=None)
    def post_thread_reply(self, thread_ts: str, text: str) -> None:
        """Post a reply in a thread."""
        payload: dict[str, Any] = {
            "channel": self._channel,
            "thread_ts": thread_ts,
            "text": text,
        }
        self._api_call("chat.postMessage", payload)

    def _api_call(self, method: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST to Slack Web API. Never raises — returns parsed JSON or None."""
        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{_SLACK_API}/{method}",
                data=data,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {self._token}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                body = json.loads(resp.read().decode())
            if not body.get("ok"):
                logger.warning(
                    "slack_api_error", method=method, error=body.get("error", "unknown"),
                )
            else:
                logger.debug("slack_api_ok", method=method)
            return body
        except Exception:
            logger.warning("slack_api_failed", method=method, exc_info=True)
            return None
