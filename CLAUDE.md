# BMAD Autonomous Engineering Orchestrator

## Project Overview

LangGraph-powered CLI that automates the full BMAD engineering workflow: from Jira epic/story creation through code generation, QA, code review, and PR creation — all driven by Claude AI with role-based personas.

**Entry point:** `bmad-orchestrator = "bmad_orchestrator.cli:app"` (Typer CLI)

## Quick Reference

```bash
# Install dependencies
uv sync --dev

# Run unit tests (must maintain ≥90% coverage)
uv run pytest tests/unit/ -v

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/bmad_orchestrator/

# Run the orchestrator
uv run bmad-orchestrator run --team-id <TEAM> --prompt "<PROMPT>" --dummy-jira --dummy-github
```

## Architecture

### Execution Graph

```
START → check_epic_state → create_or_correct_epic → create_story_tasks
→ party_mode_refinement → dev_story → qa_automation → code_review
→ (conditional) → commit_and_push → create_pull_request → END
                ↘ dev_story_fix_loop → code_review (max 2 loops)
                ↘ fail_with_state → END
```

### Directory Layout

```
src/bmad_orchestrator/
├── cli.py                  # Typer CLI entry point
├── config.py               # Pydantic Settings (BMAD_* env vars)
├── graph.py                # LangGraph StateGraph assembly + composition root
├── state.py                # OrchestratorState TypedDict + sub-TypedDicts
├── nodes/                  # One file per graph node (10 nodes)
│   ├── check_epic_state.py
│   ├── create_or_correct_epic.py
│   ├── create_story_tasks.py
│   ├── party_mode_refinement.py
│   ├── dev_story.py
│   ├── qa_automation.py
│   ├── code_review.py
│   ├── dev_story_fix_loop.py
│   ├── commit_and_push.py
│   └── create_pull_request.py
├── services/               # External service wrappers
│   ├── protocols.py        # Protocol interfaces (JiraServiceProtocol, GitHubServiceProtocol)
│   ├── service_factory.py  # Composition root — returns real or dummy implementations
│   ├── claude_agent_service.py  # Claude Agent SDK wrapper (agentic code gen sessions)
│   ├── claude_service.py   # Anthropic API wrapper (complete, complete_structured, classify)
│   ├── jira_service.py     # Real Jira REST API
│   ├── dummy_jira_service.py    # File-backed Jira mock (markdown + YAML frontmatter)
│   ├── git_service.py      # Git CLI wrapper
│   ├── github_service.py   # GitHub CLI (gh) wrapper
│   └── dummy_github_service.py  # File-backed GitHub mock
├── personas/
│   └── loader.py           # Loads YAML personas from .claude/skills/ or falls back to hardcoded
└── utils/
    ├── cli_prompts.py      # Interactive Rich prompts (CLI only, never in nodes)
    ├── dry_run.py          # @skip_if_dry_run decorator
    ├── json_repair.py      # Repairs malformed JSON from Claude tool_use responses
    └── logger.py           # structlog configuration
```

### Test Layout (mirrors src/)

```
tests/
├── conftest.py             # Shared fixtures: settings, base_state, mock_*, make_state()
├── unit/
│   ├── nodes/              # One test file per node
│   ├── services/           # One test file per service
│   └── utils/              # Utility tests
└── integration/
    └── test_graph_integration.py
```

## Code Conventions

### Node Factory Pattern (MUST follow for all nodes)

```python
def make_<node_name>_node(
    service: ServiceType,
    settings: Settings,
) -> Callable[[OrchestratorState], dict[str, Any]]:
    system_prompt = build_system_prompt("persona_id", settings.bmad_install_dir)

    def <node_name>(state: OrchestratorState) -> dict[str, Any]:
        # Read from state → call services → return state update dict
        return {"field": value, "execution_log": [log_entry]}

    return <node_name>
```

### State Management

- `OrchestratorState` is a `TypedDict`, not a Pydantic model
- Nodes return partial dicts — LangGraph merges them
- `qa_results`, `execution_log`, and `touched_files` use `Annotated[list[...], operator.add]` (accumulate across nodes)
- `code_review_issues` is a plain `list` (replaced each review pass, not accumulated)
- All other fields are simple replacement on update

### Claude Structured Output

Claude returns structured data via `tool_use` with forced tool choice. The response is validated against a Pydantic model schema. Three methods on `ClaudeService`:
- `complete()` → raw text
- `complete_structured(schema=PydanticModel)` → validated Pydantic instance
- `classify(options=[...])` → pick one option

### JSON Repair Pattern

Claude sometimes returns list fields as stringified JSON or includes invalid escape sequences in generated code content. All Pydantic models with list fields that receive Claude output must have:

```python
@field_validator("list_field", mode="before")
@classmethod
def _parse_stringified_json(cls, v: Any) -> Any:
    return parse_stringified_list(v)
```

This is used in: `FileOperationList`, `StoryDraft`, `ReviewResult`, `RefinedStory`.

### Claude Agent SDK Integration

`ClaudeAgentService` wraps the Claude Agent SDK for agentic code generation sessions.
Key configuration defaults in `claude_agent_service.py`:
- `effort="low"` — minimises thinking overhead for tool-heavy sessions
- `max_budget_usd=2.0` — per-session cost ceiling to prevent runaway sessions
- `disallowed_tools` — blocks Task, Agent, TodoWrite, WebSearch, WebFetch
- `allowed_tools` — Read, Write, Edit, Bash, Glob, Grep
- `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000` — prevents default 32k limit from causing retry stalls

