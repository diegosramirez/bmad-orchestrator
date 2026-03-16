from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from bmad_orchestrator.utils.logger import configure_logging, get_log_contents

app = typer.Typer(
    name="bmad-orchestrator",
    help="BMAD Autonomous Engineering Orchestrator — automates the full BMAD workflow.",
    add_completion=False,
)

console = Console(record=True)

_BMAD_HOME = Path.home() / ".bmad"
_LOGS_DIR = _BMAD_HOME / "logs"
_LAST_RUN_FILE = _BMAD_HOME / ".last_run"


_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}:\d{2})\.\d+Z)"
    r" \[(\w+)\s*\] "
    r"(\S+)"
    r"\s*(.*)?$"
)

# Key-value patterns in structlog trailing text: key='value' or key=value
_KV_RE = re.compile(r"(\w+)=(?:'([^']*(?:''[^']*)*)'|\"([^\"]*)\"|(\S+))")

# Events that produce excessively long values — show only select keys
_SUMMARY_EVENTS: dict[str, set[str]] = {
    "claude_request": {"agent", "method", "schema"},
    "claude_request_full": set(),  # skip entirely
    "claude_response": {"agent", "duration_s", "tokens_in", "tokens_out", "method"},
    "agent_system_message": {"agent", "subtype"},
    "agent_user_message": {"agent", "turn"},
    "agent_block": {"agent", "block_type", "turn"},
}


def _parse_kv(text: str) -> dict[str, str]:
    """Extract key=value pairs from a structlog trailing string."""
    result: dict[str, str] = {}
    for m in _KV_RE.finditer(text):
        key = m.group(1)
        val = m.group(2) if m.group(2) is not None else (m.group(3) if m.group(3) is not None else m.group(4))
        result[key] = val
    return result


def _relative_time(t: str, start: str) -> str:
    """Compute +M:SS offset between two HH:MM:SS strings."""
    def _secs(hms: str) -> int:
        h, m, s = hms.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    diff = _secs(t) - _secs(start)
    if diff < 0:
        diff = 0
    minutes, secs = divmod(diff, 60)
    return f"+{minutes}:{secs:02d}"


def _format_details(event: str, kv: dict[str, str]) -> str:
    """Format the details column for a timeline row."""
    allowed = _SUMMARY_EVENTS.get(event)
    if allowed is not None:
        if not allowed:
            return ""  # skip this event entirely
        parts = []
        for k in ("method", "schema", "duration_s", "tokens_in", "tokens_out",
                   "subtype", "block_type", "turn"):
            if k in allowed and k in kv:
                val = kv[k]
                if k == "duration_s":
                    parts.append(f"duration={val}s")
                elif k == "tokens_in" and "tokens_out" in kv:
                    parts.append(f"tokens={val}→{kv['tokens_out']}")
                elif k == "tokens_out":
                    continue  # handled with tokens_in
                else:
                    parts.append(f"{k}={val}")
        return " ".join(parts)

    # For agent tool use events, show tool and detail (truncated)
    if event in ("agent_tool_use",):
        tool = kv.get("tool", "")
        detail = kv.get("detail", "")
        if len(detail) > 120:
            detail = detail[:120] + "..."
        return f"tool={tool} `{detail}`" if detail else f"tool={tool}"

    if event == "agent_text":
        text = kv.get("text", "")
        if len(text) > 150:
            text = text[:150] + "..."
        return text

    # Default: show all kv pairs, truncating long values
    parts = []
    for k, v in kv.items():
        if k == "agent":
            continue  # shown in the section header
        if len(v) > 80:
            v = v[:80] + "..."
        parts.append(f"{k}={v}")
    return " ".join(parts)


