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
    assert router(state) == "e2e_automation"


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
    assert router(state) == "e2e_automation"


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
    assert router(state) == "e2e_automation"


def test_router_commit_when_no_issues(settings):
    router = make_review_router(settings)
    assert router(make_state()) == "e2e_automation"


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


def test_build_graph_discovery_execution_mode(settings, tmp_path):
    """Smoke test: discovery execution mode compiles (Forge /bmad/discovery-run)."""
    from bmad_orchestrator.graph import build_graph

    disc = settings.model_copy(
        update={
            "execution_mode": "discovery",
            "checkpoint_db_path": str(tmp_path / "discovery_cp.db"),
        },
    )
    graph, _, _ = build_graph(disc)
    assert graph is not None


def test_step_status_suffix_discovery_create_epic_completed(settings):
    """Forge Discovery: last real node shows process completed (Jira step comment)."""
    from bmad_orchestrator.graph import _step_status_suffix

    disc = settings.model_copy(update={"execution_mode": "discovery"})
    assert "completed successfully" in _step_status_suffix("create_or_correct_epic", disc)
    assert _step_status_suffix("create_or_correct_epic", settings) == "⏩ Process continuing..."


def test_step_status_suffix_terminal_and_continuing():
    """PR / epic_architect / fail_with_state / default dev node suffixes."""
    from bmad_orchestrator.graph import _step_status_suffix

    assert "completed successfully" in _step_status_suffix("create_pull_request")
    assert "completed successfully" in _step_status_suffix("epic_architect")
    assert _step_status_suffix("fail_with_state") == "Process finished."
    assert _step_status_suffix("dev_story") == "⏩ Process continuing..."


def test_step_status_suffix_create_pull_request_merged_success_with_branch_and_pr(settings):
    """Merged state adds GitHub tree URL and PR link after success headline."""
    from bmad_orchestrator.graph import _github_branch_tree_url, _step_status_suffix

    merged = {
        "branch_name": "feat/foo-bar",
        "pr_url": "https://github.com/org/repo/pull/99",
        "failure_state": None,
    }
    text = _step_status_suffix("create_pull_request", settings, merged)
    assert "completed successfully" in text
    assert "**Branch:**" in text
    assert "https://github.com/org/repo/tree/feat/foo-bar" in text
    assert "[feat/foo-bar](https://github.com/org/repo/tree/feat/foo-bar)" in text
    assert "**PR:** [PR #99](https://github.com/org/repo/pull/99)" in text
    assert _github_branch_tree_url(settings, None) is None


def test_step_status_suffix_create_pull_request_merged_failure_headline(settings):
    """When failure_state is set, headline explains draft PR; still list branch + PR."""
    from bmad_orchestrator.graph import _step_status_suffix

    merged = {
        "branch_name": "bmad/x",
        "pr_url": "https://github.com/org/repo/pull/1",
        "failure_state": "Pipeline failed after 2 loop(s).",
    }
    text = _step_status_suffix("create_pull_request", settings, merged)
    assert "draft PR includes unresolved pipeline issues" in text
    assert "completed successfully" not in text
    assert "**Branch:**" in text and "**PR:**" in text


def test_github_branch_tree_url_malformed_repo(settings):
    from bmad_orchestrator.graph import _github_branch_tree_url

    bad = settings.model_copy(update={"github_repo": "not-a-slash"})
    assert _github_branch_tree_url(bad, "main") is None


