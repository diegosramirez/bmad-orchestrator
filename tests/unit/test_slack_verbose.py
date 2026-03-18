from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from bmad_orchestrator.config import Settings
from bmad_orchestrator.graph import _make_verbose_callback, _wrap_with_slack_notifications


class TestMakeVerboseCallback:
    """Tests for _make_verbose_callback in graph.py."""

    def _make_settings(self, **overrides: object) -> Settings:
        base = {
            "anthropic_api_key": "sk-test",
            "dummy_jira": True,
            "dummy_github": True,
            "slack_notify": True,
            "slack_bot_token": "xoxb-test",
            "slack_channel": "#test",
            "slack_verbose": True,
        }
        base.update(overrides)
        return Settings(**base)  # type: ignore[arg-type]

    def test_posts_to_thread_when_verbose(self) -> None:
        slack = MagicMock()
        settings = self._make_settings()
        holder: list[str | None] = ["ts123"]
        cb = _make_verbose_callback(slack, settings, holder)
        cb("hello")
        slack.post_thread_reply.assert_called_once_with("ts123", "hello")

    def test_noop_when_verbose_disabled(self) -> None:
        slack = MagicMock()
        settings = self._make_settings(slack_verbose=False)
        holder: list[str | None] = ["ts123"]
        cb = _make_verbose_callback(slack, settings, holder)
        cb("hello")
        slack.post_thread_reply.assert_not_called()

    def test_noop_when_slack_notify_disabled(self) -> None:
        slack = MagicMock()
        settings = self._make_settings(
            slack_notify=False, slack_bot_token=None, slack_channel=None,
        )
        holder: list[str | None] = ["ts123"]
        cb = _make_verbose_callback(slack, settings, holder)
        cb("hello")
        slack.post_thread_reply.assert_not_called()

    def test_noop_when_no_thread_ts(self) -> None:
        slack = MagicMock()
        settings = self._make_settings()
        holder: list[str | None] = [None]
        cb = _make_verbose_callback(slack, settings, holder)
        cb("hello")
        slack.post_thread_reply.assert_not_called()

    def test_swallows_exceptions(self) -> None:
        slack = MagicMock()
        slack.post_thread_reply.side_effect = RuntimeError("Slack down")
        settings = self._make_settings()
        holder: list[str | None] = ["ts123"]
        cb = _make_verbose_callback(slack, settings, holder)
        # Should NOT raise
        cb("hello")
        slack.post_thread_reply.assert_called_once()

    def test_holder_updates_reflected(self) -> None:
        """Callback reads from the mutable holder, so later updates take effect."""
        slack = MagicMock()
        settings = self._make_settings()
        holder: list[str | None] = [None]
        cb = _make_verbose_callback(slack, settings, holder)
        cb("first")  # holder is None → no call
        slack.post_thread_reply.assert_not_called()

        holder[0] = "ts456"
        cb("second")
        slack.post_thread_reply.assert_called_once_with("ts456", "second")


class TestWrapWithSlackNotificationsCrash:
    """Tests for exception handling in _wrap_with_slack_notifications."""

    def _make_settings(self, **overrides: object) -> Settings:
        base = {
            "anthropic_api_key": "sk-test",
            "dummy_jira": True,
            "dummy_github": True,
            "slack_notify": True,
            "slack_bot_token": "xoxb-test",
            "slack_channel": "#test",
        }
        base.update(overrides)
        return Settings(**base)  # type: ignore[arg-type]

    def test_crash_posts_to_thread_and_reraises(self) -> None:
        """When node_fn raises, error is posted to thread and exception propagates."""
        slack = MagicMock()
        settings = self._make_settings()

        def crashing_node(state: dict) -> dict:
            raise RuntimeError("node exploded")

        wrapped = _wrap_with_slack_notifications(
            slack, settings, "dev_story", crashing_node, [None],
        )
        state = {"slack_thread_ts": "ts123", "team_id": "SAM1", "input_prompt": "test"}

        with pytest.raises(RuntimeError, match="node exploded"):
            wrapped(state)

        slack.post_thread_reply.assert_called_once()
        call_args = slack.post_thread_reply.call_args
        assert call_args[0][0] == "ts123"
        assert "crashed" in call_args[0][1]
        assert "node exploded" in call_args[0][1]

    def test_crash_posts_root_message_when_no_thread(self) -> None:
        """When node crashes before any thread exists, post_message is used."""
        slack = MagicMock()
        settings = self._make_settings()

        def crashing_node(state: dict) -> dict:
            raise ValueError("bad input")

        wrapped = _wrap_with_slack_notifications(
            slack, settings, "check_epic_state", crashing_node, [None],
        )
        state = {"team_id": "SAM1", "input_prompt": "test prompt"}

        with pytest.raises(ValueError, match="bad input"):
            wrapped(state)

        slack.post_message.assert_called_once()
        msg = slack.post_message.call_args[0][0]
        assert "crashed" in msg
        assert "SAM1" in msg


