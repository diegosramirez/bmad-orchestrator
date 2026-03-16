from __future__ import annotations

import json
import time
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel
from rich.console import Console
from rich.live import Live
from rich.text import Text

from bmad_orchestrator.config import Settings
from bmad_orchestrator.personas.loader import AGENT_DISPLAY_NAMES
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if over max_len."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _summarize_model(result: BaseModel) -> str:
    """Produce a compact one-line summary of a Pydantic model."""
    fields: dict[str, object] = {}
    for name, value in result:
        if isinstance(value, str):
            fields[name] = _truncate(value, 40)
        elif isinstance(value, list):
            fields[name] = f"[{len(value)} items]"
        else:
            fields[name] = value
    parts = ", ".join(f"{k}={v!r}" for k, v in list(fields.items())[:4])
    return f"{type(result).__name__}({parts})"


class _StreamingSpinner:
    """Dynamic renderable whose elapsed time updates on every Live refresh."""

    def __init__(self, agent_name: str, method: str, t0: float) -> None:
        self.agent_name = agent_name
        self.method = method
        self.t0 = t0
        self.approx_tokens = 0

    def __rich__(self) -> Text:
        elapsed = time.perf_counter() - self.t0
        return Text.from_markup(
            f"  [bold cyan]\u23f3 {self.agent_name}[/bold cyan] | {self.method} | "
            f"{elapsed:.1f}s | ~{self.approx_tokens:,} tokens out"
        )


