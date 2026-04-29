from __future__ import annotations

import os

from pydantic import Field, SecretStr, field_validator, model_validator
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
    # Jira custom field IDs (vary per Cloud site). Defaults match legacy BMAD fields.
    jira_target_repo_custom_field_id: str = "customfield_10112"
    jira_branch_custom_field_id: str = "customfield_10145"
    # Checklists for Jira | Free — "Checklist Text" field (Paragraph / multi-line).
    jira_checklist_text_custom_field_id: str = "customfield_10046"
    # Reserved for future Jira ADF inline media; Mermaid diagrams are attached as PNG only.
    jira_media_collection: str = ""
    # Mermaid to PNG for Jira descriptions: off | kroki | mmdc (needs issue key + attachment).
    mermaid_renderer: str = "mmdc"
    kroki_url: str = "https://kroki.io"
    mermaid_kroki_timeout_seconds: float = 30.0
    mmdc_path: str = "mmdc"
    # mmdc -w/-H/-s (viewport + Puppeteer scale); larger = bigger PNG for Jira attachments.
    mermaid_mmdc_width: int = Field(default=1600, ge=200, le=8192)
    mermaid_mmdc_height: int = Field(default=1200, ge=200, le=8192)
    mermaid_mmdc_scale: float = Field(default=1.5, ge=0.25, le=4.0)
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
    max_pipeline_cost_usd: float = 10.0
    draft_pr: bool = False
    # Execution mode: "inline" runs dev/QA/review inside the graph via Claude Agent SDK.
    # "github-agent" creates a GitHub Issue and terminates (external agent takes over).
    # "discovery" ends after planning nodes (Forge /bmad/discovery-run; no Issue, no dev/QA/PR).
    # "epic_architect": only epic_architect after create_or_correct_epic (Forge architect-run).
    # "stories_breakdown": default 3 stories (contract + FE + BE) when UI+server; party mode;
    # ends before detect_commands.
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

    # ── Timeout ───────────────────────────────────────────────────────────
    # Maximum execution time in minutes. 0 = no timeout.
    execution_timeout_minutes: int = 30

    # ── Skip nodes ──────────────────────────────────────────────────────────
    skip_nodes: list[str] = []

    # ── Figma MCP (LOCAL DEV ONLY) ───────────────────────────────────────────
    # Connects the developer agent to the official Figma Dev Mode MCP server.
    # Requires Figma desktop running locally with Dev Mode; will not work in
    # GitHub Actions, Cloud Run, or any headless environment.
    figma_mcp_enabled: bool = False
    figma_mcp_url: str = "http://127.0.0.1:3845/sse"

    @field_validator("jira_target_repo_custom_field_id", mode="before")
    @classmethod
    def _target_repo_cf_default(cls, v: object) -> str:
        if v is None or (isinstance(v, str) and not str(v).strip()):
            return "customfield_10112"
        s = str(v).strip()
        if not s.startswith("customfield_"):
            msg = "Jira custom field id must look like customfield_12345"
            raise ValueError(msg)
        return s

    @field_validator("jira_branch_custom_field_id", mode="before")
    @classmethod
    def _branch_cf_default(cls, v: object) -> str:
        if v is None or (isinstance(v, str) and not str(v).strip()):
            return "customfield_10145"
        s = str(v).strip()
        if not s.startswith("customfield_"):
            msg = "Jira custom field id must look like customfield_12345"
            raise ValueError(msg)
        return s

    @field_validator("jira_checklist_text_custom_field_id", mode="before")
    @classmethod
    def _checklist_text_cf_default(cls, v: object) -> str:
        if v is None or (isinstance(v, str) and not str(v).strip()):
            return "customfield_10046"
        s = str(v).strip()
        if not s.startswith("customfield_"):
            msg = "Jira custom field id must look like customfield_12345"
            raise ValueError(msg)
        return s

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


# Defaults for code paths that do not load full Settings (e.g. Jira field id env helpers).
JIRA_TARGET_REPO_CUSTOM_FIELD_ID_DEFAULT = "customfield_10112"
JIRA_BRANCH_CUSTOM_FIELD_ID_DEFAULT = "customfield_10145"
JIRA_CHECKLIST_TEXT_CUSTOM_FIELD_ID_DEFAULT = "customfield_10046"


def jira_target_repo_custom_field_id_from_env() -> str:
    """Read target-repo field id from env (see Settings.jira_target_repo_custom_field_id)."""
    raw = os.environ.get("BMAD_JIRA_TARGET_REPO_CUSTOM_FIELD_ID", "").strip()
    return raw or JIRA_TARGET_REPO_CUSTOM_FIELD_ID_DEFAULT


def jira_branch_custom_field_id_from_env() -> str:
    """Read branch field id from env; same default as Settings.jira_branch_custom_field_id."""
    raw = os.environ.get("BMAD_JIRA_BRANCH_CUSTOM_FIELD_ID", "").strip()
    return raw or JIRA_BRANCH_CUSTOM_FIELD_ID_DEFAULT
