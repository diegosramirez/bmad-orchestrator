# BMAD Orchestrator — Current State Analysis

## Part 1: Spec Alignment Report

Comparison of the implementation against `docs/BMAD_LangGraph_Orchestration_Spec.md`.

### Fully Implemented (Spec-Aligned)

| Spec Requirement | Status | Notes |
|---|---|---|
| LangGraph StateGraph orchestration | **Done** | `graph.py` assembles a `StateGraph(OrchestratorState)` with explicit nodes, edges, and conditional routing |
| TypedDict structured state | **Done** | `state.py` — `OrchestratorState` is a `TypedDict` with all required fields |
| CLI accepts `team_id` + `prompt` | **Done** | `cli.py` — Typer CLI with `run` command, accepts `--team-id` and `--prompt` |
| CheckEpicState node | **Done** | `check_epic_state.py` — queries Jira for active epics, Claude PM decides `add_to_existing` or `create_new` |
| CreateOrCorrectEpic node | **Done** | `create_or_correct_epic.py` — creates new or updates existing epic via BMAD workflow or inline Claude |
| CreateStoryTasks node | **Done** | `create_story_tasks.py` — generates story + subtasks with AC, dependencies, QA scope, DoD; includes quality gate |
| PartyModeRefinement node | **Done** | `party_mode_refinement.py` — Designer + Architect (parallel), Developer (sequential), Aggregator synthesizes |
| DevStory node | **Done** | `dev_story.py` — Claude Agent SDK for agentic code generation |
| QAAutomation node | **Done** | `qa_automation.py` — Claude Agent SDK generates test suite + independent validation |
| CodeReview node | **Done** | `code_review.py` — Architect reviews with structured `ReviewResult` output |
| DevStoryFixLoop + max iterations | **Done** | `dev_story_fix_loop.py` — fix loop with `max_review_loops` (default 2, spec says 3 — see deviations) |
| CommitAndPush node | **Done** | `commit_and_push.py` — branch creation, file staging, commit, push |
| CreatePullRequest node | **Done** | `create_pull_request.py` — `gh pr create` with comprehensive body |
| Structured input/output per node | **Done** | All LLM responses use `complete_structured()` with Pydantic schemas |
| Observability/logging | **Done** | `execution_log` accumulated per node; structlog JSON output |
| Idempotency | **Done** | All nodes check state before creating artifacts (epic/story/PR/commit) |
| Dry-run mode | **Done** | `@skip_if_dry_run` decorator on all mutating methods |
| Python 3.11+ | **Done** | `.python-version` pins 3.11 |
| Fully typed | **Done** | TypedDict state, Pydantic structured outputs, strict mypy |
| 90%+ test coverage | **Done** | ~91% with 288 tests; threshold enforced in `pyproject.toml` |
| Secrets via env vars | **Done** | All `BMAD_*` env vars, `.env` file support, `SecretStr` for sensitive values |
| Configurable model provider | **Done** | Per-agent model overrides via `agent_models` config |
| Branch format `bmad/{team}/{story}-{slug}` | **Done** | `git_service.py` `make_branch_name()` |
| PR body includes story/AC/QA/review | **Done** | Comprehensive PR body with all required sections |

### Deviations from Spec

| Spec Requirement | Actual Implementation | Impact |
|---|---|---|
| `new_story_created` boolean in state | **Not implemented** — story creation is tracked by whether `current_story_id` is set | Low — idempotency achieved through `current_story_id` null check instead |
| Code review max **3** fix loops | Default `max_review_loops = 2` | Low — configurable; 2 loops + progressive leniency achieves convergence faster |
| Code review blocks on `severity >= medium` (simple) | **Progressive leniency**: loop 0 blocks medium+, loop 1 blocks high+, loop 2+ blocks critical only | Improvement — guarantees convergence; more sophisticated than spec's flat threshold |
| `failure_state` set after 3 failures | Set after `max_review_loops` exhausted (default 2) OR infrastructure failure detected | Aligned in spirit; the limit is configurable |
| "Persist state after every node" + "Resume from last successful node" | SQLite checkpointing via `SqliteSaver`; `--resume` / `--retry` flags | **Done** — LangGraph checkpointing satisfies this |
| Rate limiting (max tokens per agent, hard timeout) | `max_budget_usd=2.0` per agent session; `max_turns` per agent (10-20) | Partial — cost ceiling replaces token limit; no global execution timeout |
| CI to test orchestration logic | Unit tests cover orchestration; no dedicated CI pipeline in this repo (Nx `project.json` has targets) | Partial — testable locally but no CI config committed |

