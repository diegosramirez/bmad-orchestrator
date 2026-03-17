"""Minimal FastAPI app that receives Jira webhook POST and dispatches a GitHub Actions run."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from bmad_orchestrator.webhook.jira_payload import parse_jira_webhook
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="BMAD Jira Webhook", version="0.1.0")

# Folder to save each POST (in the project, or configurable by env)
_WEBHOOK_DIR = Path(__file__).resolve().parent.parent.parent
WEBHOOK_STORE_DIR = _WEBHOOK_DIR / "webhook_payloads"

WEBHOOK_STORE_DIR.mkdir(parents=True, exist_ok=True)

BMAD_GITHUB_OWNER = os.getenv("BMAD_GITHUB_OWNER", "")
BMAD_GITHUB_REPO_TO_WORK = ""

GITHUB_REPO = os.getenv("BMAD_GITHUB_REPO", "")
GITHUB_TOKEN = os.getenv("BMAD_GITHUB_TOKEN")
DEFAULT_TARGET_REPO = os.getenv("DEFAULT_TARGET_REPO", "")
DEFAULT_TEAM_ID = os.getenv("DEFAULT_TEAM_ID", "")
DEFAULT_REF = os.getenv("BMAD_GITHUB_BASE_BRANCH", "main")


async def _dispatch_github_workflow_from_jira(ctx) -> tuple[bool, int | None, str | None]:
    """Dispatch the bmad-start-run.yml GitHub Actions workflow using Jira context.

    Returns a tuple of (ok, status_code, error_body).
    """
    if not GITHUB_REPO or not GITHUB_TOKEN:
        return False, None, "Missing GITHUB_REPO or GITHUB_TOKEN"

    inputs: dict[str, str] = {
        # Prefer target_repo coming from the Jira payload; fall back to env default.
        "target_repo": ctx.target_repo or DEFAULT_TARGET_REPO,
        "team_id": ctx.team_id or DEFAULT_TEAM_ID,
        "prompt": ctx.prompt,
        "slack_verbose": "false",
    }

    extra_flags: list[str] = []
    if getattr(ctx, "epic_key", None):
        extra_flags.extend(["--epic-key", ctx.epic_key])
    if getattr(ctx, "story_key", None):
        extra_flags.extend(["--story-key", ctx.story_key])
    if extra_flags:
        inputs["extra_flags"] = " ".join(extra_flags)

    for node in ("check_epic_state", "create_or_correct_epic", "create_story_tasks"):
        inputs[f"skip_{node}"] = "true"

    url = (
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/"
        "bmad-start-run.yml/dispatches"
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "bmad-jira-webhook",
                },
                json={"ref": DEFAULT_REF, "inputs": inputs},
                timeout=30.0,
            )
    except Exception as exc:  # noqa: BLE001
        return False, None, f"Request error: {exc}"

    if resp.status_code != 204:
        try:
            body_text = resp.text
        except Exception:  # noqa: BLE001
            body_text = "<unavailable>"
        return False, resp.status_code, body_text

    return True, resp.status_code, None


@app.post("/bmad/jira-webhook")
async def jira_webhook(request: Request):
    """Receive the Jira POST, save the body, and dispatch a GitHub Actions workflow."""
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
                "message": (
                    "Payload saved; run not started "
                    "(missing context or story has no parent epic)."
                ),
            },
            status_code=200,
        )

    ok, dispatch_status, dispatch_error = await _dispatch_github_workflow_from_jira(ctx)

    github_actions_url = (
        f"https://github.com/{GITHUB_REPO}/actions/workflows/bmad-start-run.yml"
        if GITHUB_REPO
        else None
    )

    content: dict[str, object] = {
        "ok": True,
        "saved": str(path),
        "run_started": ok,
    }
    if github_actions_url is not None:
        content["actions_url"] = github_actions_url
    content["message"] = (
        "GitHub Actions workflow dispatched."
        if ok
        else "Payload saved, but failed to dispatch GitHub Actions workflow."
    )
    if dispatch_status is not None:
        content["dispatch_status"] = dispatch_status
    if dispatch_error is not None:
        content["dispatch_error"] = dispatch_error

    return JSONResponse(
        content=content,
        status_code=202 if ok else 500,
    )


@app.get("/health")
async def health():
    return {"status": "ok"}