"""Minimal FastAPI app that receives Jira webhook POST and stores the body."""
from __future__ import annotations

import asyncio
import json
import shlex
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from bmad_orchestrator.webhook.jira_payload import parse_jira_webhook

app = FastAPI(title="BMAD Jira Webhook", version="0.1.0")

# Folder to save each POST (in the project, or configurable by env)
_WEBHOOK_DIR = Path(__file__).resolve().parent.parent.parent
WEBHOOK_STORE_DIR = _WEBHOOK_DIR / "webhook_payloads"
# App root (where pyproject.toml is) for running bmad-orchestrator
APP_ROOT = _WEBHOOK_DIR.parent
BMAD_OUTPUT_DIR = APP_ROOT / "_bmad-output"
SKIP_NODES = "check_epic_state,create_or_correct_epic,create_story_tasks"

WEBHOOK_STORE_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/bmad/jira-webhook")
async def jira_webhook(request: Request):
    """Receive the Jira POST, save the body, and optionally start an orchestrator run."""
    body = await request.json()
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    key = body.get("issue", {}).get("key", "unknown")
    safe_key = key.replace("-", "_")
    path = WEBHOOK_STORE_DIR / f"{ts}_{safe_key}.json"
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")

    ctx = parse_jira_webhook(body)
    if ctx is None or ctx.epic_key is None:
        return JSONResponse(
            content={
                "ok": True,
                "saved": str(path),
                "run_started": False,
                "message": "Payload saved; run not started (missing context or story has no parent epic).",
            },
            status_code=200,
        )

    BMAD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_path = BMAD_OUTPUT_DIR / f"webhook-run-{ctx.story_key.replace('-', '_')}-{log_ts}.log"
    prompt_quoted = shlex.quote(ctx.prompt)
    cmd = (
        f"uv run bmad-orchestrator run "
        f"--team-id {shlex.quote(ctx.team_id)} "
        f"--epic-key {shlex.quote(ctx.epic_key)} "
        f"--story-key {shlex.quote(ctx.story_key)} "
        f"--skip-nodes {shlex.quote(SKIP_NODES)} "
        f"--prompt {prompt_quoted} "
        f"--non-interactive "
        f"> {shlex.quote(str(log_path))} 2>&1"
    )
    await asyncio.create_subprocess_shell(cmd, cwd=str(APP_ROOT))

    return JSONResponse(
        content={
            "ok": True,
            "saved": str(path),
            "run_started": True,
            "log_path": str(log_path),
            "message": f"Orchestrator run started. Watch progress: tail -f {log_path}",
        },
        status_code=202,
    )


@app.get("/health")
async def health():
    return {"status": "ok"}