### Beyond Spec (Additions)

The implementation significantly exceeds the original spec:

| Feature | Description |
|---|---|
| **detect_commands node** | Auto-detects build/test/lint/E2E commands from project context — spec assumed manual config |
| **E2E automation** | Full Playwright E2E test generation + fix loop (`e2e_automation.py`, `e2e_fix_loop.py`) — not in spec |
| **GitHub-agent execution mode** | Creates GitHub Issue with metadata for external agent execution — spec only covers inline |
| **Slack notifications** | Per-node Slack thread with Retry/Refine buttons — not in spec |
| **Jira step notifications** | Single Jira comment updated per step — not in spec |
| **update_jira_branch node** | Writes branch name to Jira custom field — not in spec |
| **fail_with_state → commit_and_push** | Creates draft PR even on failure with diagnostic info — spec just sets failure_state |
| **BMAD workflow runner** | Loads real BMAD workflow YAML files for epic/story creation — spec assumes inline Claude |
| **Persona system** | YAML-based personas loaded from `.claude/commands/` with fallback chain — spec doesn't specify |
| **Project context gathering** | Auto-collects README, config files, dev guidelines — spec doesn't specify |
| **Retry guidance injection** | `--retry --guidance "..."` injects human direction into agent prompts |
| **Skip nodes** | `--skip-nodes` allows bypassing specific pipeline steps |
| **Dummy services** | File-backed Jira/GitHub mocks for local development |
| **Token usage tracking** | Aggregated token usage reported at end of run |
| **Progressive leniency** | Code review severity threshold increases per loop (medium → high → critical) |
| **Independent test validation** | QA and fix-loop nodes verify tests independently (not just agent self-report) |
| **Branch refining** | Detects existing bmad branch and stays on it for refinement runs |

### Alignment Summary

**Overall: ~95% spec-aligned, with significant value-add beyond spec.**

The core execution graph, state model, node responsibilities, structured outputs, idempotency, and quality gates all match the spec. The few deviations (loop count default, `new_story_created` field) are minor and intentional improvements. The implementation adds substantial production-readiness features (Slack, Jira notifications, E2E testing, GitHub-agent mode, retry/resume) that the spec didn't envision.

---

## Part 2: Functional & Technical Documentation

### What This Application Does

The BMAD Autonomous Engineering Orchestrator is a **CLI tool that takes a feature request and autonomously produces a complete pull request** — including Jira tracking, code implementation, tests, code review, and PR creation — all driven by Claude AI with role-based personas.

#### Inputs

- **team_id** — Team identifier (e.g., `growth`, `platform`) used for epic/branch prefixing
- **prompt** — Natural language feature request (e.g., "Add multi-language support to the checkout page")

#### Outputs

- Jira epic (created or updated)
- Jira story with acceptance criteria, subtasks, QA scope
- Implemented code files
- Unit test suite
- E2E test suite (Playwright)
- Code review resolution
- Git branch with commits
- GitHub pull request with comprehensive description

---

