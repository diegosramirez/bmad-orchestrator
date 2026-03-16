# Detailed Plan — Deploy `bmad-orchestrator` to a Test Environment with GitHub Actions + Slack

## Goal

Deploy the existing `bmad-orchestrator` into a **test execution environment** so that:

- a user can trigger a run
- the run executes in a clean environment
- the user can **see progress**
- the user can **provide feedback / input**
- the orchestrator can eventually create a branch and PR in a target repo

This plan assumes:

- you **already have the automation/orchestrator code**
- for V1, you want:
  - **GitHub Actions** as the execution environment
  - **Slack** as the user interaction surface
- this is a **test / MVP environment**, not full production

---

# 1. Recommended V1 Architecture

## Main components

### 1. `bmad-orchestrator`

Your existing Python app / LangGraph / BMAD orchestration logic.

Responsibilities:

- analyze request
- inspect codebase
- generate plan
- modify code
- run checks
- determine whether user input is needed
- create output artifacts
- create PR when ready

### 2. GitHub Actions

Execution engine.

Responsibilities:

- run the orchestrator in an isolated environment
- clone the target repo
- install dependencies
- run the orchestrator
- push a branch
- create a draft PR
- expose logs/progress in GitHub Actions UI

### 3. Slack

Interaction surface.

Responsibilities:

- trigger a run
- receive run status notifications
- receive questions from the orchestrator
- allow the user to reply
- trigger a resume of the run if needed

### 4. Tiny Slack bridge

A very small service that sits between Slack and GitHub Actions.

Responsibilities:

- receive Slack command or message
- trigger GitHub workflow dispatch
- receive user reply
- trigger resume workflow
- post status updates back to Slack

### 5. State persistence

A minimal way to save and reload run state when the orchestrator pauses for user feedback.

For V1:

- JSON state file
- stored as workflow artifact, repo artifact, or another very lightweight store

---

# 2. High-Level Flow

```text
User in Slack
   -> Slack command/message
   -> Slack bridge
   -> GitHub Actions workflow starts
   -> GitHub Action runs bmad-orchestrator
   -> Progress visible in Actions logs
   -> If input needed, orchestrator pauses
   -> Slack receives question
   -> User replies in Slack
   -> Slack bridge triggers resume workflow
   -> GitHub Action resumes orchestrator
   -> Branch + Draft PR created
   -> Slack receives final result
```

---

# 3. Why This Is a Good V1

## Benefits

### Minimal infrastructure

You do not need to build:

- a backend worker platform
- queues
- a web dashboard
- a database on day one

### Clear execution environment

GitHub Actions gives:

- clean runner per execution
- logs
- cancellation
- repo-friendly execution

### Natural feedback channel

Slack is already where humans communicate, so it is a good place for:

- trigger
- approvals
- lightweight input
- notifications

### Easy to demo

This architecture is easy to explain to a client:

- Slack starts the work
- GitHub Actions runs the job
- PR is the output

---

# 4. Recommended Repo Layout

## Automation repository

Create or use a dedicated automation repo, for example:

```text
ai-dev-automation
```

Suggested structure:

```text
ai-dev-automation/
  .github/
    workflows/
      start-run.yml
      resume-run.yml
  orchestrator/
    run.py
    state_store.py
    github_ops.py
    slack_notifications.py
    prompts/
    services/
  slack_bridge/
    app.py
  docs/
  scripts/
  requirements.txt
  README.md
```

## Target repository

The client repo or test repo that the orchestrator will modify.

For V1, strongly recommended:

- start with **one target repo**
- keep the use case narrow
- create **draft PRs only**

---

# 5. Deployment Strategy

## Execution environment

Deploy the orchestrator into **GitHub Actions**, not onto your laptop as the main runtime.

### What this means

Your code lives in the automation repo.

When a workflow starts, GitHub:

- spins up a runner
- checks out the automation repo
- installs dependencies
- clones the target repo
- runs the orchestrator

### Why this is the right test environment

- isolated per run
- visible logs
- no always-on server needed
- easy to cancel
- easy to show to stakeholders

---

# 6. Progress Visibility

## Main progress surface: GitHub Actions

The user should be able to open the GitHub Actions run and see progress like:

- Step 1: Load request
- Step 2: Clone target repo
- Step 3: Analyze codebase
- Step 4: Generate implementation plan
- Step 5: Ask for user input
- Step 6: Apply code changes
- Step 7: Run tests/build/lint
- Step 8: Create draft PR

## Secondary progress surface: Slack

Slack should receive milestones like:

- run started
- waiting for user input
- resumed
- PR created
- failed

### Recommendation

Use:

- **GitHub Actions** for detailed logs
- **Slack** for notifications and decision points

---

# 7. Feedback / User Input Model

This is the most important design choice.

## Recommended approach: pause + resume

Do **not** try to keep one GitHub Actions workflow alive waiting for Slack messages.

Instead:

### Start run

- workflow starts
- orchestrator runs
- if no user input is needed, it completes

### Pause

