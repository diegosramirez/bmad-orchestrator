from __future__ import annotations

from bmad_orchestrator.nodes.code_review import make_review_router
from tests.conftest import make_state

_HIGH = {
    "severity": "high", "file": "f.py",
    "line": 1, "description": "x", "fix_required": True,
}
_CRITICAL = {
    "severity": "critical", "file": "f.py",
    "line": 1, "description": "y", "fix_required": True,
}
_MEDIUM = {
    "severity": "medium", "file": "f.py",
    "line": 1, "description": "z", "fix_required": True,
}
_LOW = {
    "severity": "low", "file": "f.py",
    "line": 1, "description": "style", "fix_required": False,
}


# ── Progressive leniency: loop 0 = medium+, loop 1 = high+, loop 2+ = critical ─


def test_router_loop0_medium_triggers_fix(settings):
    """Loop 0: medium+ issues trigger a fix loop."""
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=0,
        code_review_issues=[_MEDIUM],
    )
    assert router(state) == "dev_story_fix_loop"


def test_router_loop0_high_triggers_fix(settings):
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=0,
        code_review_issues=[_HIGH],
    )
    assert router(state) == "dev_story_fix_loop"


def test_router_loop1_high_triggers_fix(settings):
    """Loop 1: high+ still triggers a fix loop."""
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=1,
        code_review_issues=[_HIGH],
    )
    assert router(state) == "dev_story_fix_loop"


def test_router_loop1_medium_commits(settings):
    """Loop 1: medium issues no longer block — progressive leniency."""
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=1,
        code_review_issues=[_MEDIUM],
    )
    assert router(state) == "commit_and_push"


def test_router_loop1_critical_triggers_fix(settings):
    """Loop 1: only high+ issues trigger another fix loop (progressive leniency)."""
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=1,
        code_review_issues=[_CRITICAL],
    )
    assert router(state) == "dev_story_fix_loop"


def test_router_at_max_loops_no_blocking_commits(settings):
    """At max loops with only non-blocking issues → commit."""
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=2,
        code_review_issues=[_HIGH],  # high is not blocking at loop 2 (critical only)
    )
    assert router(state) == "commit_and_push"


def test_router_fail_at_max_loops(settings):
    # max_review_loops == 2; at loop 2 only critical blocks, and it fails
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=2,
        code_review_issues=[_CRITICAL],
    )
    assert router(state) == "fail_with_state"


def test_router_commit_when_only_low_issues(settings):
    router = make_review_router(settings)
    state = make_state(
        review_loop_count=0,
        code_review_issues=[_LOW],
    )
    assert router(state) == "commit_and_push"


def test_router_commit_when_no_issues(settings):
    router = make_review_router(settings)
    assert router(make_state()) == "commit_and_push"


def test_build_graph_does_not_raise(settings):
    """Smoke test: build_graph() completes without errors."""
    from bmad_orchestrator.graph import build_graph
    graph, checkpointer, _ = build_graph(settings)
    assert graph is not None


def test_build_graph_with_skip_nodes(settings):
    """Smoke test: build_graph() works with skip_nodes configured."""
    from bmad_orchestrator.graph import build_graph
    skip_settings = settings.model_copy(update={"skip_nodes": ["qa_automation", "code_review"]})
    graph, _, _ = build_graph(skip_settings)
    assert graph is not None


def test_skip_node_returns_log_entry():
    """A skipped node returns an execution_log entry with 'Skipped' message."""
    from bmad_orchestrator.graph import _make_skip_node
    skip = _make_skip_node("qa_automation")
    result = skip(make_state())
    assert len(result["execution_log"]) == 1
    entry = result["execution_log"][0]
    assert entry["node"] == "qa_automation"
    assert "Skipped" in entry["message"]


def test_make_initial_state_with_story_key(settings, monkeypatch, tmp_path):
    """--story-key pre-seeds current_story_id in the initial state."""
    from bmad_orchestrator.graph import make_initial_state
    monkeypatch.chdir(tmp_path)
    state = make_initial_state("growth", "Add SSO login", epic_key="PUG-437", story_key="PUG-438")
    assert state["current_story_id"] == "PUG-438"
    assert state["current_epic_id"] == "PUG-437"


def test_make_initial_state_without_story_key(settings, monkeypatch, tmp_path):
    """Without --story-key, current_story_id is None."""
    from bmad_orchestrator.graph import make_initial_state
    monkeypatch.chdir(tmp_path)
    state = make_initial_state("growth", "Add SSO login", epic_key="PUG-437")
    assert state["current_story_id"] is None


def test_make_initial_state_with_story_content(settings, monkeypatch, tmp_path):
    """story_content and acceptance_criteria are pre-loaded into state."""
    from bmad_orchestrator.graph import make_initial_state
    monkeypatch.chdir(tmp_path)
    state = make_initial_state(
        "growth", "Add SSO login",
        story_key="PUG-438",
        story_content="Implement SSO login flow",
        acceptance_criteria=["Login works", "Logout works"],
    )
    assert state["story_content"] == "Implement SSO login flow"
    assert state["acceptance_criteria"] == ["Login works", "Logout works"]