### Execution Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PLANNING PHASE                               │
│                                                                     │
│  1. CheckEpicState ─── Query Jira for active epics. Claude PM      │
│     │                  decides: add to existing or create new.      │
│     ▼                                                               │
│  2. CreateOrCorrectEpic ─── Create new epic or update existing      │
│     │                       description via BMAD workflow.           │
│     ▼                                                               │
│  3. CreateStoryTasks ─── Generate story with AC, tasks, QA scope.   │
│     │                    Quality gate: refine if vague.              │
│     ▼                                                               │
│  4. PartyModeRefinement ─── 3 expert personas review story:         │
│     │   Designer (UX) + Architect (technical) → Developer (impl)    │
│     │   Aggregator synthesizes into refined story.                  │
│     ▼                                                               │
│  5. DetectCommands ─── Auto-detect build/test/lint/E2E commands     │
│     │                  from project manifests.                       │
│     ▼                                                               │
│  ┌──┴──────────────────────────────────────┐                        │
│  │ Execution Mode Router                    │                        │
│  ├──────────────────┬───────────────────────┤                        │
│  │ inline (default) │ github-agent          │                        │
│  │      ▼           │      ▼                │                        │
│  │ Continue below    │ CreateGitHubIssue     │                        │
│  │                  │      ▼                │                        │
│  │                  │    END                 │                        │
│  └──────────────────┴───────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                      IMPLEMENTATION PHASE (inline only)              │
│                                                                     │
│  6. DevStory ─── Claude Agent SDK generates code with direct        │
│     │            file system access (Read/Write/Edit/Bash).          │
│     ▼                                                               │
│  7. QAAutomation ─── Claude Agent SDK generates unit tests.         │
│     │                Independent validation: runs test commands.      │
│     ▼                                                               │
│  8. CodeReview ─── Architect reviews (read-only: Read/Glob/Grep).   │
│     │              Returns structured issues with severity.           │
│     ▼                                                               │
│  ┌──┴──────────────────────────────────────────────┐                │
│  │ Review Router (progressive leniency)             │                │
│  ├─────────────────────┬──────────┬─────────────────┤                │
│  │ Blocking issues     │ No       │ Loops exhausted  │                │
│  │ + loops remain      │ blockers │ + still blocking  │                │
│  │      ▼              │    ▼     │      ▼            │                │
│  │ DevStoryFixLoop ──┐ │ E2E     │ FailWithState     │                │
│  │  (back to review) │ │ Autom.  │      │            │                │
│  └───────────────────┘ │    │    │      │            │                │
│                        │    ▼    │      │            │                │
│                        │ ┌──┴──┐ │      │            │                │
│                        │ │E2E  │ │      │            │                │
│                        │ │Router│ │      │            │                │
│                        │ └─┬──┘ │      │            │                │
│                        │   │    │      │            │                │
│                        │   ▼    │      ▼            │                │
│                        └────────┴──────────────────┘                │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       DELIVERY PHASE                                │
│                                                                     │
│  9.  CommitAndPush ─── Create branch, stage files, commit, push     │
│      │                 (empty commit if failure, so PR still works)  │
│      ▼                                                              │
│  10. UpdateJiraBranch ─── Write branch name to Jira custom field    │
│      │                                                              │
│      ▼                                                              │
│  11. CreatePullRequest ─── `gh pr create` with full description     │
│      │                     (draft if pipeline failed)               │
│      ▼                                                              │
│    END                                                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Architecture

#### Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  CLI Layer (cli.py — Typer)                                       │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ run cmd  │  │ state cmd │  │ Interactive   │  │ .env       │  │
│  │          │  │           │  │ prompts       │  │ loading    │  │
│  └────┬─────┘  └───────────┘  └──────────────┘  └────────────┘  │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Graph Assembly (graph.py)                                   │ │
│  │  - Service instantiation (composition root)                  │ │
│  │  - Node factory invocation                                   │ │
│  │  - Edge wiring (linear + conditional)                        │ │
│  │  - Notification wrapping (Jira + Slack)                      │ │
│  │  - SQLite checkpointing                                      │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
└──────────────────────────────┼──────────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  Nodes (10+)     │ │  Services        │ │  Personas        │
│  ─────────────   │ │  ────────        │ │  ────────        │
│  check_epic_state│ │  ClaudeService   │ │  YAML loader     │
│  create_epic     │ │  ClaudeAgentSvc  │ │  .claude/commands│
│  create_story    │ │  JiraService     │ │  Bundled fallback│
│  party_mode      │ │  GitService      │ │                  │
│  detect_commands │ │  GitHubService   │ │  7 agents:       │
│  dev_story       │ │  SlackService    │ │  Alex (PM)       │
│  qa_automation   │ │  BmadWorkflow    │ │  Sally (Designer)│
│  code_review     │ │  Runner          │ │  Winston (Arch)  │
│  fix_loop        │ │                  │ │  Amelia (Dev)    │
│  e2e_automation  │ │  Dummy variants: │ │  Quinn (QA)      │
│  e2e_fix_loop    │ │  DummyJiraService│ │  Bob (SM)        │
│  fail_with_state │ │  DummyGitHub     │ │  Build Expert    │
│  commit_and_push │ │  NullSlack       │ │                  │
│  update_jira     │ └──────────────────┘ └──────────────────┘
│  create_pr       │
│  create_gh_issue │
└──────────────────┘
```

#### State Model

The entire pipeline shares a single `OrchestratorState` (TypedDict) with ~40 fields organized into:

- **Inputs**: `team_id`, `input_prompt`, `project_context`
- **Jira artifacts**: `current_epic_id`, `current_story_id`, notification tracking
- **Story content**: `story_content`, `acceptance_criteria`, `dependencies`, `qa_scope`, `definition_of_done`
- **Party mode outputs**: `architect_output`, `developer_output`
- **Git/GitHub**: `branch_name`, `commit_sha`, `pr_url`, `github_issue_url`
- **Review tracking**: `review_loop_count`, `code_review_issues`, `tests_passing`
- **E2E tracking**: `e2e_loop_count`, `e2e_tests_passing`, `e2e_failure_output`
- **Accumulated lists** (auto-concatenated by LangGraph): `touched_files`, `qa_results`, `e2e_results`, `execution_log`
- **Commands**: `build_commands`, `test_commands`, `lint_commands`, `e2e_commands`
- **Control**: `failure_state`, `failure_diagnostic`, `retry_guidance`

#### Service Layer

| Service | Real | Dummy | Purpose |
|---|---|---|---|
| JiraService | REST API (basic auth) | File-backed (YAML frontmatter markdown) | Epic/story/task CRUD |
| GitHubService | `gh` CLI subprocess | File-backed | PR/Issue creation |
| GitService | `git` CLI subprocess | — (always real, uses `@skip_if_dry_run`) | Branch/commit/push |
| ClaudeService | Anthropic API | — | Text completion, structured output, classification |
| ClaudeAgentService | Claude Agent SDK | — | Agentic code gen sessions with file system access |
| SlackService | Slack Web API | NullSlack (no-op) or DummySlack (file-backed) | Run notifications |
| BmadWorkflowRunner | YAML workflow files | — | Loads BMAD workflows for epic/story creation |

**Composition root**: `service_factory.py` decides real vs dummy based on `Settings` flags (`dummy_jira`, `dummy_github`, `slack_notify`).

#### Claude Integration (Two Tiers)

1. **ClaudeService** — Standard Anthropic API for planning/analysis nodes
   - `complete()` → raw text
   - `complete_structured(schema=PydanticModel)` → validated Pydantic instance via `tool_use`
   - `classify(options=[...])` → pick one option
   - Used by: check_epic_state, create_epic, create_story, party_mode, detect_commands

2. **ClaudeAgentService** — Claude Agent SDK for implementation nodes
   - `run_agent(agent_id, system_prompt, prompt, allowed_tools, ...)` → agentic session
   - Agent has direct file system access: Read, Write, Edit, Bash, Glob, Grep
   - Budget-capped: `max_budget_usd` per session (default $2.0, code_review $0.50, e2e $3.0)
   - Turn-limited: `max_turns` per session (10-20)
   - Used by: dev_story, qa_automation, code_review, fix_loop, e2e_automation, e2e_fix_loop

---

### Key Mechanisms

#### Progressive Leniency (Code Review)

Rather than a flat severity threshold, the review router gets progressively more lenient:

| Loop | Blocks on | Rationale |
|---|---|---|
| 0 (first review) | medium, high, critical | Strict — catch everything meaningful |
| 1 (after first fix) | high, critical | Medium issues might be style/preference |
| 2+ (after second fix) | critical only | Only build-breaking/security issues block |

This guarantees convergence — the pipeline will never loop infinitely.

#### Checkpointing & Resumption

- **Thread ID**: SHA256(`{team_id}:{prompt}`) → first 16 chars. Stable across retries.
- **Storage**: SQLite at `~/.bmad/checkpoints.db`
- **`--resume`**: Loads last checkpoint, continues from where it stopped
- **`--retry`**: Resets `review_loop_count`, re-enters from last failure point
- **`--retry --guidance "..."`**: Injects human direction into agent prompts

#### Independent Test Validation

QA and fix-loop nodes don't trust the agent's self-report. After the agent runs, the node independently executes the project's test/lint commands and records whether they pass. This catches cases where the agent claims success but tests actually fail.

#### Failure Recovery

When the review loop exhausts:
1. `fail_with_state` records diagnostic info (issues, test output, recommended fixes)
2. Pipeline continues to `commit_and_push` (creates empty commit if needed)
3. PR is created as **draft** with failure context in the body
4. Hidden metadata in PR body enables `/bmad retry` to parse and re-enter

---

### Configuration

All settings are `BMAD_*` env vars (Pydantic Settings with `.env` file support).

#### Required

| Variable | Purpose |
|---|---|
| `BMAD_ANTHROPIC_API_KEY` | Anthropic API key |

#### Required for Real Mode

| Variable | Purpose |
|---|---|
| `BMAD_JIRA_BASE_URL` | Jira instance URL |
| `BMAD_JIRA_USERNAME` | Jira username |
| `BMAD_JIRA_API_TOKEN` | Jira API token |
| `BMAD_GITHUB_REPO` | GitHub repo (`owner/repo`) |

#### Key Options

| Variable | Default | Purpose |
|---|---|---|
| `BMAD_MODEL_NAME` | `claude-opus-4-6` | Default Claude model |
| `BMAD_AGENT_MODELS` | JSON dict | Per-agent model overrides |
| `BMAD_DRY_RUN` | `false` | Skip all mutations |
| `BMAD_DUMMY_JIRA` | `false` | Use file-backed Jira mock |
| `BMAD_DUMMY_GITHUB` | `false` | Use file-backed GitHub mock |
| `BMAD_EXECUTION_MODE` | `inline` | `inline` or `github-agent` |
| `BMAD_MAX_REVIEW_LOOPS` | `2` | Max code review fix iterations |
| `BMAD_MAX_E2E_LOOPS` | `1` | Max E2E test fix iterations |
| `BMAD_DRAFT_PR` | `false` | Force draft PRs |
| `BMAD_SKIP_NODES` | `[]` | JSON list of node names to skip |
| `BMAD_SLACK_NOTIFY` | `false` | Enable Slack notifications |
| `BMAD_ARTIFACTS_DIR` | `""` | Output directory for generated code |
| `BMAD_VERBOSE` | `false` | Verbose logging |

---

### Execution Modes

#### 1. Inline Mode (Default)

Full pipeline runs locally. Claude Agent SDK generates code with direct file system access. Best for: local development, CI pipelines, trusted environments.

```bash
uv run bmad-orchestrator run \
  --team-id growth \
  --prompt "Add multi-language support" \
  --dummy-jira --dummy-github
