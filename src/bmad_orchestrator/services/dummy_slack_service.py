from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)


class DummySlackService:
    """File-backed Slack mock — writes messages to a JSONL file.

    Used when ``dummy_jira=True`` for local testing.  Messages are stored
    in ``~/.bmad/dummy/slack/messages.jsonl`` (configurable via
    ``BMAD_DUMMY_DATA_DIR``).
    """

    def __init__(self, settings: Settings, base_dir: Path | None = None) -> None:
        self._base = base_dir or Path(settings.dummy_data_dir).expanduser() / "slack"
        self._base.mkdir(parents=True, exist_ok=True)
        self._file = self._base / "messages.jsonl"

    def post_message(
        self, text: str, blocks: list[dict[str, Any]] | None = None,
    ) -> str | None:
        ts = datetime.now(UTC).isoformat()
        entry = {"ts": ts, "text": text, "blocks": blocks}
        with self._file.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        logger.debug("dummy_slack_message", text=text[:100])
        return ts

    def update_message(
        self, ts: str, text: str, blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        entry = {"ts": ts, "text": text, "blocks": blocks, "updated": True}
        with self._file.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def post_thread_reply(self, thread_ts: str, text: str) -> None:
        entry = {"thread_ts": thread_ts, "text": text, "reply": True}
        with self._file.open("a") as f:
            f.write(json.dumps(entry) + "\n")
