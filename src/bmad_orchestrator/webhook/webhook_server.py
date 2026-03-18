"""Minimal FastAPI app that receives Jira webhook POST and dispatches a GitHub Actions run."""
from __future__ import annotations

import json
import os
import shlex
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


GITHUB_REPO = os.getenv("BMAD_GITHUB_REPO", "")
GITHUB_TOKEN = os.getenv("BMAD_GITHUB_TOKEN")
DEFAULT_TARGET_REPO = os.getenv("DEFAULT_TARGET_REPO", "")
DEFAULT_TEAM_ID = os.getenv("DEFAULT_TEAM_ID", "")
DEFAULT_REF = os.getenv("BMAD_GITHUB_BASE_BRANCH", "main")


def _normalize_target_repo(raw: str | None) -> str:
    """Normalize target_repo to OWNER/REPO for GitHub CLI.

    Jira customfield_10112.value can be either:
    - "my-test-app" (slug only)
    - "owner/my-test-app" (already normalized)
    """
    value = (raw or "").strip()
    if not value:
        return ""
    if "/" in value:
        return value
    if BMAD_GITHUB_OWNER:
        return f"{BMAD_GITHUB_OWNER}/{value}"
    return value


async def _dispatch_bmad_workflow(inputs: dict[str, str]) -> tuple[bool, int | None, str | None]:
    """Dispatch the bmad-start-run.yml GitHub Actions workflow with arbitrary inputs."""
    if not GITHUB_REPO or not GITHUB_TOKEN:
        return False, None, "Missing GITHUB_REPO or GITHUB_TOKEN"

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


async def _dispatch_github_workflow_from_jira(ctx) -> tuple[bool, int | None, str | None]:
    """Dispatch the bmad-start-run.yml GitHub Actions workflow using Jira issue context."""
    target_repo_raw = ctx.target_repo or DEFAULT_TARGET_REPO
    target_repo = _normalize_target_repo(target_repo_raw)
    inputs: dict[str, str] = {
        # Prefer target_repo coming from the Jira payload; fall back to env default.
        "target_repo": target_repo,
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

    return await _dispatch_bmad_workflow(inputs)


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


@app.post("/bmad/jira-comment-webhook")
async def jira_comment_webhook(request: Request):
    """Receive Jira comment webhook, optionally dispatch a retry/refine run based on /bmad commands."""
    body = await request.json()
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    key = body.get("issue", {}).get("key", "unknown")
    safe_key = key.replace("-", "_")
    path = WEBHOOK_STORE_DIR / f"{ts}_{safe_key}_comment.json"
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")

    comment = body.get("comment") or {}
    comment_body = (comment.get("body") or "").strip()

    # Ignore comments that do not start with /bmad
    if not comment_body.startswith("/bmad"):
        return JSONResponse(
            content={
                "ok": True,
                "saved": str(path),
                "run_started": False,
                "message": "Comment does not contain a /bmad command; no run started.",
            },
            status_code=200,
        )

    try:
        tokens = shlex.split(comment_body)
    except ValueError as exc:
        return JSONResponse(
            content={
                "ok": False,
                "saved": str(path),
                "run_started": False,
                "message": f"Invalid /bmad command syntax: {exc}",
            },
            status_code=400,
        )

    if len(tokens) < 2:
        return JSONResponse(
            content={
                "ok": False,
                "saved": str(path),
                "run_started": False,
                "message": 'Usage: /bmad retry "guidance" or /bmad refine "guidance"',
            },
            status_code=400,
        )

    subcommand = tokens[1]
    if subcommand not in {"retry", "refine"}:
        return JSONResponse(
            content={
                "ok": False,
                "saved": str(path),
                "run_started": False,
                "message": f"Unknown /bmad subcommand: {subcommand}",
            },
            status_code=400,
        )

    # Guidance: optional third token (in quotes), e.g. /bmad retry "fix the auth"
    guidance = tokens[2] if len(tokens) >= 3 else ""

    issue = body.get("issue") or {}
    issue_key = issue.get("key") or "unknown"
    fields = issue.get("fields") or {}

    # Branch from customfield_10145 (BMAD Branch) — required for retry/refine
    branch_val = fields.get("customfield_10145")
    branch = (branch_val.strip() if isinstance(branch_val, str) and branch_val else "") or ""
    if not branch:
        return JSONResponse(
            content={
                "ok": False,
                "saved": str(path),
                "run_started": False,
                "message": (
                    "Missing branch. Ensure the issue has customfield_10145 (BMAD Branch) set, "
                    "e.g. by running the pipeline once so BMAD can save the branch."
                ),
            },
            status_code=400,
        )

    # team_id from issue key prefix (e.g. SAM1-61 -> SAM1)
    team_id = DEFAULT_TEAM_ID
    if isinstance(issue_key, str) and "-" in issue_key:
        team_id = issue_key.split("-", 1)[0]

    # target_repo from customfield_10112.value if present, otherwise fallback to DEFAULT_TARGET_REPO
    target_repo_raw = ""
    custom_target = fields.get("customfield_10112")
    if isinstance(custom_target, dict):
        value = custom_target.get("value")
        if isinstance(value, str) and value.strip():
            target_repo_raw = value.strip()

    if not target_repo_raw:
        target_repo_raw = DEFAULT_TARGET_REPO
    target_repo = _normalize_target_repo(target_repo_raw)

    inputs: dict[str, str] = {
        "target_repo": target_repo,
        "team_id": team_id,
        "prompt": issue_key,
        "slack_verbose": "false",
        "branch": branch,
        "guidance": guidance,
    }

    # For retry/refine flows, skip planning and detection nodes.
    for node in (
        "check_epic_state",
        "create_or_correct_epic",
        "create_story_tasks",
        "party_mode_refinement",
        "detect_commands",
    ):
        inputs[f"skip_{node}"] = "true"

    ok, dispatch_status, dispatch_error = await _dispatch_bmad_workflow(inputs)

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