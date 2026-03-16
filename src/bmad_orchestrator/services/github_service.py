from __future__ import annotations

import os
import subprocess

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
