from __future__ import annotations

from pathlib import Path

import pytest

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.dummy_github_service import DummyGitHubService


@pytest.fixture
def svc(tmp_path: Path) -> DummyGitHubService:
    settings = Settings(
        anthropic_api_key="test-key",  # type: ignore[arg-type]
        dummy_jira=True,
        dummy_github=True,
        github_repo="org/test-repo",
        dummy_data_dir=str(tmp_path),
        dry_run=False,
    )
    return DummyGitHubService(settings, base_dir=tmp_path / "github" / "prs")


class TestCreatePR:
    def test_writes_markdown_and_returns_url(self, svc: DummyGitHubService) -> None:
        url = svc.create_pr(
            title="feat: add login",
            body="## Summary\nAdds login page",
            head_branch="bmad/growth/DUMMY-3-add-login",
        )
        assert "org/test-repo/pull/1" in url

        pr_file = svc._base / "DUMMY-PR-1.md"
        assert pr_file.exists()
        content = pr_file.read_text()
        assert "feat: add login" in content
        assert "Adds login page" in content

    def test_auto_increments_pr_number(self, svc: DummyGitHubService) -> None:
        url1 = svc.create_pr("PR 1", "body", "branch-1")
        url2 = svc.create_pr("PR 2", "body", "branch-2")
        assert "/pull/1" in url1
        assert "/pull/2" in url2


class TestPRExists:
    def test_returns_none_when_empty(self, svc: DummyGitHubService) -> None:
        assert svc.pr_exists("some-branch") is None

    def test_finds_matching_branch(self, svc: DummyGitHubService) -> None:
        url = svc.create_pr("title", "body", "feature/login")
        found = svc.pr_exists("feature/login")
        assert found == url

    def test_returns_none_for_different_branch(self, svc: DummyGitHubService) -> None:
        svc.create_pr("title", "body", "feature/login")
        assert svc.pr_exists("feature/signup") is None


class TestCreateIssue:
    def test_writes_markdown_and_returns_url(self, svc: DummyGitHubService) -> None:
        url, number = svc.create_issue(
            title="feat: implement login",
            body="## Acceptance Criteria\n- Users can log in",
            labels=["bmad-orchestrated"],
        )
        assert "org/test-repo/issues/1" in url
        assert number == 1

        issue_file = svc._issues_base / "DUMMY-ISSUE-1.md"
        assert issue_file.exists()
        content = issue_file.read_text()
        assert "feat: implement login" in content
        assert "Users can log in" in content

    def test_auto_increments_issue_number(self, svc: DummyGitHubService) -> None:
        url1, n1 = svc.create_issue("Issue 1", "body")
        url2, n2 = svc.create_issue("Issue 2", "body")
        assert n1 == 1
        assert n2 == 2
        assert "/issues/1" in url1
        assert "/issues/2" in url2

    def test_labels_stored_in_frontmatter(self, svc: DummyGitHubService) -> None:
        svc.create_issue("t", "b", labels=["bmad", "agent"])
        data = svc.get_issue(1)
        assert data["labels"] == ["bmad", "agent"]


class TestGetIssue:
    def test_returns_issue_data(self, svc: DummyGitHubService) -> None:
        svc.create_issue("My Issue", "The body content", labels=["bug"])
        data = svc.get_issue(1)
        assert data["title"] == "My Issue"
        assert data["body"] == "The body content"
        assert data["state"] == "open"

    def test_raises_for_missing_issue(self, svc: DummyGitHubService) -> None:
        with pytest.raises(FileNotFoundError):
            svc.get_issue(999)


class TestAddIssueComment:
    def test_appends_comment_to_file(self, svc: DummyGitHubService) -> None:
        svc.create_issue("t", "body")
        svc.add_issue_comment(1, "A comment")
        content = (svc._issues_base / "DUMMY-ISSUE-1.md").read_text()
        assert "A comment" in content

    def test_raises_for_missing_issue(self, svc: DummyGitHubService) -> None:
        with pytest.raises(FileNotFoundError):
            svc.add_issue_comment(999, "comment")


class TestCloseIssue:
    def test_updates_state_to_closed(self, svc: DummyGitHubService) -> None:
        svc.create_issue("t", "body")
        svc.close_issue(1)
        data = svc.get_issue(1)
        assert data["state"] == "closed"

    def test_raises_for_missing_issue(self, svc: DummyGitHubService) -> None:
        with pytest.raises(FileNotFoundError):
            svc.close_issue(999)
