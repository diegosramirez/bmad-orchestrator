from __future__ import annotations

import os
import re
import subprocess

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.github_token_provider import GitHubAppTokenProvider
from bmad_orchestrator.utils.dry_run import skip_if_dry_run
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)


def _slugify(text: str, max_len: int = 40) -> str:
    """Convert text to a safe branch-name slug."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len].rstrip("-")


def _run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        args,
        check=True,
        capture_output=True,
        text=True,
        **kwargs,  # type: ignore[arg-type]
    )


def _git_env_with_token(
    token_provider: GitHubAppTokenProvider | None,
) -> dict[str, str] | None:
    """Build env dict injecting GH_TOKEN for HTTPS git operations.

    Returns None when no provider is configured (e.g. dummy/dry-run modes), so
    callers fall through to the parent process environment.
    """
    if token_provider is None:
        return None
    return {**os.environ, "GH_TOKEN": token_provider.get_installation_token()}


def classify_push_error(exc: subprocess.CalledProcessError) -> str:
    """Return a human-readable category for a git push failure.

    Categories: ``'auth'``, ``'rejected'``, ``'network'``, ``'unknown'``.
    """
    stderr = (exc.stderr or "").lower()
    if any(kw in stderr for kw in (
        "authentication", "403", "401", "permission denied",
    )):
        return "auth"
    if any(kw in stderr for kw in (
        "rejected", "non-fast-forward", "stale info",
    )):
        return "rejected"
    if any(kw in stderr for kw in (
        "could not resolve host", "connection refused",
        "timed out", "network", "ssl",
    )):
        return "network"
    return "unknown"


class GitService:
    def __init__(
        self,
        settings: Settings,
        token_provider: GitHubAppTokenProvider | None = None,
    ) -> None:
        self.settings = settings
        self._token_provider = token_provider

    def make_branch_name(self, team_id: str, story_id: str, story_summary: str) -> str:
        team_slug = _slugify(team_id, max_len=20)
        slug = _slugify(story_summary)
        return f"bmad/{team_slug}/{story_id}-{slug}"

    def get_current_branch(self) -> str:
        result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def branch_exists_remote(self, branch_name: str) -> bool:
        env = _git_env_with_token(self._token_provider)
        kwargs: dict[str, object] = {"capture_output": True, "text": True}
        if env is not None:
            kwargs["env"] = env
        result = subprocess.run(  # noqa: S603
            ["git", "ls-remote", "--heads", "origin", branch_name],
            **kwargs,  # type: ignore[arg-type]
        )
        return bool(result.stdout.strip())

    def branch_exists_local(self, branch_name: str) -> bool:
        result = subprocess.run(  # noqa: S603
            ["git", "branch", "--list", branch_name],
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    @skip_if_dry_run(fake_return=None)
    def create_and_checkout_branch(self, branch_name: str) -> None:
        if self.branch_exists_remote(branch_name):
            logger.info("branch_exists_remote_checkout", branch=branch_name)
            env = _git_env_with_token(self._token_provider)
            kwargs: dict[str, object] = {}
            if env is not None:
                kwargs["env"] = env
            _run(["git", "fetch", "origin", branch_name], **kwargs)
            _run(["git", "checkout", branch_name])
        else:
            try:
                _run(["git", "checkout", "-b", branch_name])
            except subprocess.CalledProcessError as exc:
                if "already exists" in (exc.stderr or "").lower():
                    # Branch exists locally (e.g. retry after push failure) — just check it out.
                    logger.info("branch_exists_local_checkout", branch=branch_name)
                    _run(["git", "checkout", branch_name])
                else:
                    raise
        logger.info("branch_checked_out", branch=branch_name)

    @skip_if_dry_run(fake_return=None)
    def stage_path(self, path: str) -> None:
        """Stage only the files under the given path (never the whole tree)."""
        _run(["git", "add", "--", path])
        logger.info("staged_path", path=path)

    def has_staged_changes(self) -> bool:
        """Return True if there are staged changes ready to commit.

        Uses ``git diff --cached --quiet`` which exits 1 when staged changes
        exist and 0 when the index is clean — no output parsing needed.
        """
        result = subprocess.run(  # noqa: S603
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
        )
        return result.returncode != 0

    def get_head_sha(self) -> str:
        result = _run(["git", "rev-parse", "HEAD"])
        return result.stdout.strip()

    def rev_parse(self, ref: str) -> str:
        """Resolve a ref (branch name, tag, etc.) to its SHA."""
        result = _run(["git", "rev-parse", ref])
        return result.stdout.strip()

    @skip_if_dry_run(fake_return="dry-run-sha")
    def commit(
        self,
        message: str,
        author_name: str | None = None,
        author_email: str | None = None,
        *,
        allow_empty: bool = False,
    ) -> str:
        name = author_name or self.settings.git_author_name
        email = author_email or self.settings.git_author_email
        env_override = {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        }
        env = {**os.environ, **env_override}
        cmd = ["git", "commit", "-m", message]
        if allow_empty:
            cmd.append("--allow-empty")
        _run(cmd, env=env)
        result = _run(["git", "rev-parse", "HEAD"])
        sha = result.stdout.strip()
        logger.info("committed", sha=sha[:12])
        return sha

    @skip_if_dry_run(fake_return=None)
    def push(self, branch_name: str, remote: str = "origin") -> None:
        # Use explicit refspec HEAD:refs/heads/<branch> to avoid "cannot be resolved
        # to branch" errors that occur when git can't resolve a hierarchical branch
        # name (e.g. bmad/test/DUMMY-2-...) from the local ref store.
        env = _git_env_with_token(self._token_provider)
        kwargs: dict[str, object] = {}
        if env is not None:
            kwargs["env"] = env
        _run(
            ["git", "push", "-u", remote, f"HEAD:refs/heads/{branch_name}"],
            **kwargs,
        )
        logger.info("pushed", remote=remote, branch=branch_name)

    # ── Read-only query methods (no @skip_if_dry_run needed) ───────

    def is_detached_head(self) -> bool:
        """Return True if HEAD is detached (not on any branch)."""
        result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip() == "HEAD"

    def has_uncommitted_changes(self) -> bool:
        """Return True if the working tree has uncommitted changes."""
        result = subprocess.run(  # noqa: S603
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def can_merge_cleanly(
        self, head_branch: str, base_branch: str,
    ) -> bool:
        """Check if *head_branch* can merge into *base_branch* cleanly.

        Uses ``git merge-tree --write-tree`` (Git 2.38+) for a
        non-destructive check.  Falls back to ``True`` on old Git so
        we never block PR creation due to an unsupported command.
        """
        try:
            result = subprocess.run(  # noqa: S603
                [
                    "git", "merge-tree", "--write-tree",
                    "--no-messages",
                    base_branch, head_branch,
                ],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:  # noqa: BLE001
            return True
