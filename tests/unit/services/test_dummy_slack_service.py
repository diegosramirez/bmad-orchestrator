from __future__ import annotations

import json
from pathlib import Path

from bmad_orchestrator.services.dummy_slack_service import DummySlackService


def _make_service(tmp_path: Path) -> DummySlackService:
    # Bypass Settings by passing base_dir directly
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.dummy_data_dir = str(tmp_path)
    return DummySlackService(settings, base_dir=tmp_path / "slack")


def test_post_message_returns_ts(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    ts = svc.post_message("hello world")
    assert ts is not None
    assert len(ts) > 0


def test_post_message_writes_to_file(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    svc.post_message("first message")
    svc.post_message("second message", blocks=[{"type": "section"}])

    lines = (tmp_path / "slack" / "messages.jsonl").read_text().strip().split("\n")
    assert len(lines) == 2

    entry1 = json.loads(lines[0])
    assert entry1["text"] == "first message"
    assert entry1["blocks"] is None

    entry2 = json.loads(lines[1])
    assert entry2["text"] == "second message"
    assert entry2["blocks"] == [{"type": "section"}]


def test_update_message_writes_to_file(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    svc.update_message("ts123", "updated text")

    lines = (tmp_path / "slack" / "messages.jsonl").read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["ts"] == "ts123"
    assert entry["text"] == "updated text"
    assert entry["updated"] is True


def test_post_thread_reply_writes_to_file(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    svc.post_thread_reply("ts456", "thread reply")

    lines = (tmp_path / "slack" / "messages.jsonl").read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["thread_ts"] == "ts456"
    assert entry["text"] == "thread reply"
    assert entry["reply"] is True
