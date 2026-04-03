from __future__ import annotations

from bmad_orchestrator.services.claude_agent_service import AgentResult
from bmad_orchestrator.utils.cost_tracking import accumulate_cost


def test_accumulate_cost_below_budget(settings):
    """Cost below budget returns new total and no message."""
    result = AgentResult(total_cost_usd=1.50)
    new_total, msg = accumulate_cost(0.0, result, settings)
    assert new_total == 1.50
    assert msg is None


def test_accumulate_cost_exceeds_budget(settings):
    """Cost exceeding budget returns total and a budget message."""
    over_budget = settings.model_copy(update={"max_pipeline_cost_usd": 2.0})
    result = AgentResult(total_cost_usd=1.50)
    new_total, msg = accumulate_cost(1.0, result, over_budget)
    assert new_total == 2.50
    assert msg is not None
    assert "$2.50" in msg
    assert "$2.00" in msg


def test_accumulate_cost_none_treated_as_zero(settings):
    """AgentResult with None cost should be treated as $0."""
    result = AgentResult(total_cost_usd=None)
    new_total, msg = accumulate_cost(3.0, result, settings)
    assert new_total == 3.0
    assert msg is None


def test_accumulate_cost_exact_budget_no_exceed(settings):
    """Exactly at budget should not trigger the message (only > triggers)."""
    exact = settings.model_copy(update={"max_pipeline_cost_usd": 5.0})
    result = AgentResult(total_cost_usd=2.0)
    new_total, msg = accumulate_cost(3.0, result, exact)
    assert new_total == 5.0
    assert msg is None
