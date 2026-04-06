"""Detect an in-flight GitHub Actions run for the same workflow_dispatch ``prompt``."""
from __future__ import annotations

import os
from typing import Any

import httpx

from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

BMAD_WORKFLOW_FILE = "bmad-start-run.yml"

# GitHub workflow run ``status`` values that mean the job is not finished yet.
ACTIVE_RUN_STATUSES = frozenset(
    {
        "queued",
        "in_progress",
        "waiting",
        "requested",
        "pending",
    }
)

_GITHUB_HEADERS_BASE = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "bmad-jira-webhook",
}


def _github_auth_headers(token: str) -> dict[str, str]:
    return {**_GITHUB_HEADERS_BASE, "Authorization": f"Bearer {token}"}


def _run_matches_issue_key(run_data: dict[str, Any], key: str) -> tuple[bool, str]:
    """Return (match, reason) for duplicate detection.

    Prefer ``inputs.prompt`` when the API returns it; otherwise match ``display_title`` (from
    workflow ``run-name``) so Forge duplicate detection works when GitHub omits ``inputs``.
    """
    inputs = run_data.get("inputs")
    if isinstance(inputs, dict):
        pv = inputs.get("prompt")
        if isinstance(pv, str) and pv.strip() == key:
            return True, "inputs.prompt"

    display_title = run_data.get("display_title")
    if isinstance(display_title, str) and key in display_title:
        return True, "display_title"

    return False, "no_match"


async def has_active_bmad_run_for_prompt(
    issue_key: str,
    *,
    github_repo: str | None = None,
    github_token: str | None = None,
) -> bool:
    """Return True if ``bmad-start-run.yml`` has a non-completed run for this Jira issue.

    Matches ``inputs.prompt`` when the GitHub API includes it; otherwise ``display_title`` (set via
    workflow ``run-name`` in ``bmad-start-run.yml``).

    Fail-open: missing credentials, HTTP errors, or unexpected payloads return False so dispatch
    can still be attempted (e.g. token lacks ``actions:read``).
    """
    repo = (github_repo or os.getenv("BMAD_GITHUB_REPO") or "").strip()
    token = (github_token or os.getenv("BMAD_GITHUB_TOKEN") or "").strip()
    key = issue_key.strip()
    if not repo or not token or not key:
        return False

    logger.info(
        "github_active_run_check_start",
        issue_key=key,
        repo=repo,
        workflow=BMAD_WORKFLOW_FILE,
    )

    list_url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/"
        f"{BMAD_WORKFLOW_FILE}/runs?per_page=30"
    )
    headers = _github_auth_headers(token)

    try:
        async with httpx.AsyncClient() as client:
            list_resp = await client.get(list_url, headers=headers, timeout=30.0)
            if list_resp.status_code != 200:
                logger.warning(
                    "github_active_run_list_http_error",
                    status_code=list_resp.status_code,
                    repo=repo,
                )
                return False

            try:
                payload: dict[str, Any] = list_resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.warning("github_active_run_list_json_error", error=str(exc))
                return False

            runs = payload.get("workflow_runs")
            if not isinstance(runs, list):
                logger.info(
                    "github_active_run_list_bad_shape",
                    workflow_run_field_type=type(runs).__name__,
                )
                return False

            total_count = payload.get("total_count")
            logger.info(
                "github_active_run_list_ok",
                http_status=list_resp.status_code,
                workflow_run_count=len(runs),
                total_count=total_count,
            )

            for wr in runs:
                if not isinstance(wr, dict):
                    continue
                status = wr.get("status")
                if status not in ACTIVE_RUN_STATUSES:
                    continue
                run_id = wr.get("id")
                if not isinstance(run_id, int):
                    continue
                logger.info(
                    "github_active_run_active_candidate",
                    run_id=run_id,
                    status=status,
                )
                run_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
                run_resp = await client.get(run_url, headers=headers, timeout=30.0)

                if run_resp.status_code != 200:
                    logger.warning(
                        "github_active_run_detail_http_error",
                        run_id=run_id,
                        status_code=run_resp.status_code,
                    )
                    continue

                try:
                    run_data: dict[str, Any] = run_resp.json()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "github_active_run_detail_json_error",
                        run_id=run_id,
                        error=str(exc),
                    )
                    continue

                inputs = run_data.get("inputs")
                top_level_keys = sorted(run_data.keys()) if isinstance(run_data, dict) else []
                inputs_keys: list[str] | None = (
                    sorted(inputs.keys()) if isinstance(inputs, dict) else None
                )
                prompt_val = inputs.get("prompt") if isinstance(inputs, dict) else None
                display_title = run_data.get("display_title")
                display_title_str = display_title if isinstance(display_title, str) else None
                matches, match_reason = _run_matches_issue_key(run_data, key)
                logger.info(
                    "github_active_run_detail_payload",
                    run_id=run_id,
                    run_event=run_data.get("event"),
                    run_top_level_keys=top_level_keys,
                    inputs_present="inputs" in run_data,
                    inputs_type=type(inputs).__name__,
                    inputs_keys=inputs_keys,
                    prompt_value=prompt_val if isinstance(prompt_val, str) else None,
                    display_title=display_title_str,
                    expected_issue_key=key,
                    prompt_matches=(
                        isinstance(prompt_val, str) and prompt_val.strip() == key
                    ),
                    display_title_contains_key=(
                        display_title_str is not None and key in display_title_str
                    ),
                    match=matches,
                    match_reason=match_reason,
                )

                if matches:
                    logger.info(
                        "github_active_run_conflict",
                        issue_key=key,
                        run_id=run_id,
                        status=status,
                        match_reason=match_reason,
                    )
                    return True

            logger.info(
                "github_active_run_no_conflict",
                issue_key=key,
                repo=repo,
            )
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "github_active_run_request_failed",
            error=str(exc),
            repo=repo,
        )
        return False