def test_execution_log_indicates_skip_and_strip_trailing_status():
    from bmad_orchestrator.graph import _execution_log_indicates_skip, _strip_trailing_status

    assert _execution_log_indicates_skip(
        {"execution_log": [{"message": "Skipped (--skip-nodes)"}]},
    )
    assert not _execution_log_indicates_skip({"execution_log": [{"message": "done"}]})
    base = (
        "🚀 Process started\n\n[10 Mar 2026 - 14:32] ✅ Step completed: X\n\n"
        "⏩ Process continuing..."
    )
    assert _strip_trailing_status(base).endswith("Step completed: X")
    assert _strip_trailing_status("x\n⏩ Process continuing...") == "x"
    assert _strip_trailing_status("no status suffix") == "no status suffix"
    assert _strip_trailing_status("z\n\nProcess finished.") == "z"
    assert _strip_trailing_status("w\n\n⏭️ Process continuing...") == "w"

    multiline = (
        "🚀 Process started\n\n[10 Mar 2026 - 14:32] ✅ Step completed: X\n\n"
        "🎉 Process completed successfully\n"
        "**Branch:** [main](https://github.com/org/repo/tree/main)\n"
        "**PR:** [PR #1](https://github.com/org/repo/pull/1)"
    )
    stripped = _strip_trailing_status(multiline)
    assert "Step completed: X" in stripped
    assert "completed successfully" not in stripped
    assert "**Branch:**" not in stripped


def test_route_after_create_or_correct_epic(settings):
    """After create_or_correct_epic: architect, discovery→END, or default story tasks."""
    from bmad_orchestrator.graph import _route_after_create_or_correct_epic

    assert (
        _route_after_create_or_correct_epic(
            settings.model_copy(update={"execution_mode": "discovery"}),
        )
        == "discovery_epic_end"
    )
    assert (
        _route_after_create_or_correct_epic(
            settings.model_copy(update={"execution_mode": "epic_architect"}),
        )
        == "epic_architect"
    )
    assert _route_after_create_or_correct_epic(settings) == "create_story_tasks"


def test_build_graph_epic_architect_execution_mode(settings, tmp_path):
    """Smoke test: epic_architect execution mode compiles (Forge /bmad/architect-run)."""
    from bmad_orchestrator.graph import build_graph

    arch = settings.model_copy(
        update={
            "execution_mode": "epic_architect",
            "checkpoint_db_path": str(tmp_path / "architect_cp.db"),
        },
    )
    graph, _, _ = build_graph(arch)
    assert graph is not None


def test_build_graph_stories_breakdown_execution_mode(settings, tmp_path):
    """Smoke test: stories_breakdown mode compiles (Forge /bmad/stories-run)."""
    from bmad_orchestrator.graph import build_graph

    sb = settings.model_copy(
        update={
            "execution_mode": "stories_breakdown",
            "checkpoint_db_path": str(tmp_path / "stories_cp.db"),
        },
    )
    graph, _, _ = build_graph(sb)
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


def test_wrap_step_notifications_add_comment_raises_skips_jira_updates(settings):
    """If add_comment fails, run the node but omit step-notification state updates."""
    from unittest.mock import MagicMock

    from bmad_orchestrator.graph import _wrap_with_step_notifications

    jira = MagicMock()
    jira.add_comment.side_effect = RuntimeError("jira unavailable")

    def fake_node(state):
        return {"execution_log": [], "ok": True}

    wrapped = _wrap_with_step_notifications(
        jira, settings.model_copy(update={"dry_run": False}),
        "dev_story", fake_node,
    )
    state = make_state(notify_jira_story_key="SAM1-51")
    result = wrapped(state)
    assert result.get("ok") is True
    assert "step_notification_comment_id" not in result
    jira.update_comment.assert_not_called()