def _format_agent_timeline(structlog_text: str) -> str:
    """Transform raw structlog output into a readable markdown timeline."""
    lines = structlog_text.splitlines()
    entries: list[tuple[str, str, str, str, dict[str, str]]] = []
    start_time: str | None = None

    for line in lines:
        m = _LOG_LINE_RE.match(line)
        if not m:
            continue
        _full_ts, hms, level, event, rest = m.groups()
        if start_time is None:
            start_time = hms
        kv = _parse_kv(rest or "")
        entries.append((hms, level.strip(), event, rest or "", kv))

    if not entries or start_time is None:
        return ""

    # Group by agent (or "System" for events without agent=)
    output: list[str] = ["## Agent Timeline\n"]
    current_agent: str | None = None
    table_open = False

    for hms, level, event, _rest, kv in entries:
        # Skip events with empty details from _SUMMARY_EVENTS
        if event in _SUMMARY_EVENTS and not _SUMMARY_EVENTS[event]:
            continue

        agent = kv.get("agent", "System")
        rel = _relative_time(hms, start_time)

        if agent != current_agent:
            if table_open:
                output.append("")
            output.append(f"### {agent}\n")
            output.append("| Time | Event | Details |")
            output.append("|------|-------|---------|")
            current_agent = agent
            table_open = True

        details = _format_details(event, kv)
        # Escape pipe characters in details for markdown tables
        details = details.replace("|", "\\|")
        output.append(f"| {hms} ({rel}) | `{event}` | {details} |")

    output.append("")
    return "\n".join(output)


def _save_log(thread_id: str) -> Path:
    """Export recorded console output + all structlog messages to a markdown file."""
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_path = _LOGS_DIR / f"run_{thread_id}_{ts}.md"
    console_text = console.export_text()
    structlog_text = get_log_contents()
    parts = ["# BMAD Orchestrator Run Log\n"]
    parts.append("## Console Output\n\n```\n" + console_text + "```\n")
    if structlog_text.strip():
        timeline = _format_agent_timeline(structlog_text)
        if timeline:
            parts.append(timeline)
        parts.append(
            "\n<details>\n<summary>Raw structlog output</summary>\n\n```\n"
            + structlog_text
            + "```\n\n</details>\n"
        )
    log_path.write_text("\n".join(parts))
    return log_path


def _save_last_run(thread_id: str, team_id: str, prompt: str) -> None:
    """Persist thread context so --resume can recover it without re-prompting."""
    _LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LAST_RUN_FILE.write_text(
        json.dumps({"thread_id": thread_id, "team_id": team_id, "prompt": prompt})
    )


def _load_last_run() -> dict | None:
    """Return the saved thread context, or None if not found."""
    if _LAST_RUN_FILE.exists():
        try:
            return json.loads(_LAST_RUN_FILE.read_text())
        except Exception:
            return None
    return None


def _derive_thread_id(team_id: str, prompt: str) -> str:
    return hashlib.sha256(f"{team_id}:{prompt}".encode()).hexdigest()[:16]


def _print_token_report(claude: object) -> None:
    """Render a Rich table with per-agent token usage summary."""
    from rich.table import Table

    report = claude.get_usage_report()  # type: ignore[attr-defined]
    if not report["rows"]:
        return

    mixed = report["models_mixed"]
    title = (
        "Token Usage"
        if mixed
        else f"Token Usage  |  Model: {report['model']}"
    )
    table = Table(title=title, show_footer=True, title_style="bold")
    table.add_column("Step", footer="Total", style="cyan")
    if mixed:
        table.add_column("Model", footer="")
    table.add_column(
        "Input", footer=f"{report['total_input']:,}", justify="right",
    )
    table.add_column(
        "Output", footer=f"{report['total_output']:,}", justify="right",
    )
    table.add_column(
        "Total",
        footer=f"{report['total']:,}",
        justify="right",
        style="bold",
    )
    table.add_column(
        "Calls", footer=str(report["total_calls"]), justify="right",
    )
    table.add_column(
        "Time", footer=f"{report['total_duration_s']}s", justify="right",
    )

    for row in report["rows"]:
        cells = [row["agent"]]
        if mixed:
            cells.append(row["model"])
        cells += [
            f"{row['input_tokens']:,}",
            f"{row['output_tokens']:,}",
            f"{row['total_tokens']:,}",
            str(row["calls"]),
            f"{row['duration_s']:.1f}s",
        ]
        table.add_row(*cells)

    console.print()
    console.print(table)