Per-agent model defaults are configured in `config.py` via `_DEFAULT_AGENT_MODELS` dict.
Users can override via `BMAD_AGENT_MODELS` env var (JSON dict mapping agent_id → model name).

### Service Pattern

- Services take `Settings` in `__init__`
- Side-effect methods use `@skip_if_dry_run(fake_return=...)` decorator
- `Protocol` classes define interfaces; `service_factory.py` returns real or dummy implementation
- Dummy services are file-backed (markdown + YAML frontmatter). Default location: `~/.bmad/dummy/` (configurable via `BMAD_DUMMY_DATA_DIR`). This directory is gitignored — data is ephemeral per run.

### GitHub Authentication (App-based, no PAT)

GitHub auth uses a GitHub App via `services/github_token_provider.py::GitHubAppTokenProvider`. Required env: `BMAD_GITHUB_APP_ID`, `BMAD_GITHUB_APP_INSTALLATION_ID`, plus either `BMAD_GITHUB_APP_PRIVATE_KEY` (inline PEM) or `BMAD_GITHUB_APP_PRIVATE_KEY_PATH` (file). Required App permissions: `Contents R/W`, `Issues R/W`, `Pull requests R/W`, `Actions R/W`, `Metadata R`.

Auth chokepoints (where tokens enter subprocess env / HTTP calls):
- `services/github_service.py::_gh_env(token_provider)` — `gh` CLI calls
- `services/git_service.py::_git_env_with_token(token_provider)` — git push/fetch
- `webhook-worker/src/lib/github-auth.ts::getGitHubAuth()` — Node webhook-worker fetch calls
- `.github/workflows/*.yml` — use `actions/create-github-app-token@v1`, repo secrets `BMAD_APP_ID` + `BMAD_APP_PRIVATE_KEY`

The provider is built once in `graph.py` and shared between `GitService` + `GitHubService` so they hit the same in-memory token cache. Validation lives in `services/service_factory.py::create_github_token_provider` (hard-fails on partial App config).

### Figma MCP Integration (remote)

The orchestrator can drive UI implementation from Figma designs via Figma's **remote** Dev Mode MCP server (`https://mcp.figma.com/mcp`, HTTP transport, OAuth Bearer token). Required env: `BMAD_FIGMA_MCP_ENABLED=true` + `BMAD_FIGMA_MCP_TOKEN`. The integration auto-extracts Figma URLs from prompts via `utils/figma_url.py`, fires the `ux_design_handoff` node before `dev_story` (graph.py), and injects `mcp__figma__*` tool access. Setup guide at [docs/figma-mcp-setup.md](docs/figma-mcp-setup.md). Validation lives in `services/service_factory.py::build_figma_mcp_config` (hard-fails when enabled without a token).

### General Python Style

- Every file starts with `from __future__ import annotations`
- Use `str | None` union syntax (not `Optional[str]`)
- All `__init__.py` files are empty — no package-level exports
- Ruff rules: E, W, F, I (isort), UP, B, C4, PIE. B008 ignored (Typer defaults).
- Line length: 100 characters
- Strict mypy enabled

## Testing Requirements

- **Coverage threshold: 90%** (enforced by pytest-cov, fail-under in pyproject.toml)
- Currently at ~91% with 288 tests
- `cli.py` is excluded from coverage
- Node tests: construct node via `make_*_node(mock_services, settings)`, call with `make_state(...)`, assert returned dict
- Use `monkeypatch.chdir(tmp_path)` for any file-system operations
- Shared fixtures in `tests/conftest.py`: `settings`, `base_state`, `dummy_settings`, `mock_jira`, `mock_claude`, `mock_git`, `mock_github`, `make_state(**overrides)`

## Key Files

| File | Purpose |
|------|---------|
| `BMAD_LangGraph_Orchestration_Spec.md` | Original system requirements spec |
| `docs/pipeline-steps.md` | Comprehensive pipeline reference (845 lines) |
| `docs/installation.md` | Dev-mode installation and usage guide |
| `docs/template-jira.md` | Story ticket structure (fine-grained sections for implementation) |
| `docs/template-jira-epic.md` | Epic charter: terse what/why/solution abstract/out of scope |
| `.env.example` | All `BMAD_*` environment variables |
| `project.json` | Nx monorepo project config (targets: install, test, lint, run) |
| `.claude/skills/` | 43 BMAD skill directories loaded at runtime (SKILL.md + bmad-skill-manifest.yaml) |
| `_bmad/` | BMAD framework core (workflows, agents, templates) |

## Idempotency Rules

Nodes must be safe to re-run:
- Check state before creating Jira artifacts (skip if `current_story_id` already set)
- Check state before committing (skip if `commit_sha` already set)
- Check GitHub before creating PR (skip if PR already exists for branch)
- Never silently duplicate epics, stories, or PRs

## Environment

- **Python:** 3.11 (pinned in `.python-version`)
- **Package manager:** `uv` (not pip)
- **Build backend:** Hatchling
- **Monorepo:** Nx (`apps/ai-workflow/` within `ds24-growth`)
- **All env vars** prefixed with `BMAD_` — see `.env.example`
- **`BMAD_ARTIFACTS_DIR`**: Where generated code files are written. Default `""` = current working directory (target project root).
- **Secrets** via environment variables or `.env` file (never committed)
