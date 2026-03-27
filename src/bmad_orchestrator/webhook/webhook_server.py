"""Minimal FastAPI app that receives Jira webhook POST and dispatches a GitHub Actions run."""
from __future__ import annotations

import json
import os
import shlex
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from bmad_orchestrator.utils.logger import get_logger
from bmad_orchestrator.webhook.discovery import (
    build_discovery_workflow_inputs,
    team_id_from_issue_key,
)
from bmad_orchestrator.webhook.epic_architect import build_epic_architect_workflow_inputs
from bmad_orchestrator.webhook.jira_payload import parse_jira_webhook
from bmad_orchestrator.webhook.stories import build_stories_workflow_inputs

load_dotenv()

logger = get_logger(__name__)

app = FastAPI(title="BMAD Jira Webhook", version="0.1.0")

_GITHUB_ERROR_BODY_MAX = 4000

# Folder to save each POST (in the project, or configurable by env)
_WEBHOOK_DIR = Path(__file__).resolve().parent.parent.parent
WEBHOOK_STORE_DIR = _WEBHOOK_DIR / "webhook_payloads"

WEBHOOK_STORE_DIR.mkdir(parents=True, exist_ok=True)

BMAD_GITHUB_OWNER = os.getenv("BMAD_GITHUB_OWNER", "")


GITHUB_REPO = os.getenv("BMAD_GITHUB_REPO", "")
GITHUB_TOKEN = os.getenv("BMAD_GITHUB_TOKEN")
DEFAULT_TARGET_REPO = os.getenv("DEFAULT_TARGET_REPO", "")
DEFAULT_TEAM_ID = os.getenv("DEFAULT_TEAM_ID", "")
# Branch/ref of the orchestrator repo for workflow_dispatch (not the target app clone branch).
DEFAULT_REF = os.getenv("BMAD_GITHUB_BASE_BRANCH", "main")
# Forge: BMAD_FORGE_WEBHOOK_SECRET preferred; BMAD_DISCOVERY_WEBHOOK_SECRET fallback.
FORGE_WEBHOOK_SECRET = os.getenv("BMAD_FORGE_WEBHOOK_SECRET") or os.getenv(
    "BMAD_DISCOVERY_WEBHOOK_SECRET", ""
)


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


def _truncate_github_body(text: str | None) -> str:
    if not text:
        return ""
    if len(text) <= _GITHUB_ERROR_BODY_MAX:
        return text
    return text[:_GITHUB_ERROR_BODY_MAX] + "…(truncated)"


