# Installation Guide (Dev Mode)

How to install the BMAD Orchestrator in editable/dev mode and run it against another project.

---

## Prerequisites

```bash
# uv (package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# gh CLI (required for real GitHub mode)
brew install gh && gh auth login

# Python 3.11 is pinned — uv handles this automatically
```

---

## Step 1: Install dependencies

From the orchestrator directory:

```bash
cd apps/autonomous-engineering-orchestrator
uv sync --dev
```

---

## Step 2: Install the CLI globally in editable mode

This makes `bmad-orchestrator` available system-wide while still reading from your local source files (changes to source are reflected immediately):

```bash
# Still in apps/autonomous-engineering-orchestrator
uv tool install --editable .
```

Verify:

```bash
bmad-orchestrator --help
```

---

## Step 3: Configure environment variables

The orchestrator uses **layered `.env` loading**:

1. **Orchestrator `.env`** (base defaults) — shared credentials like Jira, GitHub, Anthropic API key
2. **Target project `.env`** (overrides) — project-specific settings that override the base

### 3a. Set up the orchestrator's base `.env`

```bash
cd apps/autonomous-engineering-orchestrator
cp .env.example .env
```

Edit `.env` with your shared credentials:

```bash
# Required
BMAD_ANTHROPIC_API_KEY=sk-ant-...

# Required for real Jira
BMAD_JIRA_BASE_URL=https://yourorg.atlassian.net
BMAD_JIRA_USERNAME=you@yourorg.com
BMAD_JIRA_API_TOKEN=ATATT...
BMAD_JIRA_PROJECT_KEY=PUG

# Required for real GitHub
BMAD_GITHUB_REPO=yourorg/your-repo
BMAD_GITHUB_BASE_BRANCH=main
```

### 3b. (Optional) Override per target project

If a target project needs different settings (e.g. a different Jira project or GitHub repo), create a `.env` in that project's root. Values here override the orchestrator's base:

```bash
cd /path/to/your-target-project

# Only include the values you want to override
cat > .env << 'EOF'
BMAD_JIRA_PROJECT_KEY=OTHER
BMAD_GITHUB_REPO=yourorg/other-repo
EOF
```

If the target project has no `.env` (or doesn't define BMAD variables), the orchestrator's base `.env` is used as-is.

---

## Step 4: Run from the target project

Generated code is written to the **current working directory** (the target project root) by default (`BMAD_ARTIFACTS_DIR` defaults to `""`):

```bash
# Inside target project
bmad-orchestrator run \
  --team-id PUG \
  --prompt "Add a user authentication feature"
```

### Smoke test (no real APIs needed)

```bash
bmad-orchestrator run \
  --team-id PUG \
  --prompt "Add hello world endpoint" \
  --dummy-jira \
  --dummy-github \
  --dry-run
```

---

## CLI flags reference

| Flag | Purpose |
|------|---------|
| `--team-id` / `-t` | Team identifier (e.g. `PUG`). Prompted if omitted. |
| `--prompt` / `-p` | Feature description or Jira epic key. Prompted if omitted. |
| `--dummy-jira` | Skip real Jira, use file-backed mock |
| `--dummy-github` | Skip real GitHub, use file-backed mock |
| `--dry-run` | No mutations at all (Jira/Git/PR) |
| `--skip-nodes` / `-s` | Comma-separated node names to skip (e.g. `qa_automation,code_review`) |
| `--resume` | Continue from last checkpoint |
| `--retry` | Retry from last code-review failure (implies `--resume`) |
| `--guidance` / `-g` | Extra instructions injected into agents on `--retry` or `--resume` |
| `--epic-key` / `-e` | Use a specific existing Jira epic (skips interactive selection) |
| `--jira-only` | Run Jira + Claude but skip Git/GitHub operations |
| `--model` / `-m` | Override the Claude model name |
| `--verbose` / `-v` | Show full agent prompts and responses |

---

## Notes

- **Logs & checkpoints** are stored in `~/.bmad/` — not in the target project
- **Personas** are bundled into the installed package from `.claude/commands/` — no need to copy them to the target project
- Updates to the orchestrator source are reflected immediately (editable install — no reinstall needed)
