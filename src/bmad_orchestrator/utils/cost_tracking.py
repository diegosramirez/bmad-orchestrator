from __future__ import annotations

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.claude_agent_service import AgentResult
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)


def accumulate_cost(
    current_total: float,
    result: AgentResult,
    settings: Settings,
) -> tuple[float, str | None]:
    """Add agent session cost to running total.

    Returns (new_total, budget_exceeded_message_or_none).
    """
    cost = result.total_cost_usd or 0.0
    new_total = current_total + cost
    logger.info(
        "cost_accumulated",
        session_cost=cost,
        total_cost=new_total,
        budget=settings.max_pipeline_cost_usd,
    )
    if new_total > settings.max_pipeline_cost_usd:
        msg = (
            f"Pipeline budget exceeded: ${new_total:.2f} > "
            f"${settings.max_pipeline_cost_usd:.2f} limit"
        )
        logger.warning(
            "budget_exceeded",
            total=new_total,
            limit=settings.max_pipeline_cost_usd,
        )
        return new_total, msg
    return new_total, None