def test_make_initial_state_story_content_defaults_none(
    settings, monkeypatch, tmp_path,
):
    """Without story_content args, fields default to None."""
    from bmad_orchestrator.graph import make_initial_state
    monkeypatch.chdir(tmp_path)
    state = make_initial_state("growth", "Add SSO login")
    assert state["story_content"] is None
    assert state["acceptance_criteria"] is None


def test_make_initial_state_sets_notify_jira_story_key(settings, monkeypatch, tmp_path):
    """When story_key is passed, notify_jira_story_key is set for step notifications."""
    from bmad_orchestrator.graph import make_initial_state
    monkeypatch.chdir(tmp_path)
    state = make_initial_state("growth", "Add SSO", story_key="SAM1-51")
    assert state["notify_jira_story_key"] == "SAM1-51"
    assert state["step_notification_comment_id"] is None
    assert state["step_notification_comment_body"] is None


# ── Step notification wrapper (Jira comment per step) ─────────────────────────


def test_wrap_step_notifications_first_step_creates_comment_and_updates(settings):
    """First node: add_comment with 'Process started', then update_comment with Step completed."""
    from unittest.mock import MagicMock

    from datetime import UTC, datetime

    from bmad_orchestrator import graph
    from bmad_orchestrator.graph import _wrap_with_step_notifications

    class _FixedDatetime(datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 3, 10, 14, 32, tzinfo=UTC)

    jira = MagicMock()
    # Patch datetime used inside graph module so timestamps are deterministic.
    graph.datetime = _FixedDatetime  # type: ignore[assignment]
    jira.add_comment.return_value = "comment-123"

    def fake_node(state):
        return {"execution_log": []}

    wrapped = _wrap_with_step_notifications(
        jira, settings.model_copy(update={"dry_run": False}),
        "dev_story", fake_node,
    )
    state = make_state(notify_jira_story_key="SAM1-51")
    result = wrapped(state)

    assert "🚀 Process started" in result["step_notification_comment_body"]
    assert (
        "[10 Mar 2026 - 14:32] ✅ Step completed: Dev story"
        in result["step_notification_comment_body"]
    )
    jira.add_comment.assert_called_once_with("SAM1-51", "🚀 Process started")
    assert jira.update_comment.call_count == 1
    jira.update_comment.assert_called_with(
        "SAM1-51",
        "comment-123",
        "🚀 Process started\n\n[10 Mar 2026 - 14:32] ✅ Step completed: Dev story\n\n⏩ Process continuing...",
    )


def test_wrap_step_notifications_later_step_only_updates_comment(settings):
    """When comment_id is in state, wrapper calls update_comment once with Step completed."""
    from unittest.mock import MagicMock

    from datetime import UTC, datetime

    from bmad_orchestrator import graph
    from bmad_orchestrator.graph import _wrap_with_step_notifications

    class _FixedDatetime(datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 3, 10, 14, 32, tzinfo=UTC)

    jira = MagicMock()
    # Patch datetime used inside graph module so timestamps are deterministic.
    graph.datetime = _FixedDatetime  # type: ignore[assignment]
    jira.add_comment.return_value = "comment-456"

    def fake_node(state):
        return {"execution_log": []}

    wrapped = _wrap_with_step_notifications(
        jira, settings.model_copy(update={"dry_run": False}),
        "qa_automation", fake_node,
    )
    state = make_state(
        notify_jira_story_key="SAM1-51",
        step_notification_comment_id="comment-456",
        step_notification_comment_body=(
            "🚀 Process started\n\n✅ Step completed: Dev story\n\n⏩ Process continuing..."
        ),
    )
    result = wrapped(state)

    jira.add_comment.assert_not_called()
    assert jira.update_comment.call_count == 1
    body = jira.update_comment.call_args_list[0][0][2]
    assert "[10 Mar 2026 - 14:32] ✅ Step completed: QA automation" in body


def test_wrap_step_notifications_no_notify_key_skips_jira(settings):
    """Without notify_jira_story_key, wrapper does not call add_comment or update_comment."""
    from unittest.mock import MagicMock

    from bmad_orchestrator.graph import _wrap_with_step_notifications

    jira = MagicMock()
    run_settings = settings.model_copy(update={"dry_run": False})

    def fake_node(state):
        return {"execution_log": []}

    wrapped = _wrap_with_step_notifications(jira, run_settings, "dev_story", fake_node)
    state = make_state(notify_jira_story_key=None)
    wrapped(state)

    jira.add_comment.assert_not_called()
    jira.update_comment.assert_not_called()


def test_wrap_step_notifications_dry_run_skips_jira(settings):
    """When dry_run is True, wrapper does not call add_comment or update_comment."""
    from unittest.mock import MagicMock

    from bmad_orchestrator.graph import _wrap_with_step_notifications

    jira = MagicMock()
    dry_settings = settings.model_copy(update={"dry_run": True})

    def fake_node(state):
        return {"execution_log": []}

    wrapped = _wrap_with_step_notifications(jira, dry_settings, "dev_story", fake_node)
    state = make_state(notify_jira_story_key="SAM1-51")
    result = wrapped(state)

    jira.add_comment.assert_not_called()
    jira.update_comment.assert_not_called()
    assert "step_notification_comment_id" not in result
