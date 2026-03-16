from __future__ import annotations

from bmad_orchestrator.utils.dry_run import skip_if_dry_run


class _FakeService:
    def __init__(self, dry_run: bool) -> None:
        from bmad_orchestrator.config import Settings
        self.settings = Settings(
            anthropic_api_key="k",  # type: ignore[arg-type]
            jira_base_url="https://x.atlassian.net",
            jira_username="u",
            jira_api_token="t",  # type: ignore[arg-type]
            jira_project_key="P",
            github_repo="o/r",
            dry_run=dry_run,
        )
        self.called = False

    @skip_if_dry_run(fake_return="fake")
    def do_something(self, x: int) -> str:
        self.called = True
        return f"real-{x}"


def test_skip_if_dry_run_returns_fake_when_dry():
    svc = _FakeService(dry_run=True)
    result = svc.do_something(42)
    assert result == "fake"
    assert svc.called is False


def test_skip_if_dry_run_executes_when_not_dry():
    svc = _FakeService(dry_run=False)
    result = svc.do_something(7)
    assert result == "real-7"
    assert svc.called is True