def _token_report_as_text(claude: object) -> str:
    """Return token usage report as plain text (for Jira comment). Empty string if no data."""
    report = claude.get_usage_report()  # type: ignore[attr-defined]
    if not report["rows"]:
        return ""

    mixed = report["models_mixed"]
    title = (
        "Token Usage"
        if mixed
        else f"Token Usage  |  Model: {report['model']}"
    )
    col_step = "Step"
    col_in = "Input"
    col_out = "Output"
    col_tot = "Total"
    col_calls = "Calls"
    col_time = "Time"
    if mixed:
        header = f"{col_step:30} {'Model':20} {col_in:>8} {col_out:>8} {col_tot:>8} {col_calls:>6} {col_time:>8}"
    else:
        header = f"{col_step:30} {col_in:>8} {col_out:>8} {col_tot:>8} {col_calls:>6} {col_time:>8}"
    sep = "-" * len(header)
    lines = [title, "", header, sep]
    for row in report["rows"]:
        if mixed:
            line = (
                f"{row['agent']:30} {row['model']:20} "
                f"{row['input_tokens']:>8,} {row['output_tokens']:>8,} "
                f"{row['total_tokens']:>8,} {row['calls']:>6} {row['duration_s']:>7.1f}s"
            )
        else:
            line = (
                f"{row['agent']:30} "
                f"{row['input_tokens']:>8,} {row['output_tokens']:>8,} "
                f"{row['total_tokens']:>8,} {row['calls']:>6} {row['duration_s']:>7.1f}s"
            )
        lines.append(line)
    lines.append(sep)
    if mixed:
        footer = (
            f"{'Total':30} {'':20} "
            f"{report['total_input']:>8,} {report['total_output']:>8,} {report['total']:>8,} "
            f"{report['total_calls']:>6} {report['total_duration_s']:>7.2f}s"
        )
    else:
        footer = (
            f"{'Total':30} "
            f"{report['total_input']:>8,} {report['total_output']:>8,} {report['total']:>8,} "
            f"{report['total_calls']:>6} {report['total_duration_s']:>7.2f}s"
        )
    lines.append(footer)
    return "\n".join(lines)


def _post_token_report_to_jira(
    claude: object,
    settings: object,
    notify_key: str | None,
) -> None:
    """Post token usage report as a new Jira comment. No-op if notify_key is falsy or dry_run."""
    if not notify_key or getattr(settings, "dry_run", True):
        return
    body_text = _token_report_as_text(claude)
    if not body_text.strip():
        return
    from bmad_orchestrator.services.service_factory import create_jira_service

    jira = create_jira_service(settings)  # type: ignore[arg-type]
    body = "h2. Token Usage\n\n{code}\n" + body_text + "\n{code}"
    jira.add_comment(notify_key, body)


