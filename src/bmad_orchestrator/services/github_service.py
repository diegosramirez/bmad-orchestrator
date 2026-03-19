from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.dry_run import skip_if_dry_run
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)


def _gh_env(settings: Settings) -> dict[str, str] | None:
    """Build env dict for ``gh`` CLI, injecting GH_TOKEN if configured."""
    token = settings.github_token
    if token is None:
        return None  # inherit parent environment as-is
    env = {**os.environ, "GH_TOKEN": token.get_secret_value()}
    return env


def _run_gh(
    args: list[str],
    settings: Settings,
) -> subprocess.CompletedProcess[str]:
    env = _gh_env(settings)
    try:
        return subprocess.run(  # noqa: S603
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        logger.error(
            "gh_cli_error",
            args=args[:3],
            returncode=exc.returncode,
            stderr=exc.stderr[:500] if exc.stderr else "",
        )
        raise


class GitHubService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def pr_exists(self, branch_name: str) -> str | None:
        """Return the PR URL if a PR already exists for the branch, else None."""
        result = subprocess.run(  # noqa: S603
            [
                "gh",
                "pr",
                "list",
                "--repo",
                self.settings.github_repo,
                "--head",
                branch_name,
                "--json",
                "url",
                "--jq",
                ".[0].url",
            ],
            capture_output=True,
            text=True,
            env=_gh_env(self.settings),
        )
        url = result.stdout.strip()
        return url if url else None

    @skip_if_dry_run(fake_return="https://github.com/dry-run/pulls/0")
    def create_pr(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str | None = None,
        draft: bool = False,
    ) -> str:
        base = base_branch or self.settings.github_base_branch
        args = [
            "pr",
            "create",
            "--repo",
            self.settings.github_repo,
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
            "--head",
            head_branch,
        ]
        if draft:
            args.append("--draft")

        result = _run_gh(args, self.settings)
        url = result.stdout.strip()
        logger.info("pr_created", url=url)
        return url

    def _ensure_labels_exist(self, repo: str, labels: list[str]) -> list[str]:
        """Create labels that don't exist on the repo. Return labels that are usable."""
        usable: list[str] = []
        for label in labels:
            try:
                _run_gh(
                    ["label", "create", label, "--repo", repo, "--force"],
                    self.settings,
                )
                usable.append(label)
            except subprocess.CalledProcessError:
                logger.warning("label_create_failed", label=label)
        return usable

    @skip_if_dry_run(fake_return=("https://github.com/dry-run/issues/0", 0))
    def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> tuple[str, int]:
        """Create a GitHub issue and return (url, number)."""
        repo = self.settings.github_repo or ""
        args = [
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            title,
            "--body",
            body,
        ]
        if labels:
            usable = self._ensure_labels_exist(repo, labels)
            for label in usable:
                args.extend(["--label", label])

        result = _run_gh(args, self.settings)
        url = result.stdout.strip()
        # gh issue create prints the URL; extract the issue number from it
        issue_number = int(url.rstrip("/").rsplit("/", 1)[-1])
        logger.info("issue_created", url=url, issue_number=issue_number)
        return url, issue_number

    def get_issue(self, issue_number: int) -> dict[str, Any]:
        """Return issue metadata as a dict."""
        repo = self.settings.github_repo or ""
        result = _run_gh(
            [
                "issue",
                "view",
                str(issue_number),
                "--repo",
                repo,
                "--json",
                "number,title,state,body,url,labels",
            ],
            self.settings,
        )
        data: dict[str, Any] = json.loads(result.stdout)
        return data

    @skip_if_dry_run(fake_return=None)
    def add_issue_comment(self, issue_number: int, body: str) -> None:
        """Add a comment to a GitHub issue."""
        repo = self.settings.github_repo or ""
        _run_gh(
            [
                "issue",
                "comment",
                str(issue_number),
                "--repo",
                repo,
                "--body",
                body,
            ],
            self.settings,
        )

    @skip_if_dry_run(fake_return=None)
    def dispatch_workflow(
        self,
        workflow: str,
        inputs: dict[str, str],
        repo: str | None = None,
    ) -> None:
        """Dispatch a GitHub Actions workflow via ``gh workflow run``."""
        target = repo or os.environ.get("GITHUB_REPOSITORY", "")
        if not target:
            logger.warning("dispatch_workflow_skipped", reason="no repo")
            return
        args = ["workflow", "run", workflow, "--repo", target]
        for key, val in inputs.items():
            args.extend(["-f", f"{key}={val}"])
        _run_gh(args, self.settings)
        logger.info("workflow_dispatched", workflow=workflow, repo=target)

    @skip_if_dry_run(fake_return=None)
    def close_issue(self, issue_number: int) -> None:
        """Close a GitHub issue."""
        repo = self.settings.github_repo or ""
        _run_gh(
            [
                "issue",
                "close",
                str(issue_number),
                "--repo",
                repo,
            ],
            self.settings,
        )
