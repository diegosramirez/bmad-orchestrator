from __future__ import annotations

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default per-agent model overrides: Opus for requirement analysis, Haiku for
# simple classification/detection tasks.  Users can override any of these via
# the BMAD_AGENT_MODELS env var (JSON dict).
_DEFAULT_AGENT_MODELS: dict[str, str] = {
    # All agents use Opus for testing — revert to tiered models after evaluation
    "pm": "claude-sonnet-4-20250514",
    "designer": "claude-sonnet-4-20250514",
    "architect_party": "claude-sonnet-4-20250514",
    "developer_party": "claude-sonnet-4-20250514",
    "scrum_master": "claude-sonnet-4-20250514",
    "build-expert": "claude-sonnet-4-20250514",
    "e2e_tester": "claude-sonnet-4-20250514",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BMAD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Anthropic ──────────────────────────────────────────────────────────────
    anthropic_api_key: SecretStr
    model_name: str = "claude-sonnet-4-20250514"
    temperature: float = 0.0
    # Per-agent model overrides. JSON dict mapping agent_id → model name.
    # E.g. BMAD_AGENT_MODELS='{"developer":"claude-opus-4","qa":"claude-haiku-4-5-20251001"}'
    agent_models: dict[str, str] = {}

    # ── Jira (optional when dummy_jira=True) ──────────────────────────────────
    jira_base_url: str | None = None
    jira_username: str | None = None
    jira_api_token: SecretStr | None = None
    jira_project_key: str = "DUMMY"
    # ADF media.attrs.collection for inline images from attachments (often "" on Jira Cloud).
    jira_media_collection: str = ""
    # Mermaid to PNG for Jira descriptions: off | kroki | mmdc (needs issue key + attachment).
    mermaid_renderer: str = "kroki"
    kroki_url: str = "https://kroki.io"
    mermaid_kroki_timeout_seconds: float = 30.0
    mmdc_path: str = "mmdc"
    mermaid_mmdc_timeout_seconds: float = 60.0
    mermaid_max_source_chars: int = 500_000

    # ── GitHub (optional when dummy_github=True) ──────────────────────────────
    github_repo: str | None = None
    github_base_branch: str = "main"
    github_token: SecretStr | None = None

    # ── Git identity ───────────────────────────────────────────────────────────
    git_author_name: str = "BMAD Orchestrator"
    git_author_email: str = "bmad@noreply.local"

    # ── Orchestrator ───────────────────────────────────────────────────────────
    verbose: bool = False
    dry_run: bool = False
    jira_only: bool = False
    checkpoint_db_path: str = "~/.bmad/checkpoints.db"
    bmad_install_dir: str = ".claude"
    # Root directory for _bmad framework (workflows, tasks). Relative to CWD or absolute.
    bmad_root: str = "_bmad"
    max_review_loops: int = 2
    max_e2e_loops: int = 1
    draft_pr: bool = False
    # Execution mode: "inline" runs dev/QA/review inside the graph via Claude Agent SDK.
    # "github-agent" creates a GitHub Issue and terminates (external agent takes over).
    # "discovery" ends after planning nodes (Forge /bmad/discovery-run; no Issue, no dev/QA/PR).
    # "epic_architect": only epic_architect after create_or_correct_epic (Forge architect-run).
    # "stories_breakdown": N stories + party from epic description; ends before detect_commands.
    execution_mode: str = "inline"
    # When True in github-agent mode, the create_github_issue node adds a
    # "bmad-execute" label that triggers immediate code generation via the
    # bmad-issue-executor workflow.  When False (default), only the
    # "bmad-orchestrated" label is added and a human must add "bmad-execute".
    auto_execute_issue: bool = False
    # Which agent generates code from GitHub Issues: "inline" (BMAD pipeline)
    # or "copilot" (GitHub Copilot Coding Agent).  Empty string = use repo default.
    code_agent: str = ""

    # ── Dummy/Local mode ──────────────────────────────────────────────────────
    dummy_jira: bool = False
    dummy_github: bool = False
    dummy_data_dir: str = "~/.bmad/dummy"
    # Empty string = write files directly to repo root (global install mode).
    # Set to a path (e.g. "_bmad-output/implementation-artifacts") to use a
    # dedicated output directory instead.
    artifacts_dir: str = ""

    # ── Slack (optional) ──────────────────────────────────────────────────────
    slack_notify: bool = False
    slack_bot_token: SecretStr | None = None
    slack_channel: str | None = None
    slack_verbose: bool = False
    slack_thread_ts: str | None = None

    # ── Skip nodes ──────────────────────────────────────────────────────────
    skip_nodes: list[str] = []

    @model_validator(mode="after")
    def _apply_default_agent_models(self) -> Settings:
        """Merge user-provided agent_models on top of built-in defaults."""
        merged = {**_DEFAULT_AGENT_MODELS, **self.agent_models}
        self.agent_models = merged
        return self

    @model_validator(mode="after")
    def _validate_service_credentials(self) -> Settings:
        if not self.dummy_jira:
            missing = [
                name
                for name in ("jira_base_url", "jira_username", "jira_api_token")
                if getattr(self, name) is None
            ]
            if missing:
                msg = f"Real Jira mode requires: {', '.join(missing)}"
                raise ValueError(msg)
        if not self.dummy_github and not self.github_repo:
            msg = "Real GitHub mode requires: github_repo"
            raise ValueError(msg)
        if self.dummy_github and not self.github_repo:
            self.github_repo = "local/dummy-repo"
        if self.slack_notify:
            missing = [
                name
                for name in ("slack_bot_token", "slack_channel")
                if not getattr(self, name)
            ]
            if missing:
                msg = f"Slack notifications require: {', '.join(missing)}"
                raise ValueError(msg)
        return self