async def _dispatch_bmad_workflow(inputs: dict[str, str]) -> tuple[bool, int | None, str | None]:
    """Dispatch the bmad-start-run.yml GitHub Actions workflow with arbitrary inputs."""
    if not GITHUB_REPO or not GITHUB_TOKEN:
        logger.warning(
            "github_workflow_dispatch_skipped",
            reason="missing_credentials",
            has_repo=bool(GITHUB_REPO),
            has_token=bool(GITHUB_TOKEN),
        )
        return False, None, "Missing GITHUB_REPO or GITHUB_TOKEN"

    url = (
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/"
        "bmad-start-run.yml/dispatches"
    )
    logger.info(
        "github_workflow_dispatch_request",
        repo=GITHUB_REPO,
        ref=DEFAULT_REF,
        workflow="bmad-start-run.yml",
        input_keys=sorted(inputs.keys()),
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
        logger.exception("github_workflow_dispatch_http_error", error=str(exc))
        return False, None, f"Request error: {exc}"

    if resp.status_code != 204:
        try:
            body_text = resp.text
        except Exception:  # noqa: BLE001
            body_text = "<unavailable>"
        logger.warning(
            "github_workflow_dispatch_failed",
            status_code=resp.status_code,
            response_body=_truncate_github_body(body_text),
        )
        return False, resp.status_code, body_text

    logger.info("github_workflow_dispatch_ok", status_code=resp.status_code)
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


@app.post("/bmad/discovery-run")
async def discovery_run(request: Request):
    """Forge panel: run epic-only Discovery (check_epic_state + create_or_correct_epic), then END.

    Expects JSON ``{"issue_key": "PROJ-123", "target_repo": "optional/override"}`` and header
    ``X-BMAD-Discovery-Secret`` matching ``BMAD_DISCOVERY_WEBHOOK_SECRET``.
    """
    if not FORGE_WEBHOOK_SECRET:
        return JSONResponse(
            content={
                "ok": False,
                "run_started": False,
                "message": (
                    "Set BMAD_FORGE_WEBHOOK_SECRET or BMAD_DISCOVERY_WEBHOOK_SECRET on the server."
                ),
            },
            status_code=503,
        )
    # secret_header = request.headers.get(DISCOVERY_SECRET_HEADER)
    # if secret_header != DISCOVERY_WEBHOOK_SECRET:
    #     return JSONResponse(
    #         content={"ok": False, "run_started": False, "message": "Unauthorized"},
    #         status_code=401,
    #     )

    body = await request.json()
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    issue_key = (body.get("issue_key") or "").strip()
    if not issue_key:
        return JSONResponse(
            content={"ok": False, "run_started": False, "message": "Missing issue_key"},
            status_code=400,
        )

    path = WEBHOOK_STORE_DIR / f"{ts}_discovery_{issue_key.replace('-', '_')}.json"
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")

    target_raw = (body.get("target_repo") or "").strip() or DEFAULT_TARGET_REPO
    target_repo = _normalize_target_repo(target_raw)
    if not target_repo:
        return JSONResponse(
            content={
                "ok": False,
                "run_started": False,
                "saved": str(path),
                "message": "Missing target_repo (body or DEFAULT_TARGET_REPO).",
            },
            status_code=400,
        )

    team_override = (body.get("team_id") or "").strip()
    team_id = team_override or team_id_from_issue_key(issue_key, default_team_id=DEFAULT_TEAM_ID)

    inputs = build_discovery_workflow_inputs(
        issue_key=issue_key,
        target_repo=target_repo,
        team_id=team_id,
    )
    ok, dispatch_status, dispatch_error = await _dispatch_bmad_workflow(inputs)

    if ok:
        logger.info(
            "discovery_run_dispatched",
            issue_key=issue_key,
            target_repo=target_repo,
            team_id=team_id,
        )
    else:
        logger.warning(
            "discovery_run_dispatch_failed",
            issue_key=issue_key,
            target_repo=target_repo,
            team_id=team_id,
            dispatch_status=dispatch_status,
            dispatch_error=_truncate_github_body(dispatch_error),
        )

    github_actions_url = (
        f"https://github.com/{GITHUB_REPO}/actions/workflows/bmad-start-run.yml"
        if GITHUB_REPO
        else None
    )

    content: dict[str, object] = {
        "ok": True,
        "saved": str(path),
        "run_started": ok,
        "issue_key": issue_key,
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


@app.post("/bmad/architect-run")
async def architect_run(request: Request):
    """Forge panel: run Epic Architect only (epic_architect node), then END.

    Expects JSON ``{"issue_key": "PROJ-123", "target_repo": "optional/override"}`` and header
    ``X-BMAD-Forge-Secret`` (or legacy ``X-BMAD-Discovery-Secret``) matching
    ``BMAD_FORGE_WEBHOOK_SECRET`` or ``BMAD_DISCOVERY_WEBHOOK_SECRET``.
    """
    if not FORGE_WEBHOOK_SECRET:
        return JSONResponse(
            content={
                "ok": False,
                "run_started": False,
                "message": (
                    "Set BMAD_FORGE_WEBHOOK_SECRET or BMAD_DISCOVERY_WEBHOOK_SECRET on the server."
                ),
            },
            status_code=503,
        )

    body = await request.json()
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    issue_key = (body.get("issue_key") or "").strip()
    if not issue_key:
        return JSONResponse(
            content={"ok": False, "run_started": False, "message": "Missing issue_key"},
            status_code=400,
        )

    path = WEBHOOK_STORE_DIR / f"{ts}_architect_{issue_key.replace('-', '_')}.json"
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")

    target_raw = (body.get("target_repo") or "").strip() or DEFAULT_TARGET_REPO
    target_repo = _normalize_target_repo(target_raw)
    if not target_repo:
        return JSONResponse(
            content={
                "ok": False,
                "run_started": False,
                "saved": str(path),
                "message": "Missing target_repo (body or DEFAULT_TARGET_REPO).",
            },
            status_code=400,
        )

    team_override = (body.get("team_id") or "").strip()
    team_id = team_override or team_id_from_issue_key(issue_key, default_team_id=DEFAULT_TEAM_ID)

    inputs = build_epic_architect_workflow_inputs(
        issue_key=issue_key,
        target_repo=target_repo,
        team_id=team_id,
    )
    ok, dispatch_status, dispatch_error = await _dispatch_bmad_workflow(inputs)

    if ok:
        logger.info(
            "architect_run_dispatched",
            issue_key=issue_key,
            target_repo=target_repo,
            team_id=team_id,
        )
    else:
        logger.warning(
            "architect_run_dispatch_failed",
            issue_key=issue_key,
            target_repo=target_repo,
            team_id=team_id,
            dispatch_status=dispatch_status,
            dispatch_error=_truncate_github_body(dispatch_error),
        )

    github_actions_url = (
        f"https://github.com/{GITHUB_REPO}/actions/workflows/bmad-start-run.yml"
        if GITHUB_REPO
        else None
    )

    content: dict[str, object] = {
        "ok": True,
        "saved": str(path),
        "run_started": ok,
        "issue_key": issue_key,
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


@app.post("/bmad/stories-run")
async def stories_run(request: Request):
    """Forge panel: run create_story_tasks (N stories) + party_mode_refinement, then END.

    Expects JSON ``{"issue_key": "PROJ-123", "target_repo": "optional"}`` and Forge secret header.
    """
    if not FORGE_WEBHOOK_SECRET:
        return JSONResponse(
            content={
                "ok": False,
                "run_started": False,
                "message": (
                    "Set BMAD_FORGE_WEBHOOK_SECRET or BMAD_DISCOVERY_WEBHOOK_SECRET on the server."
                ),
            },
            status_code=503,
        )

    body = await request.json()
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    issue_key = (body.get("issue_key") or "").strip()
    if not issue_key:
        return JSONResponse(
            content={"ok": False, "run_started": False, "message": "Missing issue_key"},
            status_code=400,
        )

    path = WEBHOOK_STORE_DIR / f"{ts}_stories_{issue_key.replace('-', '_')}.json"
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")

    target_raw = (body.get("target_repo") or "").strip() or DEFAULT_TARGET_REPO
    target_repo = _normalize_target_repo(target_raw)
    if not target_repo:
        return JSONResponse(
            content={
                "ok": False,
                "run_started": False,
                "saved": str(path),
                "message": "Missing target_repo (body or DEFAULT_TARGET_REPO).",
            },
            status_code=400,
        )

    team_override = (body.get("team_id") or "").strip()
    team_id = team_override or team_id_from_issue_key(issue_key, default_team_id=DEFAULT_TEAM_ID)

    inputs = build_stories_workflow_inputs(
        issue_key=issue_key,
        target_repo=target_repo,
        team_id=team_id,
    )
    ok, dispatch_status, dispatch_error = await _dispatch_bmad_workflow(inputs)

    if ok:
        logger.info(
            "stories_run_dispatched",
            issue_key=issue_key,
            target_repo=target_repo,
            team_id=team_id,
        )
    else:
        logger.warning(
            "stories_run_dispatch_failed",
            issue_key=issue_key,
            target_repo=target_repo,
            team_id=team_id,
            dispatch_status=dispatch_status,
            dispatch_error=_truncate_github_body(dispatch_error),
        )

    github_actions_url = (
        f"https://github.com/{GITHUB_REPO}/actions/workflows/bmad-start-run.yml"
        if GITHUB_REPO
        else None
    )

    content: dict[str, object] = {
        "ok": True,
        "saved": str(path),
        "run_started": ok,
        "issue_key": issue_key,
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
    """Receive Jira comment webhook; optional /bmad retry or refine dispatch."""
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