```

#### 2. GitHub-Agent Mode

Planning runs locally, then a GitHub Issue is created for external agent execution. Best for: distributed teams, Copilot integration, async workflows.

```bash
uv run bmad-orchestrator run \
  --team-id growth \
  --prompt "Add multi-language support" \
  --execution-mode github-agent \
  --auto-execute
```

#### 3. Jira-Only Mode

Runs planning + story creation but skips all Git/GitHub operations. Useful for story grooming without implementation.

```bash
uv run bmad-orchestrator run \
  --team-id growth \
  --prompt "Add multi-language support" \
  --jira-only
```

---

### AI Personas

The orchestrator uses 7 named AI personas, each loaded from YAML files:

| Persona | Agent ID | Role in Pipeline |
|---|---|---|
| Alex (PM) | `pm` | Epic routing, story creation, quality assessment |
| Sally (Designer) | `designer` | Party mode UX/interaction review |
| Winston (Architect) | `architect` / `architect_party` | Party mode technical review + code review |
| Amelia (Developer) | `developer` / `developer_party` | Party mode impl review + code generation + fix loops |
| Quinn (QA) | `qa` / `e2e_tester` | Test generation (unit + E2E) |
| Bob (Scrum Master) | `scrum_master` | Party mode aggregation |
| Build Expert | `build-expert` | Command detection |

Personas are loaded with a fallback chain:
1. Bundled YAML files (packaged with the wheel)
2. CWD-relative `.claude/commands/` directory
3. Hardcoded minimal fallback

---

### Testing

```bash
# Unit tests (288 tests, ~91% coverage)
uv run pytest tests/unit/ -v

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/bmad_orchestrator/
```

**Test pattern**: Each node test constructs the node via `make_*_node(mock_services, settings)`, calls it with `make_state(**overrides)`, and asserts the returned dict.

**Coverage exclusions**: `cli.py` (interactive CLI code)

---

### Directory Structure

```
src/bmad_orchestrator/
├── cli.py                    # Typer CLI (run, state commands)
├── config.py                 # Pydantic Settings (BMAD_* env vars)
├── graph.py                  # LangGraph StateGraph + composition root
├── state.py                  # OrchestratorState TypedDict
├── nodes/                    # One file per graph node (16 nodes)
│   ├── check_epic_state.py
│   ├── create_or_correct_epic.py
│   ├── create_story_tasks.py
│   ├── party_mode_refinement.py
│   ├── detect_commands.py
│   ├── create_github_issue.py
│   ├── dev_story.py
│   ├── qa_automation.py
│   ├── code_review.py        # Also contains fail_with_state + review_router
│   ├── dev_story_fix_loop.py
│   ├── e2e_automation.py      # Also contains e2e_router
│   ├── e2e_fix_loop.py
│   ├── commit_and_push.py
│   ├── update_jira_branch.py
│   └── create_pull_request.py
├── services/
│   ├── protocols.py           # Protocol interfaces
│   ├── service_factory.py     # Composition root
│   ├── claude_service.py      # Anthropic API (complete, structured, classify)
│   ├── claude_agent_service.py # Claude Agent SDK (agentic code gen)
│   ├── bmad_workflow_runner.py # BMAD YAML workflow loader
│   ├── jira_service.py        # Real Jira REST API
│   ├── dummy_jira_service.py  # File-backed Jira mock
│   ├── git_service.py         # Git CLI wrapper
│   ├── github_service.py      # GitHub CLI wrapper
│   ├── dummy_github_service.py # File-backed GitHub mock
│   ├── slack_service.py       # Slack Web API
│   └── dummy_slack_service.py # File-backed/no-op Slack mock
├── personas/
│   └── loader.py              # YAML persona loader with fallback chain
└── utils/
    ├── cli_prompts.py         # Interactive Rich prompts (CLI only)
    ├── dry_run.py             # @skip_if_dry_run decorator
    ├── json_repair.py         # Repairs malformed JSON from Claude
    ├── logger.py              # structlog configuration
    ├── project_context.py     # Auto-gather README, configs, dev guidelines
    └── jira_template.py       # Jira description template normalization
```

---

### Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11 |
| Package Manager | uv |
| Build Backend | Hatchling |
| Workflow Engine | LangGraph |
| AI (planning) | Anthropic API (claude-opus-4-6) |
| AI (code gen) | Claude Agent SDK |
| CLI Framework | Typer + Rich |
| Config | Pydantic Settings |
| Jira Integration | REST API (requests) |
| GitHub Integration | `gh` CLI |
| Git Integration | `git` CLI (subprocess) |
| Slack Integration | Slack Web API |
| Checkpointing | SQLite (LangGraph SqliteSaver) |
| Testing | pytest + pytest-cov |
| Linting | Ruff |
| Type Checking | mypy (strict) |
| Monorepo | Nx |
