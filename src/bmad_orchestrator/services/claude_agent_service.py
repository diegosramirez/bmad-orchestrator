from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    UserMessage,
    query,
)
from claude_agent_sdk.types import TextBlock, ToolResultBlock, ToolUseBlock
from pydantic import BaseModel

from bmad_orchestrator.config import Settings
from bmad_orchestrator.personas.loader import AGENT_DISPLAY_NAMES
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_MAX_TURNS = 30
_DEFAULT_EFFORT = "low"
_DEFAULT_MAX_BUDGET_USD = 2.0
_DEFAULT_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
_DEFAULT_DISALLOWED_TOOLS = [
    "Task", "Agent", "TodoWrite", "WebSearch", "WebFetch",
]


@dataclass
class AgentResult:
    """Result of a Claude Agent SDK session."""

    touched_files: list[str] = field(default_factory=list)
    structured_output: Any | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    total_cost_usd: float | None = None
    result_text: str | None = None
    is_error: bool = False


class ClaudeAgentService:
    """Wrapper around the Claude Agent SDK for agentic code generation.

    Gives Claude direct file system access (Read/Write/Edit) and Bash execution,
    eliminating the need for manual file I/O and two-phase generation patterns.
    """

    def __init__(
        self,
        settings: Settings,
        usage_tracker: list[dict[str, Any]] | None = None,
    ) -> None:
        self.settings = settings
        self._usage = usage_tracker if usage_tracker is not None else []
        self._loop = asyncio.new_event_loop()

    def _model_for(self, agent_id: str) -> str | None:
        """Resolve the model name for a given agent, with fallback to default."""
        model = self.settings.agent_models.get(agent_id, self.settings.model_name)
        return model if model else None

    def run_agent(
        self,
        prompt: str,
        *,
        system_prompt: str,
        agent_id: str = "unknown",
        cwd: str | Path | None = None,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        output_format_schema: type[BaseModel] | None = None,
        max_turns: int = _DEFAULT_MAX_TURNS,
        effort: str = _DEFAULT_EFFORT,
        max_budget_usd: float = _DEFAULT_MAX_BUDGET_USD,
    ) -> AgentResult:
        """Run a Claude Agent SDK session synchronously.

        Bridges async SDK → sync via asyncio.run().
        Returns an AgentResult with touched files, structured output, and usage.
        """
        if self.settings.dry_run:
            return self._dry_run_result(output_format_schema, agent_id)

        return self._loop.run_until_complete(
            self._run_async(
                prompt=prompt,
                system_prompt=system_prompt,
                agent_id=agent_id,
                cwd=cwd,
                allowed_tools=allowed_tools,
                disallowed_tools=disallowed_tools,
                output_format_schema=output_format_schema,
                max_turns=max_turns,
                effort=effort,
                max_budget_usd=max_budget_usd,
            )
        )

    async def _run_async(
        self,
        *,
        prompt: str,
        system_prompt: str,
        agent_id: str,
        cwd: str | Path | None,
        allowed_tools: list[str] | None,
        disallowed_tools: list[str] | None,
        output_format_schema: type[BaseModel] | None,
        max_turns: int,
        effort: str = _DEFAULT_EFFORT,
        max_budget_usd: float = _DEFAULT_MAX_BUDGET_USD,
    ) -> AgentResult:
        agent_name = AGENT_DISPLAY_NAMES.get(agent_id, agent_id)
        touched: list[str] = []

        output_format = None
        if output_format_schema is not None:
            output_format = {
                "type": "json_schema",
                "schema": output_format_schema.model_json_schema(),
            }

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=self._model_for(agent_id),
            permission_mode="bypassPermissions",
            allowed_tools=allowed_tools or _DEFAULT_TOOLS,
            disallowed_tools=(
                disallowed_tools if disallowed_tools is not None
                else _DEFAULT_DISALLOWED_TOOLS
            ),
            cwd=str(cwd) if cwd else None,
            max_turns=max_turns,
            output_format=output_format,
            effort=effort,
            max_budget_usd=max_budget_usd,
            env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "128000"},
        )

        logger.info(
            "agent_session_start",
            agent=agent_name,
            model=self._model_for(agent_id),
            max_turns=max_turns,
            tools=allowed_tools or _DEFAULT_TOOLS,
        )

        result_msg: ResultMessage | None = None
        turn = 0
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                turn += 1
                # Log API errors on the assistant message
                if message.error:
                    logger.error(
                        "agent_api_error",
                        agent=agent_name,
                        turn=turn,
                        error=message.error,
                    )
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        # Track files written/edited from stream
                        if block.name in ("Write", "Edit"):
                            fp = block.input.get("file_path", "")
                            if fp and fp not in touched:
                                touched.append(fp)

                        detail = ""
                        if block.name in (
                            "Read", "Write", "Edit", "Glob",
                        ):
                            detail = block.input.get(
                                "file_path",
                                block.input.get("pattern", ""),
                            )
                        elif block.name == "Bash":
                            cmd = block.input.get("command", "")
                            detail = (
                                cmd[:120]
                                + ("…" if len(cmd) > 120 else "")
                            )
                        elif block.name == "Grep":
                            detail = block.input.get("pattern", "")
                        logger.info(
                            "agent_tool_use",
                            agent=agent_name,
                            turn=turn,
                            tool=block.name,
                            detail=detail or None,
                        )
                    elif isinstance(block, ToolResultBlock):
                        lvl = "error" if block.is_error else "info"
                        content = (
                            block.content
                            if isinstance(block.content, str)
                            else str(block.content)
                        )
                        snippet = content[:300] if content else ""
                        getattr(logger, lvl)(
                            "agent_tool_result",
                            agent=agent_name,
                            turn=turn,
                            tool_use_id=block.tool_use_id,
                            is_error=block.is_error or False,
                            output=snippet,
                        )
                    elif isinstance(block, TextBlock):
                        text = block.text.strip()
                        if text:
                            logger.info(
                                "agent_text",
                                agent=agent_name,
                                turn=turn,
                                text=text[:300],
                            )
                    else:
                        # ThinkingBlock or unknown — log type
                        logger.debug(
                            "agent_block",
                            agent=agent_name,
                            turn=turn,
                            block_type=type(block).__name__,
                        )
            elif isinstance(message, ResultMessage):
                result_msg = message
                logger.info(
                    "agent_result_message",
                    agent=agent_name,
                    subtype=message.subtype,
                    is_error=message.is_error,
                    stop_reason=message.stop_reason,
                    result=message.result[:500] if message.result else None,
                )
            elif isinstance(message, UserMessage):
                # Tool results returned to Claude
                content = message.content
                if isinstance(content, str):
                    snippet = content[:300]
                else:
                    snippet = str(content)[:300]
                logger.info(
                    "agent_user_message",
                    agent=agent_name,
                    turn=turn,
                    content=snippet,
                )
            elif isinstance(message, SystemMessage):
                logger.info(
                    "agent_system_message",
                    agent=agent_name,
                    subtype=message.subtype,
                    data=str(message.data)[:300],
                )

        if result_msg is None:
            logger.error("agent_session_no_result", agent=agent_name)
            return AgentResult(
                touched_files=touched,
                is_error=True,
                result_text="Agent session ended without a result message",
            )

        # Track usage for the token report
        usage = result_msg.usage or {}
        self._usage.append({
            "agent_id": agent_id,
            "agent_name": agent_name,
            "model": self._model_for(agent_id) or self.settings.model_name,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "duration_s": round(result_msg.duration_ms / 1000, 2),
        })

        logger.info(
            "agent_session_complete",
            agent=agent_name,
            turns=result_msg.num_turns,
            touched_files=len(touched),
            is_error=result_msg.is_error,
            duration_ms=result_msg.duration_ms,
            tokens_in=usage.get("input_tokens", 0),
            tokens_out=usage.get("output_tokens", 0),
            cost_usd=result_msg.total_cost_usd,
        )

        return AgentResult(
            touched_files=touched,
            structured_output=result_msg.structured_output,
            usage=usage,
            duration_ms=result_msg.duration_ms,
            total_cost_usd=result_msg.total_cost_usd,
            result_text=result_msg.result,
            is_error=result_msg.is_error,
        )

    def _dry_run_result(
        self,
        output_format_schema: type[BaseModel] | None,
        agent_id: str,
    ) -> AgentResult:
        agent_name = AGENT_DISPLAY_NAMES.get(agent_id, agent_id)
        logger.info("dry_run_skip", agent=agent_name, method="run_agent")

        structured = None
        if output_format_schema is not None:
            defaults: dict[str, Any] = {}
            for name, field_info in output_format_schema.model_fields.items():
                if not field_info.is_required():
                    continue
                ann = field_info.annotation
                if ann is str:
                    defaults[name] = "[DRY RUN]"
                elif ann is bool:
                    defaults[name] = False
                elif ann is int:
                    defaults[name] = 0
                else:
                    defaults[name] = []
            structured = output_format_schema.model_construct(**defaults)

        return AgentResult(
            touched_files=[],
            structured_output=structured,
            result_text="[DRY RUN — no agent session]",
        )