@app.command()
def run(
    team_id: str | None = typer.Option(
        None, "--team-id", "-t", help="Team identifier (e.g. 'growth'). Prompted if omitted."
    ),
    prompt: str | None = typer.Option(
        None, "--prompt", "-p",
        help="Feature description or Jira epic key (e.g. 'PUG-437'). Prompted if omitted.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Simulate without side effects (no Jira/Git/PR mutations)"
    ),
    resume: bool = typer.Option(
        False, "--resume", help="Resume execution from the last checkpoint for this run"
    ),
    epic_key: str | None = typer.Option(
        None, "--epic-key", "-e", help="Existing Jira epic key to use (skips interactive selection)"
    ),
    story_key: str | None = typer.Option(
        None, "--story-key",
        help="Existing Jira story key to load and run dev_story directly (e.g. 'PUG-438'). "
             "Skips epic check, epic creation, story creation, and party mode refinement.",
    ),
    jira_only: bool = typer.Option(
        False, "--jira-only", help="Run real Jira + Claude but skip Git/GitHub operations"
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Override Claude model name"
    ),
    dummy_jira: bool = typer.Option(
        False, "--dummy-jira", help="Use file-backed dummy Jira instead of real Jira API"
    ),
    dummy_github: bool = typer.Option(
        False, "--dummy-github", help="Use file-backed dummy GitHub instead of real GitHub API"
    ),
    skip_nodes: str | None = typer.Option(
        None, "--skip-nodes", "-s",
        help="Comma-separated node names to skip (e.g. 'qa_automation,code_review')",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show full agent prompts and responses (DEBUG level)"
    ),
    retry: bool = typer.Option(
        False, "--retry",
        help="Retry from the last code-review failure: resets fix-loop counter and resumes "
             "from the unresolved issues. Implies --resume.",
    ),
    guidance: str | None = typer.Option(
        None, "--guidance", "-g",
        help="Additional instructions injected into agents on --retry or --resume "
             "(e.g. 'Focus only on fixing the SQL FK constraints').",
    ),
    max_loops: int | None = typer.Option(
        None, "--max-loops",
        help="Override BMAD_MAX_REVIEW_LOOPS (default 3). Use higher values if the architect "
             "is strict and the developer needs more iterations to converge.",
    ),
    agent_model: list[str] | None = typer.Option(
        None, "--agent-model",
        help="Per-agent model override as agent=model "
             "(e.g. --agent-model developer=claude-opus-4). Repeatable.",
    ),
    clean: bool = typer.Option(
        False, "--clean",
        help="Wipe dummy data and checkpoints before starting, ensuring a truly fresh run.",
    ),
    non_interactive: bool = typer.Option(
        False, "--non-interactive",
        help="No prompts; use defaults (e.g. force-commit on review failure). For webhook.",
    ),
) -> None:
    """Run the BMAD orchestrator end-to-end."""
    from pathlib import Path

    from dotenv import load_dotenv

    # Layered .env loading:
    # 1. Orchestrator's own .env (base defaults — Jira creds, GitHub token, etc.)
    # 2. Target project's .env (overrides — project-specific settings)
    # Shell env vars always win over both files.
    import bmad_orchestrator as _pkg

    _orchestrator_root = Path(_pkg.__file__).resolve().parent.parent.parent
    load_dotenv(_orchestrator_root / ".env", override=False)  # base defaults
    load_dotenv(Path.cwd() / ".env", override=True)  # target overrides
    configure_logging(verbose=verbose)

    # Late import so .env is loaded before Settings validates
    import os

    from bmad_orchestrator.config import Settings
    from bmad_orchestrator.graph import build_graph, make_initial_state
    from bmad_orchestrator.services.service_factory import create_jira_service
    from bmad_orchestrator.utils.cli_prompts import (
        confirm_action,
        confirm_epic,
        is_jira_key,
        prompt_feature,
        prompt_team_id,
        select_epic_from_list,
        select_skip_nodes,
    )

    # Inject CLI boolean flags into env *before* Settings() so the model_validator
    # sees them during validation (e.g. --dummy-jira skips the Jira creds check).
    if dummy_jira:
        os.environ["BMAD_DUMMY_JIRA"] = "true"
    if dummy_github:
        os.environ["BMAD_DUMMY_GITHUB"] = "true"
    if dry_run:
        os.environ["BMAD_DRY_RUN"] = "true"
    if verbose:
        os.environ["BMAD_VERBOSE"] = "true"

    # ── Story-key auto-resolution ─────────────────────────────────────────
    # When --story-key is provided (or the prompt looks like a Jira key),
    # derive team_id, prompt, epic_key, and story content from Jira so the
    # user doesn't have to pass them and so downstream nodes have the story
    # context even when create_story_tasks is skipped.
    _story_content: str | None = None
    _acceptance_criteria: list[str] | None = None

    # Auto-detect: if prompt looks like a Jira key and --story-key wasn't
    # explicitly provided, treat the prompt as the story key.
    if not story_key and prompt:
        from bmad_orchestrator.utils.cli_prompts import is_jira_key

        if is_jira_key(prompt.strip()):
            story_key = prompt.strip()
            console.print(
                f"[dim]Auto-detected story key from prompt: {story_key}[/dim]"
            )

    if story_key:
        _settings = Settings()  # type: ignore[call-arg]
        _jira = create_jira_service(_settings)
        story_data = _jira.get_story(story_key)
        if story_data is None:
            console.print(
                f"[bold red]Error:[/bold red] Story '{story_key}' not found in Jira."
            )
            raise typer.Exit(1)
        if not team_id:
            labels = story_data.get("labels") or []
            team_id = labels[0] if labels else "unknown"
        if not prompt:
            prompt = story_data.get("summary", story_key)
        if not epic_key:
            epic_key = story_data.get("parent_key")
        # Pre-load story content so it's available even if create_story_tasks
        # is skipped.
        desc = story_data.get("description") or ""
        if desc:
            from bmad_orchestrator.nodes.create_story_tasks import (
                _parse_acceptance_criteria,
            )

            _story_content = desc
            _acceptance_criteria = _parse_acceptance_criteria(desc)

    # --retry implies --resume
    if retry:
        resume = True

    # ── Interactive fallback for required inputs ──────────────────────────
    # On --resume, recover team_id/prompt from the saved last-run context so
    # the user doesn't have to re-type them just to get the same thread_id.
    if resume and (not team_id or not prompt):
        last = _load_last_run()
        if last:
            team_id = team_id or last["team_id"]
            prompt = prompt or last["prompt"]
        else:
            console.print(
                "[bold red]Error:[/bold red] --resume requires --team-id and --prompt "
                "(no previous run found in _bmad-output/.last_run)."
            )
            raise typer.Exit(1)

    if not team_id:
        team_id = prompt_team_id()
        if not team_id:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    if not prompt:
        prompt = prompt_feature()
        if not prompt:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    settings = Settings()  # type: ignore[call-arg]
    if jira_only:
        settings = settings.model_copy(update={"jira_only": True})
    if model:
        settings = settings.model_copy(update={"model_name": model})
    if max_loops is not None:
        settings = settings.model_copy(update={"max_review_loops": max_loops})
    if agent_model:
        overrides: dict[str, str] = {}
        for pair in agent_model:
            if "=" not in pair:
                console.print(
                    f"[bold red]Error:[/bold red] --agent-model must be "
                    f"agent=model, got '{pair}'"
                )
                raise typer.Exit(1)
            k, v = pair.split("=", 1)
            overrides[k.strip()] = v.strip()
        merged = {**settings.agent_models, **overrides}
        settings = settings.model_copy(update={"agent_models": merged})
    if skip_nodes is not None:
        # Explicit --skip-nodes flag: use the provided list (empty string = skip nothing)
        settings = settings.model_copy(
            update={"skip_nodes": [s.strip() for s in skip_nodes.split(",") if s.strip()]}
        )
    elif not resume and not dry_run and not non_interactive:
        # Interactive checkbox — pre-check story-related nodes if --story-key
        pre_checked: list[str] = []
        if story_key:
            pre_checked = [
                "check_epic_state",
                "create_or_correct_epic",
                "party_mode_refinement",
            ]
        chosen_skips = select_skip_nodes(pre_checked=pre_checked)
        if chosen_skips:
            settings = settings.model_copy(update={"skip_nodes": chosen_skips})

    # ── Interactive epic resolution (before graph starts) ────────────────
    original_prompt = prompt  # preserve for stable thread_id
    resolved_epic_key: str | None = epic_key  # --epic-key wins if provided

    if not resume and not resolved_epic_key and not dry_run and not non_interactive:
        jira = create_jira_service(settings)

        if is_jira_key(prompt.strip()):
            # Prompt looks like a Jira key — validate and confirm
            epic_data = jira.get_epic(prompt.strip())
            if epic_data is None:
                console.print(
                    f"[bold red]Error:[/bold red] '{prompt}' is not a valid Epic "
                    f"or does not exist in Jira."
                )
                raise typer.Exit(1)

            if confirm_epic(epic_data):
                resolved_epic_key = epic_data["key"]
                prompt = epic_data["summary"]
            else:
                console.print("[yellow]Aborted by user.[/yellow]")
                raise typer.Exit(0)

        else:
            # Free text — show open epics and let user choose
            epics = jira.find_epic_by_team(team_id)

            if epics:
                console.print(
                    f"\n[bold]Found {len(epics)} open epic(s) "
                    f"in project {settings.jira_project_key}:[/bold]\n"
                )
                chosen = select_epic_from_list(epics)
                if chosen is not None:
                    resolved_epic_key = chosen["key"]
                else:
                    console.print("[dim]Will create a new epic.[/dim]")
                    # User explicitly chose to create a new epic — skip check_epic_state
                    # so the LLM evaluation inside that node cannot override this choice.
                    settings = settings.model_copy(
                        update={"skip_nodes": list(settings.skip_nodes) + ["check_epic_state"]}
                    )
            else:
                console.print(
                    f"[dim]No open epics found in {settings.jira_project_key}. "
                    f"A new epic will be created.[/dim]"
                )

        # Final confirmation gate before any Jira writes (skip when non-interactive)
        if not non_interactive:
            if resolved_epic_key:
                if not confirm_action(
                    f"Will proceed with epic [bold]{resolved_epic_key}[/bold] "
                    f"and create stories/tasks in Jira."
                ):
                    console.print("[yellow]Aborted by user.[/yellow]")
                    raise typer.Exit(0)
            else:
                if not confirm_action(
                    "Will create a [bold]new epic[/bold] and stories/tasks in Jira."
                ):
                    console.print("[yellow]Aborted by user.[/yellow]")
                    raise typer.Exit(0)

    # ── Clean stale data if requested ───────────────────────────────────
    if clean:
        import shutil

        cleaned: list[str] = []
        dummy_dir = Path(settings.dummy_data_dir).expanduser()
        if dummy_dir.exists():
            shutil.rmtree(dummy_dir)
            cleaned.append(f"dummy data ({dummy_dir})")
        db_path = Path(settings.checkpoint_db_path).expanduser()
        if db_path.exists():
            db_path.unlink()
            cleaned.append(f"checkpoints ({db_path})")
        if _LAST_RUN_FILE.exists():
            _LAST_RUN_FILE.unlink()
            cleaned.append("last-run context")
        if cleaned:
            console.print(f"[bold cyan]Cleaned:[/bold cyan] {', '.join(cleaned)}")
        else:
            console.print("[dim]--clean: nothing to remove (already clean)[/dim]")

    # ── Build graph and derive thread ────────────────────────────────────
    graph, checkpointer, claude = build_graph(settings, console=console)
    thread_id = _derive_thread_id(team_id, original_prompt)
    config: dict = {"configurable": {"thread_id": thread_id}}

    # Persist context so next --resume doesn't need to re-prompt
    _save_last_run(thread_id, team_id, original_prompt)

    # ── Resolve initial state vs resume ────────────────────────────────────
    stream_input: dict | None  # None = resume from checkpoint
    if resume:
        snapshot = graph.get_state(config)
        if not snapshot or not snapshot.values:
            console.print(
                f"[bold red]Error:[/bold red] No checkpoint found for thread {thread_id}. "
                f"Cannot resume."
            )
            raise typer.Exit(1)

        failure = snapshot.values.get("failure_state")
        issues = snapshot.values.get("code_review_issues") or []
        if retry and (failure or issues):
            # Re-inject state to restart the fix loop from the last unresolved issues.
            # as_node="code_review" positions the cursor after code_review so the
            # conditional edge re-evaluates: loop_count=0 < max → dev_story_fix_loop.
            update: dict = {"failure_state": None, "review_loop_count": 0}
            if guidance:
                update["retry_guidance"] = guidance
            graph.update_state(config, update, as_node="code_review")
            console.print(
                f"[bold cyan]Retrying[/bold cyan] thread {thread_id}: "
                f"reset fix-loop counter, re-entering from unresolved issues."
            )
        else:
            # No code-review failure to reset — fall through to plain resume.
            if guidance:
                graph.update_state(config, {"retry_guidance": guidance})
            last_tasks = snapshot.next
            console.print(
                f"[bold cyan]Resuming[/bold cyan] thread {thread_id} "
                f"from [bold]{', '.join(last_tasks) if last_tasks else 'END'}[/bold]"
            )
        stream_input = None
    else:
        stream_input = make_initial_state(
            team_id, prompt, epic_key=resolved_epic_key, story_key=story_key,
            story_content=_story_content,
            acceptance_criteria=_acceptance_criteria,
        )

    # ── Print run header ──────────────────────────────────────────────────
    console.print(
        Panel(
            f"[bold]Team:[/bold] {team_id}\n"
            f"[bold]Epic:[/bold] {resolved_epic_key or '(will be auto-created)'}\n"
            f"[bold]Prompt:[/bold] {prompt}\n"
            f"[bold]Dry run:[/bold] {dry_run}\n"
            f"[bold]Jira only:[/bold] {jira_only}\n"
            f"[bold]Dummy Jira:[/bold] {settings.dummy_jira}\n"
            f"[bold]Dummy GitHub:[/bold] {settings.dummy_github}\n"
            f"[bold]Thread:[/bold] {thread_id}"
            + ("\n[bold]Mode:[/bold] resume" if resume else "")
            + (f"\n[bold]Guidance:[/bold] {guidance}" if guidance else "")
            + (
                f"\n[bold]Skipping:[/bold] {', '.join(settings.skip_nodes)}"
                if settings.skip_nodes
                else ""
            ),
            title="[bold blue]BMAD Orchestrator[/bold blue]",
        )
    )

    _MEDIUM_PLUS = {"medium", "high", "critical"}

    try:
        for event in graph.stream(stream_input, config=config, stream_mode="updates"):
            for node_name, update in event.items():
                console.print(f"  [green]✓[/green] {node_name}")

                # ── Per-node detail ────────────────────────────────────────
                if node_name == "code_review":
                    issues = update.get("code_review_issues") or []
                    if issues:
                        mp = [i for i in issues if i["severity"] in _MEDIUM_PLUS]
                        console.print(
                            f"    [dim]  → {len(issues)} issue(s) found, "
                            f"{len(mp)} medium+[/dim]"
                        )
                        for iss in issues:
                            sev = iss["severity"].upper()
                            color = "red" if sev in {"HIGH", "CRITICAL"} else "yellow"
                            desc = iss["description"][:120].replace("\n", " ")
                            console.print(
                                f"    [{color}]  [{sev}][/{color}] "
                                f"[bold]{iss['file']}[/bold]: {desc}"
                            )

                elif node_name == "dev_story_fix_loop":
                    touched = update.get("touched_files") or []
                    if touched:
                        from pathlib import Path as _Path
                        names = ", ".join(_Path(p).name for p in touched[:6])
                        console.print(
                            f"    [dim]  → rewrote {len(touched)} file(s): {names}[/dim]"
                        )
    except Exception as exc:
        import subprocess as _sp

        console.print(f"\n[bold red]Error:[/bold red] {exc}")
        # Show subprocess stderr (e.g. gh, git failures)
        if isinstance(exc, _sp.CalledProcessError) and exc.stderr:
            console.print(f"[red]stderr:[/red] {exc.stderr.strip()}")
        # Walk the exception chain for wrapped subprocess errors
        cause = exc.__cause__ or exc.__context__
        if isinstance(cause, _sp.CalledProcessError) and cause.stderr:
            console.print(f"[red]stderr:[/red] {cause.stderr.strip()}")
        # Attempt to show checkpoint state for debugging
        snapshot = None
        try:
            snapshot = graph.get_state(config)
            if snapshot and snapshot.values.get("failure_state"):
                console.print(f"[red]Failure state:[/red] {snapshot.values['failure_state']}")
        except Exception:
            pass
        _print_token_report(claude)
        _notify_key = (
            snapshot.values.get("notify_jira_story_key")
            if snapshot and snapshot.values
            else None
        ) or story_key
        _post_token_report_to_jira(claude, settings, _notify_key)
        log_path = _save_log(thread_id)
        console.print(f"[dim]Log saved to {log_path}[/dim]")
        raise typer.Exit(1) from exc

    # ── Show final result ─────────────────────────────────────────────────
    final = graph.get_state(config)
    if final and final.values:
        pr_url = final.values.get("pr_url")
        failure = final.values.get("failure_state")

        if failure:
            # Graph now routes fail_with_state → commit_and_push → create_pull_request
            # automatically, so a draft PR with failure context should already exist.
            console.print(f"\n[bold yellow]Pipeline failed.[/bold yellow] {failure[:400]}")
            if pr_url:
                console.print(
                    Panel(
                        f"[bold yellow]Draft PR (with failure context):[/bold yellow] {pr_url}",
                        title="[bold yellow]Failed — draft PR created[/bold yellow]",
                    )
                )
        elif pr_url:
            console.print(
                Panel(
                    f"[bold green]PR created:[/bold green] {pr_url}",
                    title="[bold green]Done![/bold green]",
                )
            )
        elif dry_run:
            console.print("\n[bold cyan]Dry run complete — no side effects applied.[/bold cyan]")

    _print_token_report(claude)
    _post_token_report_to_jira(
        claude, settings,
        (final.values.get("notify_jira_story_key") if final and final.values else None) or story_key,
    )
    log_path = _save_log(thread_id)
    console.print(f"[dim]Log saved to {log_path}[/dim]")