class TestWrapWithSlackNotificationsRefine:
    """Tests for the Refine button on PR success messages."""

    def _make_settings(self, **overrides: object) -> Settings:
        base = {
            "anthropic_api_key": "sk-test",
            "dummy_jira": True,
            "dummy_github": True,
            "slack_notify": True,
            "slack_bot_token": "xoxb-test",
            "slack_channel": "#test",
        }
        base.update(overrides)
        return Settings(**base)  # type: ignore[arg-type]

    def test_pr_success_includes_refine_button(self) -> None:
        """When pr_url is set and branch exists, blocks include a Refine button."""
        import json

        slack = MagicMock()
        slack.post_thread_reply = MagicMock()
        settings = self._make_settings()

        def success_node(state: dict) -> dict:
            return {
                "pr_url": "https://github.com/org/repo/pull/42",
                "branch_name": "bmad/sam1/SAM1-99-feature",
            }

        wrapped = _wrap_with_slack_notifications(
            slack, settings, "create_pull_request", success_node, [None],
        )
        state = {
            "slack_thread_ts": "ts123",
            "team_id": "SAM1",
            "input_prompt": "test",
            "current_story_id": "SAM1-99",
            "branch_name": "bmad/sam1/SAM1-99-feature",
        }
        wrapped(state)

        slack.post_thread_reply.assert_called_once()
        call_args = slack.post_thread_reply.call_args
        blocks = call_args.kwargs.get("blocks")
        assert blocks is not None, "Expected blocks with Refine button"
        action_elements = blocks[1]["elements"]
        assert action_elements[0]["action_id"] == "bmad_refine"
        meta = json.loads(action_elements[0]["value"])
        assert meta["branch"] == "bmad/sam1/SAM1-99-feature"
        assert meta["team_id"] == "SAM1"

    def test_pr_success_no_refine_without_branch(self) -> None:
        """When pr_url is set but no branch, no blocks are sent."""
        slack = MagicMock()
        slack.post_thread_reply = MagicMock()
        settings = self._make_settings()

        def success_node(state: dict) -> dict:
            return {"pr_url": "https://github.com/org/repo/pull/42"}

        wrapped = _wrap_with_slack_notifications(
            slack, settings, "create_pull_request", success_node, [None],
        )
        state = {
            "slack_thread_ts": "ts123",
            "team_id": "SAM1",
            "input_prompt": "test",
        }
        wrapped(state)

        slack.post_thread_reply.assert_called_once()
        call_args = slack.post_thread_reply.call_args
        # blocks should be None (no branch → no refine button)
        blocks = call_args.kwargs.get("blocks")
        assert blocks is None


class TestWrapWithSlackNotificationsThreading:
    """Tests for Slack thread creation and continuation."""

    def _make_settings(self, **overrides: object) -> Settings:
        base = {
            "anthropic_api_key": "sk-test",
            "dummy_jira": True,
            "dummy_github": True,
            "slack_notify": True,
            "slack_bot_token": "xoxb-test",
            "slack_channel": "#test",
        }
        base.update(overrides)
        return Settings(**base)  # type: ignore[arg-type]

    def test_empty_string_thread_ts_treated_as_none(self) -> None:
        """Empty string slack_thread_ts should create a root message, not a thread reply."""
        slack = MagicMock()
        slack.post_message.return_value = "new-ts-123"
        settings = self._make_settings()

        def ok_node(state: dict) -> dict:
            return {}

        wrapped = _wrap_with_slack_notifications(
            slack, settings, "check_epic_state", ok_node, [None],
        )
        # Simulate state with empty string thread_ts (from workflow default "")
        state = {"slack_thread_ts": "", "team_id": "SAM1", "input_prompt": "test"}
        result = wrapped(state)

        # Should post a root message, NOT a thread reply
        slack.post_message.assert_called_once()
        slack.post_thread_reply.assert_not_called()
        assert result["slack_thread_ts"] == "new-ts-123"

    def test_first_node_creates_root_and_second_threads(self) -> None:
        """First node posts root message; second node posts thread reply."""
        slack = MagicMock()
        slack.post_message.return_value = "root-ts"
        settings = self._make_settings()

        def ok_node(state: dict) -> dict:
            return {}

        holder: list[str | None] = [None]
        wrapped1 = _wrap_with_slack_notifications(
            slack, settings, "check_epic_state", ok_node, holder,
        )
        wrapped2 = _wrap_with_slack_notifications(
            slack, settings, "create_or_correct_epic", ok_node, holder,
        )

        # First node — no thread yet
        state1 = {"team_id": "SAM1", "input_prompt": "test"}
        result1 = wrapped1(state1)
        assert result1["slack_thread_ts"] == "root-ts"
        slack.post_message.assert_called_once()

        # Second node — thread_ts propagated via state
        state2 = {**state1, "slack_thread_ts": "root-ts"}
        wrapped2(state2)
        slack.post_thread_reply.assert_called_once()
        assert slack.post_thread_reply.call_args[0][0] == "root-ts"
