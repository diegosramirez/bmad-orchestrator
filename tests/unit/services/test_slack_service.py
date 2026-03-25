from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.slack_service import SlackService


def _make_settings(*, dry_run: bool = False, channel: str = "#test") -> Settings:
    return Settings(
        anthropic_api_key="test-key",  # type: ignore[arg-type]
        jira_base_url="https://test.atlassian.net",
        jira_username="test@test.com",
        jira_api_token="test-token",  # type: ignore[arg-type]
        jira_project_key="TEST",
        github_repo="org/repo",
        dry_run=dry_run,
        slack_notify=True,
        slack_bot_token="xoxb-test-token",  # type: ignore[arg-type]
        slack_channel=channel,
    )


def _mock_urlopen(response_json: dict) -> MagicMock:
    """Create a mock urlopen that returns the given JSON."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_json).encode()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestPostMessage:
    @patch("bmad_orchestrator.services.slack_service.urllib.request.urlopen")
    def test_posts_to_chat_post_message(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_urlopen({"ok": True, "ts": "1234.5678"})

        svc = SlackService(_make_settings())
        ts = svc.post_message("hello")

        assert ts == "1234.5678"
        req = mock_urlopen.call_args[0][0]
        assert "chat.postMessage" in req.full_url
        assert req.get_header("Authorization") == "Bearer xoxb-test-token"
        payload = json.loads(req.data)
        assert payload["channel"] == "#test"
        assert payload["text"] == "hello"

    @patch("bmad_orchestrator.services.slack_service.urllib.request.urlopen")
    def test_includes_blocks(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_urlopen({"ok": True, "ts": "1234.5678"})

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}]
        svc = SlackService(_make_settings())
        svc.post_message("fallback", blocks=blocks)

        payload = json.loads(mock_urlopen.call_args[0][0].data)
        assert payload["blocks"] == blocks

    @patch("bmad_orchestrator.services.slack_service.urllib.request.urlopen")
    def test_returns_none_on_api_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_urlopen({"ok": False, "error": "channel_not_found"})

        svc = SlackService(_make_settings())
        ts = svc.post_message("hello")
        assert ts is None

    def test_skipped_in_dry_run(self) -> None:
        svc = SlackService(_make_settings(dry_run=True))
        result = svc.post_message("should not send")
        assert result is None

    @patch(
        "bmad_orchestrator.services.slack_service.urllib.request.urlopen",
        side_effect=Exception("network error"),
    )
    def test_swallows_exceptions(self, mock_urlopen: MagicMock) -> None:
        svc = SlackService(_make_settings())
        result = svc.post_message("hello")
        assert result is None


class TestUpdateMessage:
    @patch("bmad_orchestrator.services.slack_service.urllib.request.urlopen")
    def test_calls_chat_update(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_urlopen({"ok": True})

        svc = SlackService(_make_settings())
        svc.update_message("1234.5678", "updated text")

        req = mock_urlopen.call_args[0][0]
        assert "chat.update" in req.full_url
        payload = json.loads(req.data)
        assert payload["ts"] == "1234.5678"
        assert payload["text"] == "updated text"


class TestPostThreadReply:
    @patch("bmad_orchestrator.services.slack_service.urllib.request.urlopen")
    def test_posts_with_thread_ts(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_urlopen({"ok": True})

        svc = SlackService(_make_settings())
        svc.post_thread_reply("1234.5678", "thread reply")

        req = mock_urlopen.call_args[0][0]
        assert "chat.postMessage" in req.full_url
        payload = json.loads(req.data)
        assert payload["thread_ts"] == "1234.5678"
        assert payload["text"] == "thread reply"


def test_config_requires_bot_token_and_channel_when_notify_true() -> None:
    with pytest.raises(ValueError, match="slack_bot_token"):
        Settings(
            anthropic_api_key="test-key",  # type: ignore[arg-type]
            jira_base_url="https://test.atlassian.net",
            jira_username="test@test.com",
            jira_api_token="test-token",  # type: ignore[arg-type]
            jira_project_key="TEST",
            github_repo="org/repo",
            slack_notify=True,
        )


def test_config_requires_channel_when_notify_true() -> None:
    with pytest.raises(ValueError, match="slack_channel"):
        Settings(
            anthropic_api_key="test-key",  # type: ignore[arg-type]
            jira_base_url="https://test.atlassian.net",
            jira_username="test@test.com",
            jira_api_token="test-token",  # type: ignore[arg-type]
            jira_project_key="TEST",
            github_repo="org/repo",
            slack_notify=True,
            slack_bot_token="xoxb-test",  # type: ignore[arg-type]
            # slack_channel intentionally omitted
        )