class ClaudeService:
    def __init__(self, settings: Settings, *, console: Console | None = None) -> None:
        self.settings = settings
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )
        self._console = console
        # Separate ephemeral console for the streaming spinner so transient
        # Live output is never captured by the main console's record buffer.
        self._spinner_console = Console(stderr=True) if console else None
        # Accumulated token usage records (one per real API call).
        self._usage: list[dict[str, Any]] = []

    def _model_for(self, agent_id: str) -> str:
        """Resolve the model name for a given agent, with fallback to default."""
        return self.settings.agent_models.get(
            agent_id, self.settings.model_name,
        )

    def _call_api(
        self,
        agent_name: str,
        method: str,
        t0: float,
        **kwargs: Any,
    ) -> Any:
        """Call the Anthropic API, with streaming spinner when console is available."""
        if self._spinner_console:
            spinner = _StreamingSpinner(agent_name, method, t0)
            with Live(
                spinner,
                console=self._spinner_console,
                transient=True,
                refresh_per_second=4,
            ):
                with self._client.messages.stream(**kwargs) as stream:
                    for event in stream:
                        if (
                            hasattr(event, "type")
                            and event.type == "content_block_delta"
                        ):
                            delta = event.delta
                            chunk_len = 0
                            if hasattr(delta, "text") and delta.text:
                                chunk_len = len(delta.text)
                            elif (
                                hasattr(delta, "partial_json")
                                and delta.partial_json
                            ):
                                chunk_len = len(delta.partial_json)
                            if chunk_len:
                                spinner.approx_tokens += max(
                                    1, chunk_len // 4
                                )
                    return stream.get_final_message()
        return self._client.messages.create(**kwargs)

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        agent_id: str = "unknown",
    ) -> str:
        """Call Claude and return the raw text response."""
        agent_name = AGENT_DISPLAY_NAMES.get(agent_id, agent_id)

        if self.settings.dry_run:
            logger.info("dry_run_skip", agent=agent_name, method="complete",
                        prompt=_truncate(user_message, 120))
            return "[DRY RUN \u2014 no Claude call made]"

        logger.info("claude_request", agent=agent_name, method="complete",
                    prompt=_truncate(user_message, 120))
        logger.debug("claude_request_full", agent=agent_name, method="complete",
                     user_message=user_message)

        model = self._model_for(agent_id)
        t0 = time.perf_counter()
        response = self._call_api(
            agent_name, "complete", t0,
            model=model,
            max_tokens=max_tokens,
            temperature=self.settings.temperature,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_message}],
        )
        elapsed = time.perf_counter() - t0

        content = response.content[0]
        if content.type != "text":
            raise ValueError(f"Unexpected response type: {content.type}")

        logger.info("claude_response", agent=agent_name, method="complete",
                    response=_truncate(content.text, 200),
                    tokens_in=response.usage.input_tokens,
                    tokens_out=response.usage.output_tokens,
                    duration_s=round(elapsed, 2))
        logger.debug("claude_response_full", agent=agent_name, method="complete",
                     full_response=content.text)

        self._usage.append({
            "agent_id": agent_id,
            "agent_name": agent_name,
            "model": model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "duration_s": round(elapsed, 2),
        })

        return content.text

    def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        schema: type[T],
        max_tokens: int = 4096,
        agent_id: str = "unknown",
    ) -> T:
        """
        Call Claude with forced structured JSON output via tool_use.

        The response is validated against `schema` (a Pydantic BaseModel subclass)
        and returned as an instance of that model.
        """
        agent_name = AGENT_DISPLAY_NAMES.get(agent_id, agent_id)

        if self.settings.dry_run:
            logger.info(
                "dry_run_skip",
                agent=agent_name,
                method="complete_structured",
                schema=schema.__name__,
                prompt=_truncate(user_message, 120),
            )
            # Build a dummy instance with placeholder values for required
            # fields.  model_construct() skips validation so min_length
            # constraints (e.g. StoryDraft) don't block the dry run.
            defaults: dict[str, Any] = {}
            for name, field_info in schema.model_fields.items():
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
            return schema.model_construct(**defaults)

        tool_name = schema.__name__
        tool_schema = schema.model_json_schema()

        logger.info("claude_request", agent=agent_name, method="complete_structured",
                    schema=schema.__name__, prompt=_truncate(user_message, 120))
        logger.debug("claude_request_full", agent=agent_name, method="complete_structured",
                     user_message=user_message)

        model = self._model_for(agent_id)
        t0 = time.perf_counter()
        response = self._call_api(
            agent_name, "complete_structured", t0,
            model=model,
            max_tokens=max_tokens,
            temperature=self.settings.temperature,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=[
                {
                    "name": tool_name,
                    "description": f"Return structured {tool_name} data",
                    "input_schema": tool_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user_message}],
        )
        elapsed = time.perf_counter() - t0

        # Detect truncation: if stop_reason is max_tokens, the JSON is incomplete
        if response.stop_reason == "max_tokens":
            logger.error(
                "claude_response_truncated",
                agent=agent_name,
                method="complete_structured",
                schema=schema.__name__,
                max_tokens=max_tokens,
                tokens_out=response.usage.output_tokens,
            )
            raise ValueError(
                f"Claude response was truncated "
                f"(used {response.usage.output_tokens}/{max_tokens} tokens). "
                f"The {schema.__name__} output is too large for the "
                f"current max_tokens limit. Increase max_tokens."
            )

        tool_use_block = next(
            (b for b in response.content if b.type == "tool_use"),
            None,
        )
        if tool_use_block is None:
            raise ValueError("Claude did not return a tool_use block")

        raw: dict[str, Any] = (
            tool_use_block.input
            if isinstance(tool_use_block.input, dict)
            else json.loads(tool_use_block.input)
        )
        result = schema.model_validate(raw)

        logger.info("claude_response", agent=agent_name, method="complete_structured",
                    response=_summarize_model(result),
                    tokens_in=response.usage.input_tokens,
                    tokens_out=response.usage.output_tokens,
                    duration_s=round(elapsed, 2))

        self._usage.append({
            "agent_id": agent_id,
            "agent_name": agent_name,
            "model": model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "duration_s": round(elapsed, 2),
        })

        return result

    def classify(
        self,
        system_prompt: str,
        user_message: str,
        options: list[str],
        agent_id: str = "unknown",
    ) -> str:
        """
        Ask Claude to pick one option from a fixed list.
        Returns the chosen option string (lowercased, stripped).
        """
        opts_str = " | ".join(options)
        full_prompt = (
            f"{user_message}\n\n"
            f"Respond with EXACTLY one of: {opts_str}\n"
            f"No explanation, just the option."
        )
        result = self.complete(system_prompt, full_prompt, max_tokens=64,
                               agent_id=agent_id)
        result = result.strip().lower()
        for opt in options:
            if opt.lower() in result:
                return opt
        return options[0]

    def get_usage_report(self) -> dict[str, Any]:
        """Return token usage grouped by agent, plus totals and model."""
        from collections import defaultdict

        buckets: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "duration_s": 0.0,
                "models": set(),
            }
        )
        for rec in self._usage:
            b = buckets[rec["agent_name"]]
            b["calls"] += 1
            b["input_tokens"] += rec["input_tokens"]
            b["output_tokens"] += rec["output_tokens"]
            b["duration_s"] += rec["duration_s"]
            b["models"].add(rec.get("model", self.settings.model_name))

        rows = [
            {
                "agent": name,
                "calls": data["calls"],
                "input_tokens": data["input_tokens"],
                "output_tokens": data["output_tokens"],
                "total_tokens": (
                    data["input_tokens"] + data["output_tokens"]
                ),
                "duration_s": data["duration_s"],
                "model": ", ".join(sorted(data["models"])),
            }
            for name, data in buckets.items()
        ]
        all_models = {m for r in rows for m in r["model"].split(", ")}
        total_in = sum(r["input_tokens"] for r in rows)
        total_out = sum(r["output_tokens"] for r in rows)
        return {
            "model": self.settings.model_name,
            "models_mixed": len(all_models) > 1,
            "rows": rows,
            "total_input": total_in,
            "total_output": total_out,
            "total": total_in + total_out,
            "total_calls": sum(r["calls"] for r in rows),
            "total_duration_s": round(
                sum(r["duration_s"] for r in rows), 2
            ),
        }
