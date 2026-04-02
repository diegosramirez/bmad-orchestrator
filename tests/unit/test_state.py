from __future__ import annotations

import operator
from typing import get_type_hints

from bmad_orchestrator.state import (
    CodeReviewIssue,
    ExecutionLogEntry,
    OrchestratorState,
    QAResult,
)


def test_orchestrator_state_has_expected_keys() -> None:
    hints = get_type_hints(OrchestratorState, include_extras=False)
    required_keys = {
        "team_id",
        "input_prompt",
        "current_epic_id",
        "current_story_id",
        "branch_name",
        "commit_sha",
        "pr_url",
        "review_loop_count",
        "code_review_issues",
        "qa_results",
        "execution_log",
        "failure_state",
    }
    assert required_keys.issubset(hints.keys())


def test_annotated_reducers_use_operator_add() -> None:

    hints = get_type_hints(OrchestratorState, include_extras=True)
    # qa_results and execution_log accumulate across nodes
    for field in ("qa_results", "execution_log"):
        ann = hints[field]
        metadata = getattr(ann, "__metadata__", ())
        assert operator.add in metadata, f"{field} should use operator.add reducer"

    # code_review_issues is a simple replace (not operator.add) so each
    # review pass starts with a clean slate.
    ann = hints["code_review_issues"]
    metadata = getattr(ann, "__metadata__", ())
    assert operator.add not in metadata, "code_review_issues should NOT use operator.add"


def test_code_review_issue_typeddict_fields() -> None:
    hints = get_type_hints(CodeReviewIssue, include_extras=False)
    assert "severity" in hints
    assert "file" in hints
    assert "description" in hints


def test_qa_result_typeddict_fields() -> None:
    hints = get_type_hints(QAResult, include_extras=False)
    assert "test_file" in hints
    assert "passed" in hints
    assert "output" in hints


def test_execution_log_entry_typeddict_fields() -> None:
    hints = get_type_hints(ExecutionLogEntry, include_extras=False)
    assert "timestamp" in hints
    assert "node" in hints
    assert "message" in hints
    assert "dry_run" in hints