def test_wrap_step_notifications_update_comment_raises_still_returns_state(settings):
    """If update_comment fails after add_comment, state still includes comment id and body."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    from bmad_orchestrator import graph
    from bmad_orchestrator.graph import _wrap_with_step_notifications

    class _FixedDatetime(datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 3, 10, 14, 32, tzinfo=UTC)

    jira = MagicMock()
    graph.datetime = _FixedDatetime  # type: ignore[assignment]
    jira.add_comment.return_value = "comment-99"
    jira.update_comment.side_effect = RuntimeError("update failed")

    def fake_node(state):
        return {"execution_log": []}

    wrapped = _wrap_with_step_notifications(
        jira, settings.model_copy(update={"dry_run": False}),
        "dev_story", fake_node,
    )
    state = make_state(notify_jira_story_key="SAM1-51")
    result = wrapped(state)
    assert result["step_notification_comment_id"] == "comment-99"
    assert "Step completed: Dev story" in (result.get("step_notification_comment_body") or "")


def test_wrap_step_notifications_first_step_creates_comment_and_updates(settings):
    """First node: add_comment with 'Process started', then update_comment with Step completed."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

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
    expected_body = (
        "🚀 Process started\n\n"
        "[10 Mar 2026 - 14:32] ✅ Step completed: Dev story\n\n"
        "⏩ Process continuing..."
    )
    jira.update_comment.assert_called_with("SAM1-51", "comment-123", expected_body)


def test_wrap_step_notifications_create_pull_request_includes_branch_and_pr_links(settings):
    """Terminal create_pull_request step shows branch tree URL, PR URL, and correct headline."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    from bmad_orchestrator import graph
    from bmad_orchestrator.graph import _wrap_with_step_notifications

    class _FixedDatetime(datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 4, 13, 12, 0, tzinfo=UTC)

    jira = MagicMock()
    graph.datetime = _FixedDatetime  # type: ignore[assignment]

    def fake_create_pr(state):
        return {
            "execution_log": [],
            "pr_url": "https://github.com/org/repo/pull/42",
        }

    wrapped = _wrap_with_step_notifications(
        jira,
        settings.model_copy(update={"dry_run": False}),
        "create_pull_request",
        fake_create_pr,
    )
    state = make_state(
        notify_jira_story_key="SAM1-51",
        step_notification_comment_id="comment-456",
        step_notification_comment_body=(
            "🚀 Process started\n\n"
            "[13 Apr 2026 - 11:00] ✅ Step completed: Commit and push\n\n"
            "⏩ Process continuing..."
        ),
        branch_name="bmad/growth-123-feature",
        failure_state="Pipeline failed after 2 loop(s). Tests are FAILING.",
    )
    wrapped(state)
    body = jira.update_comment.call_args_list[0][0][2]
    assert "draft PR includes unresolved pipeline issues" in body
    assert "https://github.com/org/repo/tree/bmad/growth-123-feature" in body
    assert (
        "**Branch:** [bmad/growth-123-feature]"
        "(https://github.com/org/repo/tree/bmad/growth-123-feature)"
    ) in body
    assert "**PR:** [PR #42](https://github.com/org/repo/pull/42)" in body


def test_wrap_step_notifications_later_step_only_updates_comment(settings):
    """When comment_id is in state, wrapper calls update_comment once with Step completed."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

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
    wrapped(state)

    jira.add_comment.assert_not_called()
    assert jira.update_comment.call_count == 1
    body = jira.update_comment.call_args_list[0][0][2]
    assert "[10 Mar 2026 - 14:32] ✅ Step completed: QA automation" in body


