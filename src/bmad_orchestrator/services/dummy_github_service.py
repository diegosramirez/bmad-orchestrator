from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)


class DummyGitHubService:
    """File-backed GitHub service that writes PR markdown files to disk."""

    def __init__(self, settings: Settings, base_dir: Path | None = None) -> None:
        self.settings = settings
        self._base = base_dir or Path(settings.dummy_data_dir).expanduser() / "github" / "prs"
        self._base.mkdir(parents=True, exist_ok=True)

    def _next_pr_number(self) -> int:
        counter_file = self._base / "_counter.json"
        if counter_file.exists():
            data = json.loads(counter_file.read_text())
        else:
            data = {"next_pr": 1}
        num = data["next_pr"]
        data["next_pr"] = num + 1
        counter_file.write_text(json.dumps(data))
        return num

    def _make_url(self, pr_number: int) -> str:
        repo = self.settings.github_repo or "local/dummy-repo"
        return f"https://github.com/{repo}/pull/{pr_number}"

    def pr_exists(self, branch_name: str) -> str | None:
        for md_file in self._base.glob("DUMMY-PR-*.md"):
            text = md_file.read_text()
            parts = text.split("---", 2)
            if len(parts) >= 3:
                data = yaml.safe_load(parts[1])
                if data and data.get("head_branch") == branch_name:
                    return data["url"]
        return None

    def create_pr(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str | None = None,
        draft: bool = False,
    ) -> str:
        pr_number = self._next_pr_number()
        url = self._make_url(pr_number)
        base = base_branch or self.settings.github_base_branch

        pr_data: dict[str, Any] = {
            "pr_number": pr_number,
            "url": url,
            "title": title,
            "head_branch": head_branch,
            "base_branch": base,
            "draft": draft,
            "status": "open",
            "created_at": datetime.now(UTC).isoformat(),
        }

        frontmatter = yaml.dump(pr_data, default_flow_style=False, sort_keys=False)
        path = self._base / f"DUMMY-PR-{pr_number}.md"
        path.write_text(f"---\n{frontmatter}---\n\n{body}\n")

        logger.info("dummy_pr_created", url=url, path=str(path))
        return url
