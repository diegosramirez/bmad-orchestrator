from __future__ import annotations

from bmad_orchestrator.services.null_slack_service import NullSlackService


def test_post_message_returns_none() -> None:
    svc = NullSlackService()
    assert svc.post_message("hello") is None


def test_post_message_with_blocks_returns_none() -> None:
    svc = NullSlackService()
    assert svc.post_message("hello", blocks=[{"type": "section"}]) is None


def test_update_message_is_noop() -> None:
    svc = NullSlackService()
    svc.update_message("ts123", "updated")  # should not raise


def test_post_thread_reply_is_noop() -> None:
    svc = NullSlackService()
    svc.post_thread_reply("ts123", "reply")  # should not raise