def test_wrap_step_notifications_first_step_skipped_omits_step_completed(settings):
    """Skip nodes append ⏭️ Step skipped (not ✅ Step completed) plus status."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    from bmad_orchestrator import graph
    from bmad_orchestrator.graph import _wrap_with_step_notifications

    class _FixedDatetime(datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 3, 10, 14, 32, tzinfo=UTC)

    jira = MagicMock()
    graph.datetime = _FixedDatetime  # type: ignore[assignment]
    jira.add_comment.return_value = "comment-skip"

    def fake_skip_node(state):
        return {
            "execution_log": [{
                "timestamp": "2026-03-10T14:32:00+00:00",
                "node": "create_story_tasks",
                "message": "Skipped (--skip-nodes)",
                "dry_run": False,
            }],
        }

    wrapped = _wrap_with_step_notifications(
        jira, settings.model_copy(update={"dry_run": False}),
        "create_story_tasks", fake_skip_node,
    )
    state = make_state(notify_jira_story_key="SAM1-51")
    result = wrapped(state)

    body = result["step_notification_comment_body"]
    assert "🚀 Process started" in body
    assert "Step completed" not in body
    assert "⏭️ Step skipped: Create story tasks" in body
    assert "⏩ Process continuing..." in body
    jira.update_comment.assert_called_with(
        "SAM1-51",
        "comment-skip",
        "🚀 Process started\n\n"
        "[10 Mar 2026 - 14:32] ⏭️ Step skipped: Create story tasks\n\n"
        "⏩ Process continuing...",
    )


def test_wrap_step_notifications_later_step_skipped_omits_step_completed(settings):
    """Later skip nodes append ⏭️ Step skipped (not a new ✅ Step completed line)."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    from bmad_orchestrator import graph
    from bmad_orchestrator.graph import _wrap_with_step_notifications

    class _FixedDatetime(datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 3, 10, 14, 33, tzinfo=UTC)

    jira = MagicMock()
    graph.datetime = _FixedDatetime  # type: ignore[assignment]

    def fake_skip_node(state):
        return {
            "execution_log": [{
                "timestamp": "2026-03-10T14:33:00+00:00",
                "node": "party_mode_refinement",
                "message": "Skipped (--skip-nodes)",
                "dry_run": False,
            }],
        }

    wrapped = _wrap_with_step_notifications(
        jira, settings.model_copy(update={"dry_run": False}),
        "party_mode_refinement", fake_skip_node,
    )
    state = make_state(
        notify_jira_story_key="SAM1-51",
        step_notification_comment_id="comment-456",
        step_notification_comment_body=(
            "🚀 Process started\n\n[10 Mar 2026 - 14:32] ✅ Step completed: Check epic state\n\n"
            "⏩ Process continuing..."
        ),
    )
    result = wrapped(state)

    body = result["step_notification_comment_body"]
    assert "Step completed: Check epic state" in body
    assert "Step completed: Party mode refinement" not in body
    assert "⏭️ Step skipped: Party mode refinement" in body
    assert body.endswith("⏩ Process continuing...")
    jira.update_comment.assert_called_once()


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


def test_wrap_step_notifications_survives_jira_add_comment_exception(settings):
    """If add_comment raises, node still executes without crashing."""
    from unittest.mock import MagicMock

    from bmad_orchestrator.graph import _wrap_with_step_notifications

    jira = MagicMock()
    jira.add_comment.side_effect = RuntimeError("Jira API down")
    run_settings = settings.model_copy(update={"dry_run": False})

    def fake_node(state):
        return {"execution_log": [], "touched_files": ["a.py"]}

    wrapped = _wrap_with_step_notifications(
        jira, run_settings, "dev_story", fake_node,
    )
    state = make_state(notify_jira_story_key="SAM1-51")
    result = wrapped(state)

    # Node still executed despite Jira failure
    assert result["touched_files"] == ["a.py"]


def test_wrap_step_notifications_survives_jira_update_exception(settings):
    """If update_comment raises, node result is still returned."""
    from unittest.mock import MagicMock

    from bmad_orchestrator.graph import _wrap_with_step_notifications

    jira = MagicMock()
    jira.update_comment.side_effect = RuntimeError("Jira API down")
    run_settings = settings.model_copy(update={"dry_run": False})

    def fake_node(state):
        return {"execution_log": []}

    wrapped = _wrap_with_step_notifications(
        jira, run_settings, "qa_automation", fake_node,
    )
    state = make_state(
        notify_jira_story_key="SAM1-51",
        step_notification_comment_id="comment-456",
        step_notification_comment_body="🚀 Process started",
    )
    # Should not raise
    result = wrapped(state)
    assert "step_notification_comment_body" in result