@app.command()
def state(
    team_id: str | None = typer.Option(
        None, "--team-id", "-t", help="Team identifier used in the original run."
    ),
    prompt: str | None = typer.Option(
        None, "--prompt", "-p", help="Prompt used in the original run."
    ),
    full: bool = typer.Option(
        False, "--full", "-f", help="Show full field values without truncation."
    ),
) -> None:
    """Print the current checkpoint state for a previous run."""
    from pathlib import Path

    from dotenv import load_dotenv
    from rich.syntax import Syntax

    import bmad_orchestrator as _pkg

    _orchestrator_root = Path(_pkg.__file__).resolve().parent.parent.parent
    load_dotenv(_orchestrator_root / ".env", override=False)
    load_dotenv(Path.cwd() / ".env", override=True)

    # Recover team_id/prompt from last run if not provided
    if not team_id or not prompt:
        last = _load_last_run()
        if last:
            team_id = team_id or last["team_id"]
            prompt = prompt or last["prompt"]
        else:
            console.print(
                "[bold red]Error:[/bold red] No previous run found. "
                "Pass --team-id and --prompt to identify the run."
            )
            raise typer.Exit(1)

    import json

    from bmad_orchestrator.config import Settings
    from bmad_orchestrator.graph import build_graph

    thread_id = _derive_thread_id(team_id, prompt)
    config: dict = {"configurable": {"thread_id": thread_id}}

    settings = Settings()  # type: ignore[call-arg]
    graph, _, _ = build_graph(settings)
    snapshot = graph.get_state(config)

    if not snapshot or not snapshot.values:
        console.print(f"[yellow]No checkpoint found for thread {thread_id}.[/yellow]")
        raise typer.Exit(1)

    values = dict(snapshot.values)

    # Truncate long text fields for readability (unless --full)
    if not full:
        _MAX = 500
        for key in ("story_content", "architect_output", "developer_output",
                    "project_context", "dev_guidelines", "failure_state"):
            if values.get(key) and len(str(values[key])) > _MAX:
                values[key] = str(values[key])[:_MAX] + "..."

    console.print(Panel(
        f"[bold]Thread:[/bold] {thread_id}\n"
        f"[bold]Next node(s):[/bold] {', '.join(snapshot.next) if snapshot.next else 'END'}",
        title="[bold blue]Checkpoint State[/bold blue]",
    ))
    console.print(Syntax(
        json.dumps(values, indent=2, default=str),
        "json",
        theme="monokai",
    ))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