If user input is needed:

- orchestrator writes run state to a file
- workflow posts a question to Slack
- workflow exits with a known “waiting for input” result

### Resume

When the user replies:

- Slack bridge receives the reply
- Slack bridge triggers a second GitHub workflow
- second workflow loads the saved state
- orchestrator resumes from the paused point

## Why this is better

- simpler than long-lived interactive jobs
- easier to reason about
- easier to retry
- more robust for MVP

---

# 8. Minimal State Persistence

For V1, you need only lightweight state persistence.

## State to save

At minimum:

- run id
- target repo
- base branch
- current orchestrator step
- plan summary
- pending question
- previous outputs
- branch name if already created
- any structured context needed for resume

## Suggested format

Use JSON.

Example conceptual structure:

```json
{
  "run_id": "run-001",
  "status": "waiting_for_user",
  "target_repo": "org/repo-name",
  "base_branch": "development",
  "current_step": "choose_implementation_path",
  "question": "I found two likely implementation paths. Which should I use?",
  "choices": ["Controller-first", "Service-first"],
  "context": {
    "ticket": "PUG-437",
    "prompt": "Implement cursor pagination"
  }
}
```

## Where to store it

For MVP, choose one:

- GitHub Actions artifact
- lightweight persisted file in automation repo branch
- tiny external store if needed later

For the first demo, artifact or simple persisted file is enough.

---

# 9. Detailed Implementation Plan

## Phase 1 — Define the narrow MVP

Pick a very specific first use case.

### Recommended scope

- one Slack trigger
- one GitHub Action run
- one target repo
- one orchestrator flow
- one possible pause/resume
- create a **draft PR only**

### Explicit guardrails

- no auto-merge
- no direct push to protected branches
- no production deployment
- no broad repo access
- no multiple repos yet

---

## Phase 2 — Make GitHub Actions the execution environment

### Objective

Run the existing `bmad-orchestrator` manually through GitHub Actions before involving Slack.

### Tasks

1. Create a dedicated automation repo if not already done.
2. Add a workflow, e.g. `start-run.yml`.
3. Add inputs such as:
   - `target_repo`
   - `base_branch`
   - `prompt`
   - `run_id`
4. In the workflow:
   - checkout automation repo
   - set up Python
   - install dependencies
   - clone target repo
   - run the orchestrator
5. Ensure progress is logged clearly.

### Success criteria

- workflow runs from GitHub UI
- orchestrator starts successfully
- target repo can be cloned
- logs are visible
- workflow exits cleanly

---

## Phase 3 — Prove repo write flow before AI PR logic

### Objective

Make sure GitHub Actions can safely create a branch and PR in the target repo.

### Tasks

1. Add a temporary step that:
   - creates a feature branch
   - writes a dummy file like `ai-demo-note.md`
   - commits
   - pushes
   - opens a draft PR
2. Confirm:
   - permissions are correct
   - branch naming works
   - PR creation works

### Success criteria

- draft PR is created in target repo
- no direct branch protection issues
- GitHub auth is validated

### Why this matters

This isolates repo permissions from orchestrator logic.

---

## Phase 4 — Integrate the real `bmad-orchestrator`

### Objective

Replace the dummy step with the real orchestration flow.

### Tasks

1. Wrap `bmad-orchestrator` in a CLI-friendly entrypoint.
2. Standardize input arguments such as:
   - target repo path
   - prompt
   - run id
   - mode
3. Make sure it can:
   - run in non-interactive mode
   - emit structured status
   - save state when it needs user input
4. Output useful logs for GitHub Actions.

### Success criteria

- orchestrator runs end to end in GitHub Actions
- happy path can finish without Slack
- branch and draft PR can be produced

---

## Phase 5 — Add Slack trigger

### Objective

Allow a user to start a run from Slack.

### Tasks

1. Create a Slack app.
2. Add:
   - slash command or channel-triggering mechanism
   - bot token
   - ability to post messages back
3. Build a tiny Slack bridge that:
   - receives the Slack command
   - parses input
   - triggers `workflow_dispatch` in GitHub Actions
4. Return immediate confirmation to Slack.

### Suggested Slack MVP trigger

Examples:

- `/ai-dev run repo=repo-name ticket=PUG-437`
- or a very simple formatted message

### Success criteria

- Slack message triggers GitHub workflow
- user receives “run started” confirmation
- GitHub Actions URL can be shared back

---

## Phase 6 — Add Slack notifications

### Objective

Use Slack as the notification and lightweight control channel.

### Notifications to send

- run started
- waiting for user input
- resumed
- completed
- failed
- PR created

### Tasks

1. Add Slack post-message support in the bridge or workflow support layer.
2. Include:
   - run id
   - target repo
   - current status
   - GitHub Actions link
   - PR link when available

### Success criteria

- Slack is informed at key milestones
- user no longer has to poll GitHub manually

---

## Phase 7 — Add pause/resume for user feedback

### Objective

Allow the orchestrator to ask for clarification and continue later.

### Tasks

