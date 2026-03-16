# BMAD Orchestrator — Pipeline Steps Reference

This document describes every step the orchestrator executes, what data flows between them, and how to run or test each step individually.

---

## Local Environment Setup

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | >= 3.11 | Runtime (`.python-version` pins to `3.11`) |
| [uv](https://docs.astral.sh/uv/) | latest | Python package manager (replaces pip/venv) |
| [gh](https://cli.github.com/) | latest | GitHub CLI — used by `create_pull_request` node |
| Git | any | Branching, committing, pushing |

### 1. Install uv (if not already installed)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or via Homebrew
brew install uv
```

### 2. Clone and navigate to the project

```bash
git clone git@github.com:digistore24/ds24-growth.git
cd ds24-growth/apps/autonomous-engineering-orchestrator
```

### 3. Create the virtual environment and install dependencies

```bash
uv sync
```

This reads `pyproject.toml` + `uv.lock`, creates `.venv/`, and installs all production and dev dependencies. No manual `pip install` needed.

### 4. Configure environment variables

```bash
cp .env.example .env
```

Then edit `.env` with your real credentials:

```env
# ─── Required ────────────────────────────────────────────────────────────────
BMAD_ANTHROPIC_API_KEY=sk-ant-...          # Anthropic API key
BMAD_JIRA_BASE_URL=https://yourorg.atlassian.net
BMAD_JIRA_USERNAME=you@yourorg.com
BMAD_JIRA_API_TOKEN=ATATT...               # Jira API token (not password)
BMAD_JIRA_PROJECT_KEY=PUG                  # Your Jira project key
BMAD_GITHUB_REPO=digistore24/ds24-growth   # owner/repo for PRs

# ─── Optional (with defaults) ────────────────────────────────────────────────
# BMAD_MODEL_NAME=claude-opus-4-6
# BMAD_GITHUB_BASE_BRANCH=main
# BMAD_GIT_AUTHOR_NAME=BMAD Orchestrator
# BMAD_GIT_AUTHOR_EMAIL=bmad@noreply.local
# BMAD_DRY_RUN=false
# BMAD_JIRA_ONLY=false
# BMAD_MAX_REVIEW_LOOPS=3
# BMAD_CHECKPOINT_DB_PATH=~/.bmad/checkpoints.db
# BMAD_BMAD_INSTALL_DIR=.claude
```

**Where to get credentials:**
- **Anthropic API key:** [console.anthropic.com](https://console.anthropic.com/) → API Keys
- **Jira API token:** [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) → Create API token
- **GitHub CLI auth:** Run `gh auth login` (uses browser-based OAuth, no token needed in `.env`)

### 5. Authenticate GitHub CLI

The `create_pull_request` node uses `gh` to create PRs. Authenticate once:

```bash
gh auth login
# Follow the browser-based flow
gh auth status  # verify
```

### 6. Verify the setup

```bash
# Run unit tests (should all pass)
uv run pytest tests/unit/ -v

# Dry run the full pipeline (no external calls)
uv run bmad-orchestrator run --team-id growth --prompt "Test prompt" --dry-run

# Verify Jira connectivity
uv run python -c "
from dotenv import load_dotenv; load_dotenv()
from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.jira_service import JiraService
svc = JiraService(Settings())
epics = svc.find_epic_by_team('growth')
print(f'Found {len(epics)} epic(s):', [e['key'] for e in epics])
"
```

### Project Structure

```
apps/autonomous-engineering-orchestrator/
├── .claude/              # BMAD persona YAML files (loaded at runtime)
│   └── commands/         # Agent persona definitions (43 YAML files)
├── .env.example          # Template for environment variables
├── .vscode/
│   └── launch.json       # VS Code debug configurations
├── docs/
│   ├── pipeline-steps.md # This file
│   ├── installation.md   # Dev-mode installation guide
│   └── debugging.md      # VS Code debugging guide
├── pyproject.toml        # Dependencies, scripts, tool config
├── uv.lock               # Locked dependency versions
├── src/
│   └── bmad_orchestrator/
│       ├── cli.py                 # CLI entry point (Typer)
│       ├── config.py              # Pydantic Settings (reads .env)
│       ├── graph.py               # LangGraph StateGraph assembly
│       ├── state.py               # OrchestratorState TypedDict
│       ├── nodes/                 # One file per graph node
│       │   ├── check_epic_state.py
│       │   ├── create_or_correct_epic.py
│       │   ├── create_story_tasks.py
│       │   ├── party_mode_refinement.py
│       │   ├── dev_story.py
│       │   ├── qa_automation.py
│       │   ├── code_review.py
│       │   ├── dev_story_fix_loop.py
│       │   ├── commit_and_push.py
│       │   └── create_pull_request.py
│       ├── services/              # External service wrappers
│       │   ├── claude_service.py  # Anthropic API
│       │   ├── jira_service.py    # Jira REST API
│       │   ├── dummy_jira_service.py  # File-backed Jira mock
│       │   ├── git_service.py     # Git CLI
│       │   ├── github_service.py  # GitHub CLI (gh)
│       │   └── dummy_github_service.py  # File-backed GitHub mock
│       ├── personas/
│       │   └── loader.py          # Loads persona YAML → system prompts
│       └── utils/
│           ├── cli_prompts.py     # Interactive Rich prompts (CLI only)
│           ├── dry_run.py         # @skip_if_dry_run decorator
│           ├── json_repair.py     # Repairs malformed Claude JSON output
│           ├── project_context.py # Detects build/test/lint commands
│           └── logger.py          # structlog configuration
└── tests/
    └── unit/                      # 237 unit tests, ~91% coverage
        ├── conftest.py
        ├── nodes/
        └── services/
```

---

## Architecture Overview

```
┌─────────────────────────┐
│        CLI (cli.py)      │  ← Interactive epic selection (before graph)
└───────────┬─────────────┘
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      LangGraph StateGraph                           │
│                                                                     │
│  START                                                              │
│    │                                                                │
│    ▼                                                                │
│  1. check_epic_state ──► 2. create_or_correct_epic                  │
│                               │                                     │
│                               ▼                                     │
│                          3. create_story_tasks                      │
│                               │                                     │
│                               ▼                                     │
│                          4. party_mode_refinement                   │
│                               │                                     │
│                               ▼                                     │
│                     5. dev_story ◄─────────────────────────┐        │
│                     (self-verifies: build/test/lint        │        │
│                      with up to 1 self-correction)         │        │
│                               │                            │        │
│                               ▼                            │        │
│                          6. qa_automation                  │        │
│                               │                            │        │
│                               ▼                            │        │
│                     7. code_review ◄── 8. dev_story_fix_loop        │
│                               │        (self-verifies too) ─────────┘│
│                      ┌────────┼────────┐                            │
│                      ▼        ▼        ▼                            │
│               commit_and   fail_    fix_loop ──► (back to 7)        │
│               _push      with_state                                 │
│                 │                                                    │
│                 ▼                                                    │
│            9. create_pull_request                                    │
│                 │                                                    │
│                 ▼                                                    │
│                END                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Shared State (`OrchestratorState`)

Every node reads from and writes to this shared TypedDict. The full schema lives in `src/bmad_orchestrator/state.py`.

| Field | Type | Set By | Description |
|-------|------|--------|-------------|
| `team_id` | `str` | CLI (input) | Team identifier, e.g. `"growth"` |
| `input_prompt` | `str` | CLI (input) | Original user prompt or epic summary |
| `project_context` | `str \| None` | CLI (input) | Auto-detected project context injected into all agents |
| `current_epic_id` | `str \| None` | check_epic_state / CLI | Jira epic key, e.g. `"PUG-437"` |
| `current_story_id` | `str \| None` | create_story_tasks | Jira story key, e.g. `"PUG-438"` |
| `epic_routing_reason` | `str \| None` | check_epic_state | Why the epic was added-to or created |
| `story_content` | `str \| None` | create_story_tasks / party_mode | Story description text |
| `acceptance_criteria` | `list[str] \| None` | create_story_tasks / party_mode | List of AC strings |
| `dependencies` | `list[str] \| None` | create_story_tasks | Story dependencies |
| `qa_scope` | `list[str] \| None` | create_story_tasks | What the QA agent should test |
| `definition_of_done` | `list[str] \| None` | create_story_tasks | DoD checklist |
| `architect_output` | `str \| None` | party_mode_refinement | Architecture review from "Winston" |
| `developer_output` | `str \| None` | party_mode_refinement | Implementation notes from "Amelia" |
| `base_branch` | `str \| None` | commit_and_push | The branch the feature branch is based on |
| `branch_name` | `str \| None` | commit_and_push | Git branch, e.g. `"bmad/growth/PUG-438-add-login"` |
| `commit_sha` | `str \| None` | commit_and_push | Git commit SHA |
| `pr_url` | `str \| None` | create_pull_request | GitHub pull request URL |
| `review_loop_count` | `int` | dev_story_fix_loop | Number of fix iterations completed |
| `code_review_issues` | `list[CodeReviewIssue]` | code_review | Issues found (replaced each review pass) |
| `touched_files` | `list[str]` | dev_story / dev_story_fix_loop | Files written to disk (accumulated) |
| `qa_results` | `list[QAResult]` | qa_automation | Test results (accumulated via `operator.add`) |
| `execution_log` | `list[ExecutionLogEntry]` | All nodes | Timestamped log entries (accumulated via `operator.add`) |
| `failure_state` | `str \| None` | dev_story / dev_story_fix_loop / fail_with_state | Error message if pipeline failed |
| `retry_guidance` | `str \| None` | CLI (`--guidance`) | Extra instructions injected on `--retry` or `--resume` |
| `build_commands` | `list[str]` | CLI (input) | Build commands detected from project config |
| `test_commands` | `list[str]` | CLI (input) | Test commands detected from project config |
| `lint_commands` | `list[str]` | CLI (input) | Lint commands detected from project config |
| `dev_guidelines` | `str \| None` | CLI (input) | Project dev guidelines injected into developer agents |

---

## Step 0 — CLI Interactive Epic Selection

**File:** `src/bmad_orchestrator/cli.py` + `src/bmad_orchestrator/utils/cli_prompts.py`

**What it does:** Before the graph starts, the CLI resolves which epic to use interactively.

**Logic:**
1. If `--epic-key` is provided → skip interactive flow, use it directly
2. If `--dry-run` → skip interactive flow
3. If prompt looks like a Jira key (e.g. `PUG-437`) → validate via `JiraService.get_epic()` → show epic details → ask user to confirm
4. If prompt is free text → fetch open epics via `JiraService.find_epic_by_team()` → show numbered list → user picks one or chooses "create new"
5. Final confirmation before any Jira writes

**Run it:**
```bash
# Jira key as prompt — shows epic, asks confirmation
cd apps/autonomous-engineering-orchestrator
uv run bmad-orchestrator run --team-id growth --prompt "PUG-437" --jira-only

# Free text — shows epic list, user picks
uv run bmad-orchestrator run --team-id growth --prompt "Add SSO login" --jira-only

# Skip interactive (explicit epic key)
uv run bmad-orchestrator run --team-id growth --epic-key PUG-437 --prompt "Add SSO login" --jira-only

# Dry run — no prompts, no Jira calls
uv run bmad-orchestrator run --team-id growth --prompt "PUG-437" --dry-run
```

---

## Step 1 — `check_epic_state`

**File:** `src/bmad_orchestrator/nodes/check_epic_state.py`

**Persona:** PM (`pm`)

**What it does:** Determines whether the work request fits an existing epic or needs a new one.

**Reads from state:**
| Field | Purpose |
|-------|---------|
| `team_id` | Used to search epics in the project |
| `input_prompt` | Compared against existing epics |
| `current_epic_id` | If already set (via `--epic-key` or CLI selection), short-circuits |

**Writes to state:**
| Field | Value |
|-------|-------|
| `current_epic_id` | Epic key (e.g. `"PUG-437"`) or `None` (create new) |
| `execution_log` | One log entry |

**Logic:**
1. If `current_epic_id` is already set → return immediately (short-circuit)
2. Call `JiraService.find_epic_by_team(team_id)` to get open epics
3. If no epics → return `None` (new epic will be created)
4. Ask Claude (`classify`) whether the prompt fits an existing epic → `"add_to_existing"` or `"create_new"`
5. If match → return first epic's key. If not → return `None`

**Services used:** `JiraService.find_epic_by_team()`, `ClaudeService.classify()`

**Test individually:**
```python
# In a Python shell / script
from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.jira_service import JiraService
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.nodes.check_epic_state import make_check_epic_state_node

settings = Settings()  # reads from .env
jira = JiraService(settings)
claude = ClaudeService(settings)

node = make_check_epic_state_node(jira, claude, settings)

# Use make_initial_state() as a base — it populates all required fields
from bmad_orchestrator.graph import make_initial_state
state = make_initial_state("growth", "Add SSO login")
# Override specific fields as needed:
# state["current_epic_id"] = "PUG-437"  # test short-circuit

result = node(state)
print(result)
# → {"current_epic_id": "PUG-437" or None, "execution_log": [...]}
```

---

## Step 2 — `create_or_correct_epic`

**File:** `src/bmad_orchestrator/nodes/create_or_correct_epic.py`

**Persona:** PM (`pm`)

**What it does:** Either creates a new epic in Jira or course-corrects an existing epic's description.

**Reads from state:**
| Field | Purpose |
|-------|---------|
| `team_id` | Label for new epic |
| `input_prompt` | Work request description |
| `current_epic_id` | If set → course-correct; if `None` → create new |

**Writes to state:**
| Field | Value |
|-------|-------|
| `current_epic_id` | Epic key (existing or newly created) |
| `execution_log` | One log entry |

**Logic:**
- **Epic exists (`current_epic_id` is set):**
  1. Fetch epic description via `JiraService.get_story(epic_key)`
  2. Ask Claude (`complete_structured` → `EpicCorrectionDecision`) if the description needs updating
  3. If `needs_update=true` → call `JiraService.update_epic()` with new description
- **No epic:**
  1. Ask Claude (`complete_structured` → `EpicDraft`) to draft summary + description
  2. Call `JiraService.create_epic(summary, description, team_id)`

**Pydantic schemas:**
- `EpicDraft(summary: str, description: str)`
- `EpicCorrectionDecision(needs_update: bool, updated_description: str, reason: str)`

**Services used:** `JiraService.get_story()`, `JiraService.update_epic()`, `JiraService.create_epic()`, `ClaudeService.complete_structured()`

**Test individually:**
```python
node = make_create_or_correct_epic_node(jira, claude, settings)

# Test: course-correct existing epic
state["current_epic_id"] = "PUG-437"
result = node(state)
print(result)  # → {"current_epic_id": "PUG-437", "execution_log": [...]}

# Test: create new epic
state["current_epic_id"] = None
result = node(state)
print(result)  # → {"current_epic_id": "PUG-XXX", "execution_log": [...]}
```

---

## Step 3 — `create_story_tasks`

**File:** `src/bmad_orchestrator/nodes/create_story_tasks.py`

**Persona:** Scrum Master (`scrum_master`)

**What it does:** Creates a user story and sub-tasks in Jira under the epic.

**Reads from state:**
| Field | Purpose |
|-------|---------|
| `team_id` | Label for story |
| `input_prompt` | Used to generate story content |
| `current_epic_id` | Parent epic key |
| `current_story_id` | If set → idempotent skip (story already exists) |

**Writes to state:**
| Field | Value |
|-------|-------|
| `current_story_id` | Story key (e.g. `"PUG-438"`) |
| `new_story_created` | `True` if created, `False` if reused |
| `story_content` | Story description text |
| `acceptance_criteria` | List of AC strings |
| `execution_log` | One log entry |

**Logic:**
1. If `current_story_id` is already set and exists in Jira → reuse (idempotent)
2. Ask Claude (`complete_structured` → `StoryDraft`) to generate: summary, description, acceptance_criteria (min 2), tasks (min 2)
3. Call `JiraService.create_story(epic_key, summary, description, ac, team_id)`
4. For each task in the draft → call `JiraService.create_task(story_key, summary, description)`

**Pydantic schemas:**
- `StoryDraft(summary: str, description: str, acceptance_criteria: list[str], tasks: list[TaskItem])`
- `TaskItem(summary: str, description: str)`

**Test individually:**
```python
node = make_create_story_tasks_node(jira, claude, settings)

state["current_epic_id"] = "PUG-437"
state["current_story_id"] = None  # force creation
result = node(state)
print(result)
# → {"current_story_id": "PUG-438", "new_story_created": True, "story_content": "...", ...}
```

---

## Step 4 — `party_mode_refinement`

**File:** `src/bmad_orchestrator/nodes/party_mode_refinement.py`

**Personas:** Designer (`designer`), Architect (`architect`), Developer (`developer`), Scrum Master (`scrum_master` as aggregator)

**What it does:** Three virtual experts review the story, then an aggregator synthesizes their feedback into a refined story. Updates the Jira story description.

**Reads from state:**
| Field | Purpose |
|-------|---------|
| `story_content` | The story to review |
| `acceptance_criteria` | Current ACs |
| `input_prompt` | Original request context |
| `current_story_id` | Story key (for Jira update) |

**Writes to state:**
| Field | Value |
|-------|-------|
| `designer_output` | UX/interaction notes (Sally) |
| `architect_output` | Architecture guidance (Winston) |
| `developer_output` | Implementation notes (refined by aggregator) |
| `story_content` | Enriched description with all expert feedback |
| `acceptance_criteria` | Updated AC list |
| `execution_log` | 5 log entries (designer, architect, developer, aggregator, Jira update) |

**Logic:**
1. **Designer (Sally):** `claude.complete()` → UX review (user flows, edge cases, UX concerns)
2. **Architect (Winston):** `claude.complete()` → technical review (data model, API, risks)
3. **Developer (Amelia):** `claude.complete()` → implementation approach (files to modify, complexity)
4. **Aggregator (Bob):** `claude.complete_structured()` → `RefinedStory` synthesizing all feedback
5. Update Jira story description with enriched content via `JiraService.update_story_description()`

**Pydantic schema:**
- `RefinedStory(updated_summary: str, updated_description: str, acceptance_criteria: list[str], implementation_notes: str)`

**Services used:** `ClaudeService.complete()` (x3), `ClaudeService.complete_structured()` (x1), `JiraService.update_story_description()` (x1)

**Test individually:**
```python
node = make_party_mode_node(claude, jira, settings)

state["story_content"] = "As a user I want SSO login so that..."
state["acceptance_criteria"] = ["Users can log in via Google", "Session persists"]
state["current_story_id"] = "PUG-438"
result = node(state)
print(result.keys())
# → designer_output, architect_output, developer_output, story_content, acceptance_criteria, execution_log
```

---

## Step 5 — `dev_story`

**File:** `src/bmad_orchestrator/nodes/dev_story.py`

**Persona:** Developer (`developer`)

**What it does:** Generates code by producing file operations (create/modify/delete), applies them to disk, then self-verifies by running build/test/lint. If checks fail, the developer self-corrects once before giving up.

**Reads from state:**
| Field | Purpose |
|-------|---------|
| `story_content` | What to implement |
| `acceptance_criteria` | Requirements to satisfy |
| `architect_output` | Architecture guidance |
| `developer_output` | Implementation plan |
| `dev_guidelines` | Project-specific coding guidelines |
| `build_commands` | Build commands to verify after writing files |
| `test_commands` | Test commands to verify after writing files |
| `lint_commands` | Lint commands to verify after writing files |

**Writes to state:**
| Field | Value |
|-------|-------|
| `touched_files` | List of files written to disk |
| `execution_log` | Log entries |
| `failure_state` | Set if build/test/lint still fails after self-correction |

**Logic:**
1. Two-phase code generation via `_generate_chunked()`:
   - Phase 1: Claude produces a file plan (which files to create/modify/delete)
   - Phase 2: Claude generates full content for each file in parallel (up to 10 workers)
2. Apply file operations to disk via `_apply_operations()`
3. **Self-verification loop** (up to 2 attempts, skipped in `--dry-run`):
   - Run TypeScript compile check (if applicable), then `build_commands`, `test_commands`, `lint_commands`
   - If all pass → done
   - If any fail → inject error context and regenerate affected files (one self-correction attempt)
   - If still failing → set `failure_state` and halt pipeline

**Pydantic schemas:**
- `FilePlan(files: list[FilePlanItem])` — Phase 1 output
- `FileOperationModel(action, path, content)` — Phase 2 per-file output

**Side effects:** Writes files to disk, runs project build/test/lint commands

**Test individually:**
```python
node = make_dev_story_node(claude, settings)

state["story_content"] = "Full enriched story..."
state["acceptance_criteria"] = ["AC1", "AC2"]
state["architect_output"] = "Use REST API + PostgreSQL..."
state["developer_output"] = "Create src/auth/sso.py..."
result = node(state)
print(result)
# → {"execution_log": [...]} or {"failure_state": "Lint failed...", ...}
```

---

## Step 6 — `qa_automation`

**File:** `src/bmad_orchestrator/nodes/qa_automation.py`

**Persona:** QA (`qa`)

**What it does:** Generates test files for the story, applies them to disk, then runs `pytest`.

**Reads from state:**
| Field | Purpose |
|-------|---------|
| `story_content` | Context for test generation |
| `acceptance_criteria` | Each AC must have at least one test |

**Writes to state:**
| Field | Value |
|-------|-------|
| `qa_results` | List of `QAResult` dicts (appended) |
| `execution_log` | One log entry |

**Logic:**
1. Ask Claude (`complete_structured` → `FileOperationList`) to generate test files
2. Apply test file operations to disk
3. Run `python -m pytest --tb=short -q`
4. Parse results into `QAResult`

**Side effects:** Writes test files to disk, runs `pytest`

**Test individually:**
```python
node = make_qa_automation_node(claude, settings)

state["story_content"] = "Full story..."
state["acceptance_criteria"] = ["AC1", "AC2"]
result = node(state)
print(result)
# → {"qa_results": [{"test_file": "pytest", "passed": true, "output": "..."}], ...}
```

---

## Step 7 — `code_review`

**File:** `src/bmad_orchestrator/nodes/code_review.py`

**Persona:** Architect (`architect`)

**What it does:** Reviews the generated code for security, quality, performance, and AC coverage.

**Reads from state:**
| Field | Purpose |
|-------|---------|
| `story_content` | Context for review |
| `acceptance_criteria` | Coverage check |

**Writes to state:**
| Field | Value |
|-------|-------|
| `code_review_issues` | List of `CodeReviewIssue` dicts (appended) |
| `execution_log` | One log entry |

**Logic:**
1. Ask Claude (`complete_structured` → `ReviewResult`) to review code
2. Categorize issues by severity: `low`, `medium`, `high`, `critical`
3. Return all issues (the router decides what happens next)

**Pydantic schemas:**
- `ReviewResult(issues: list[ReviewIssueItem], overall_assessment: str)`
- `ReviewIssueItem(severity: str, file: str, line: int, description: str, fix_required: bool)`

**Routing logic (conditional edge):**
| Condition | Next Node |
|-----------|-----------|
| Medium+ issues AND `review_loop_count < max_review_loops` (default 2) | `dev_story_fix_loop` |
| Medium+ issues AND loops exhausted | `fail_with_state` (END) |
| No medium+ issues | `commit_and_push` |

---

## Step 8 — `dev_story_fix_loop`

**File:** `src/bmad_orchestrator/nodes/dev_story_fix_loop.py`

**Persona:** Developer (`developer`)

**What it does:** Fixes medium+ code review issues, self-verifies the fixes compile and pass tests, then loops back to `code_review`.

**Reads from state:**
| Field | Purpose |
|-------|---------|
| `code_review_issues` | Issues to fix |
| `review_loop_count` | Current iteration |
| `story_content` | Context for fixes |
| `dev_guidelines` | Project-specific coding guidelines |
| `build_commands` | Build commands to verify after fixes |
| `test_commands` | Test commands to verify after fixes |
| `lint_commands` | Lint commands to verify after fixes |

**Writes to state:**
| Field | Value |
|-------|-------|
| `review_loop_count` | Incremented by 1 |
| `code_review_issues` | Cleared to `[]` (next review starts fresh) |
| `touched_files` | Files written to disk (accumulated) |
| `execution_log` | Log entries |
| `failure_state` | Set if build/test/lint still fails after self-correction |

**Logic:**
1. Filter for medium+ severity issues
2. Two-phase code generation via `_generate_chunked()` to produce fix operations
3. Apply fixes to disk
4. **Self-verification loop** (up to 2 attempts, skipped in `--dry-run`):
   - Run build/test/lint commands
   - If all pass → done, flow returns to `code_review`
   - If any fail → inject error context and self-correct once
   - If still failing → set `failure_state` and halt pipeline
5. Clear `code_review_issues` and increment `review_loop_count`

---

## Step 9 — `commit_and_push`

**File:** `src/bmad_orchestrator/nodes/commit_and_push.py`

**Persona:** None (pure Git operations)

**What it does:** Creates a feature branch, commits all changes, and pushes to origin.

**Reads from state:**
| Field | Purpose |
|-------|---------|
| `team_id` | Branch name prefix |
| `current_story_id` | Branch name component |
| `current_epic_id` | Commit message |
| `story_content` | Commit message summary |
| `input_prompt` | Fallback for commit message |
| `commit_sha` | Idempotency check (skip if already committed) |

**Writes to state:**
| Field | Value |
|-------|-------|
| `branch_name` | e.g. `"bmad/growth/PUG-438-add-sso-login"` |
| `commit_sha` | Git SHA |
| `execution_log` | One log entry |

**Logic:**
1. If `commit_sha` already set → skip (idempotent)
2. Generate branch name: `bmad/{team_id}/{story_id}-{slugified-summary}`
3. Create and checkout branch (or fetch if it exists on remote)
4. `git add -A`
5. `git commit -m "feat(growth): implement story PUG-438 [BMAD-ORCHESTRATED]"`
6. `git push -u origin {branch_name}`

**Services used:** `GitService.make_branch_name()`, `.create_and_checkout_branch()`, `.stage_all()`, `.commit()`, `.push()`

**Skipped in:** `--dry-run`, `--jira-only`

---

## Step 10 — `create_pull_request`

**File:** `src/bmad_orchestrator/nodes/create_pull_request.py`

**Persona:** None (pure GitHub operations)

**What it does:** Creates a GitHub pull request with a structured body.

**Reads from state:**
| Field | Purpose |
|-------|---------|
| `pr_url` | Idempotency check |
| `branch_name` | PR head branch |
| `team_id` | PR title |
| `input_prompt` | PR title |
| `current_story_id` | PR title and body |
| `story_content` | PR body |
| `acceptance_criteria` | PR body |
| `developer_output` | PR body |
| `qa_results` | PR body |
| `code_review_issues` | PR body |
| `review_loop_count` | PR body |

**Writes to state:**
| Field | Value |
|-------|-------|
| `pr_url` | GitHub PR URL |
| `execution_log` | One log entry |

**Logic:**
1. If `pr_url` already set → skip (idempotent)
2. Check if PR already exists on GitHub via `gh pr list` → if yes, return existing URL
3. Build PR body from state (story, ACs, dev notes, QA results, review summary)
4. Create PR via `gh pr create`

**PR title format:** `feat(growth): Add SSO login [PUG-438]`

**Services used:** `GitHubService.pr_exists()`, `GitHubService.create_pr()`

**Skipped in:** `--dry-run`, `--jira-only`

---

## Running Individual Steps

### Option A: Dry Run (Full Pipeline, No Side Effects)

```bash
cd apps/autonomous-engineering-orchestrator
uv run bmad-orchestrator run --team-id growth --prompt "Add SSO login" --dry-run
```

All nodes execute with fake/placeholder data. No Jira, Git, or GitHub calls.

### Option B: Jira Only (Steps 1-4 Are Real, Steps 5-9 Are Dry)

```bash
uv run bmad-orchestrator run --team-id growth --prompt "PUG-437" --jira-only
```

Steps 1-4 make real Jira + Claude API calls. Steps 5-9 (dev, QA, git, PR) run in dry-run mode.

### Option C: Resume / Inspect Checkpoint

```bash
uv run bmad-orchestrator run --team-id growth --prompt "PUG-437" --resume
```

Shows the checkpoint state table for the given thread without executing anything. Useful to see where a previous run stopped.

### Option D: Call a Node Function Directly (Python)

Every node is a factory function that returns a plain callable. You can invoke any node in isolation by constructing a state dict:

```python
# setup.py or Jupyter notebook
from dotenv import load_dotenv
load_dotenv()

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.jira_service import JiraService
from bmad_orchestrator.services.claude_service import ClaudeService
from bmad_orchestrator.graph import make_initial_state

settings = Settings()
jira = JiraService(settings)
claude = ClaudeService(settings)

# Create a base state
state = make_initial_state("growth", "Add SSO login", epic_key="PUG-437")

# --- Run step 1 only ---
from bmad_orchestrator.nodes.check_epic_state import make_check_epic_state_node
node_1 = make_check_epic_state_node(jira, claude, settings)
result_1 = node_1(state)
print("Step 1 output:", result_1)

# --- Feed result into step 2 ---
state = {**state, **result_1}
from bmad_orchestrator.nodes.create_or_correct_epic import make_create_or_correct_epic_node
node_2 = make_create_or_correct_epic_node(jira, claude, settings)
result_2 = node_2(state)
print("Step 2 output:", result_2)

# --- Feed result into step 3 ---
state = {**state, **result_2}
from bmad_orchestrator.nodes.create_story_tasks import make_create_story_tasks_node
node_3 = make_create_story_tasks_node(jira, claude, settings)
result_3 = node_3(state)
print("Step 3 output:", result_3)

# ... and so on for each step
```

### Option E: Run From a Specific Step (Manual State Injection)

If you want to skip steps 1-3 (e.g., you already have an epic and story in Jira) and start from party_mode_refinement:

```python
from dotenv import load_dotenv
load_dotenv()

from bmad_orchestrator.config import Settings
from bmad_orchestrator.services.jira_service import JiraService
from bmad_orchestrator.services.claude_service import ClaudeService

settings = Settings()
jira = JiraService(settings)
claude = ClaudeService(settings)

# Manually set the state to what steps 1-3 would have produced
# Tip: use make_initial_state() as a base and override only what you need
from bmad_orchestrator.graph import make_initial_state
state = make_initial_state("growth", "Add SSO login", epic_key="PUG-437")
state = {
    **state,
    "current_story_id": "PUG-438",
    "story_content": "As a user I want to log in via Google SSO...",
    "acceptance_criteria": [
        "Users can authenticate via Google OAuth2",
        "Session persists for 24 hours",
    ],
}

# Now run step 4 directly
from bmad_orchestrator.nodes.party_mode_refinement import make_party_mode_node
node = make_party_mode_node(claude, jira, settings)
result = node(state)
print(result)
```

---

## CLI Flags Quick Reference

| Flag | Short | Description |
|------|-------|-------------|
| `--team-id` | `-t` | Team identifier (required) |
| `--prompt` | `-p` | Jira key or free text description (required) |
| `--epic-key` | `-e` | Skip interactive selection, use this epic directly |
| `--dry-run` | | Simulate everything, no side effects |
| `--jira-only` | | Real Jira + Claude, but Git/GitHub in dry-run |
| `--resume` | | Show checkpoint state for this thread, then exit |
| `--model` | `-m` | Override Claude model name |