1. Define a structured “needs input” contract for the orchestrator.
2. When input is needed:
   - orchestrator saves state
   - workflow posts the question to Slack
   - workflow exits in waiting state
3. Capture Slack reply.
4. Trigger `resume-run.yml`.
5. Load state and resume from the paused point.

### Success criteria

- a run can stop at a decision point
- user can answer in Slack
- a new workflow can resume the run
- PR can still be created at the end

---

# 10. Suggested Workflow Split

## Workflow 1 — `start-run.yml`

Triggered by:

- manual dispatch
- Slack bridge

Inputs:

- `run_id`
- `target_repo`
- `base_branch`
- `prompt`
- `triggered_by`

Responsibilities:

- set up runner
- clone target repo
- start orchestrator
- either:
  - complete successfully
  - fail
  - pause and notify Slack

## Workflow 2 — `resume-run.yml`

Triggered by:

- Slack reply processed by bridge

Inputs:

- `run_id`
- `user_reply`

Responsibilities:

- reload saved state
- continue orchestrator
- either:
  - complete
  - pause again
  - fail

---

# 11. Detailed Task Breakdown

## A. GitHub Actions / Test Environment

- create automation repo workflow files
- configure Python environment
- install orchestrator dependencies
- clone target repo
- configure Git identity
- configure branch creation
- configure PR creation
- structure logs for visibility

## B. Orchestrator integration

- add CLI wrapper if needed
- define input contract
- define output contract
- add “needs input” status
- add state save/load support
- add structured progress logs

## C. Slack integration

- create Slack app
- configure slash command or trigger pattern
- build Slack bridge endpoint
- parse user commands
- map Slack messages to run ids
- send notifications
- capture user replies

## D. State management

- define JSON schema
- save on pause
- load on resume
- track current step and context

## E. PR output

- ensure branch naming convention
- ensure draft PR creation
- generate PR title/body from orchestrator output
- include validation summary if available

---

# 12. Security / Safety Guardrails for Test Environment

Even for a test setup, apply these constraints:

## GitHub

- feature branches only
- draft PR only
- no direct pushes to protected branches
- restrict target repos to approved ones

## Slack

- limit trigger usage to approved users/channels if possible

## Secrets

Store only in GitHub Secrets / environment variables:

- GitHub token/app credentials
- Slack bot token
- Slack signing secret
- LLM API keys

## Orchestrator

- limit file modification scope if possible
- avoid infra/prod files initially
- avoid autonomous merges or deployments

---

# 13. Recommended Milestones

## Milestone 1

GitHub Action runs the orchestrator manually and shows logs.

## Milestone 2

GitHub Action can create a dummy draft PR in the target repo.

## Milestone 3

GitHub Action can run the real orchestrator happy path and create a real draft PR.

## Milestone 4

Slack can trigger the workflow.

## Milestone 5

Slack receives final notifications.

## Milestone 6

Slack supports one pause/resume loop.

---

# 14. Recommended Order of Work

## Step 1

Get `bmad-orchestrator` running inside GitHub Actions manually.

## Step 2

Prove branch + draft PR creation with a dummy change.

## Step 3

Wire in the real orchestrator flow.

## Step 4

Add Slack trigger.

## Step 5

Add Slack notifications.

## Step 6

Add pause/resume for user feedback.

This order reduces risk because:

- repo permissions are validated early
- orchestrator runtime issues are isolated before Slack is added
- user interaction is added only after the happy path works

---

# 15. Success Definition for the MVP

The MVP is successful if the following scenario works:

1. A user triggers the run from Slack.
2. GitHub Actions starts and shows progress.
3. `bmad-orchestrator` runs in the GitHub test environment.
4. If needed, the run pauses and asks a question in Slack.
5. The user replies in Slack.
6. The run resumes through GitHub Actions.
7. A draft PR is created in the target repo.
8. Slack receives the PR link and final result.

---

# 16. What Not to Build Yet

To keep V1 realistic, avoid:

- database
- web dashboard
- multi-repo orchestration
- full RBAC/permissions system
- vector database / embeddings
- advanced analytics
- autonomous merge/deploy
- complex Slack UI from day one

Keep it narrow and prove the loop first.

---

# 17. Final Recommendation

For your current situation, the best plan is:

- deploy `bmad-orchestrator` into **GitHub Actions** as the test execution environment
- use **Slack** as the trigger + notification + lightweight feedback surface
- use a **pause/resume model** for human input
- keep state persistence **minimal and JSON-based**
- create **draft PRs only**
- start with **one target repo and one narrow use case**

This gives you a demoable MVP without overbuilding.

---

# 18. Immediate Next Actions

1. Create `start-run.yml` in the automation repo.
2. Make the workflow run `bmad-orchestrator` manually from GitHub UI.
3. Validate target repo clone + branch + draft PR with a dummy file.
4. Wrap the orchestrator to support structured status and optional pause.
5. Build the tiny Slack bridge.
6. Add Slack-triggered workflow dispatch.
7. Add pause/resume support.
