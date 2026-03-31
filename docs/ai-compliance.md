# AI System Compliance Documentation

**System:** BMAD Autonomous Engineering Orchestrator
**Version:** 1.0
**Last Updated:** 2026-03-27
**Classification:** Limited / Minimal Risk (EU AI Act)

---

## 1. AI Act Risk Classification

### Assessment

The BMAD Orchestrator is an **internal developer productivity tool** that automates software engineering workflows: Jira epic/story creation, code generation, QA test authoring, code review, and pull request creation. It operates exclusively within internal engineering systems.

**Classification: Limited / Minimal Risk** under EU AI Act Article 6 and Annex III.

### Reasoning

| Criterion | Assessment |
|-----------|-----------|
| Processes personal data at scale | No — operates on source code and project metadata only |
| Safety-critical system | No — generates application code reviewed by humans before deployment |
| Biometric / surveillance | No |
| Critical infrastructure | No |
| Employment decisions | No |
| Access to essential services | No |

### Conditions That Would Require Reclassification

- Agent gains direct access to production systems or databases
- Agent processes customer personal data, payment data, or PII
- Agent output bypasses human review and deploys directly to production
- Agent is used for hiring, performance evaluation, or access control decisions

---

## 2. System Capabilities & Boundaries

### What the Agent Can Access

| System | Access Level | Details |
|--------|-------------|---------|
| **Local file system** | Read + Write | Tools: `Read`, `Write`, `Edit`, `Bash`, `Glob`, `Grep`. Scoped to `BMAD_ARTIFACTS_DIR` when configured. |
| **Git** | Full local operations | Create branches, stage files, commit, push. Author identity: configurable via `BMAD_GIT_AUTHOR_NAME` / `BMAD_GIT_AUTHOR_EMAIL` (default: `BMAD Orchestrator <bmad@noreply.local>`). |
| **GitHub** | Authenticated via `GITHUB_TOKEN` | Create pull requests, create issues, dispatch workflows, add comments and labels. |
| **Jira** | REST API via configured credentials | Create epics, stories, and tasks. Transition issue status. Add and update comments. |
| **Slack** | Bot token (optional) | Post messages, thread replies, and interactive buttons to a configured channel. |
| **Anthropic API** | API key | Send prompts to Claude models for code generation, structured output, and classification. |

### What the Agent Cannot Do

| Capability | Status | Enforcement |
|------------|--------|-------------|
| **Internet access** | Blocked | `WebSearch` and `WebFetch` are explicitly disallowed tools |
| **Agent delegation** | Blocked | `Task` and `Agent` tools are explicitly disallowed |
| **Direct production deployment** | Blocked | Agent creates draft PRs only; cannot merge or deploy |
| **Database access** | None | No database credentials or connections |
| **Force push** | Not used | Git operations use standard push only |

### Resource Constraints

| Constraint | Default | Configurable Via |
|-----------|---------|-----------------|
| Per-session budget | $2.00 USD | `max_budget_usd` parameter per agent |
| Code review budget | $0.50 USD | Hardcoded in `code_review.py` |
| E2E automation budget | $3.00 USD | Hardcoded in `e2e_automation.py` |
| Max turns per agent | 10–30 (varies by role) | `max_turns` parameter per agent |
| Execution timeout | 30 minutes | `BMAD_EXECUTION_TIMEOUT_MINUTES` |
| Max review loops | 2 | `BMAD_MAX_REVIEW_LOOPS` / `--max-loops` |
| Max E2E loops | 1 | `BMAD_MAX_E2E_LOOPS` |
| Output token limit | 128,000 | `CLAUDE_CODE_MAX_OUTPUT_TOKENS` env var |

### Per-Agent Tool Restrictions

| Agent Role | Allowed Tools | Notes |
|-----------|---------------|-------|
| Developer | Read, Write, Edit, Bash, Glob, Grep | Full file system access for code generation |
| QA Automation | Read, Write, Edit, Bash, Glob, Grep | Full access for test authoring |
| Code Reviewer | Read, Glob, Grep | **Read-only** — cannot modify files |
| E2E Automation | Read, Write, Edit, Bash, Glob, Grep | Full access for E2E test authoring |
| Fix Loop agents | Read, Write, Edit, Bash, Glob, Grep | Full access for applying fixes |

---

## 3. Human Oversight & Approval Gates

### 3.1 GitHub Actions Interface

| Gate | Human Action Required | Can Be Bypassed? | Reference |
|------|----------------------|-------------------|-----------|
| **Start pipeline** | Click "Run workflow" in GitHub Actions UI | No — `workflow_dispatch` requires manual trigger | `.github/workflows/bmad-start-run.yml` |
| **Execute from issue** | Manually add `bmad-execute` label to GitHub issue | No — workflow only fires on this label event | `.github/workflows/bmad-issue-executor.yml` |
| **Retry failed run** | Comment `/bmad retry [guidance]` on the PR | No — workflow only fires on this comment pattern | `.github/workflows/bmad-retry.yml` |
| **Merge AI-generated code** | Manually review and merge the draft PR | No — the orchestrator never merges its own PRs | GitHub branch protection (external) |
| **Skip pipeline nodes** | Select skip checkboxes in workflow dispatch UI | N/A — optional control | `.github/workflows/bmad-start-run.yml` inputs |

**Key guarantee:** AI-generated code is always delivered as a **draft pull request**. A human must explicitly review and merge it. The orchestrator has no capability to merge PRs or push to protected branches.

### 3.2 Jira Interface

| Gate | Human Action Required | Can Be Bypassed? | Reference |
|------|----------------------|-------------------|-----------|
| **Epic selection** (CLI mode) | Confirm epic choice via interactive prompt | Yes — `--non-interactive` or `--epic-key` flag | `cli.py` lines 568–627 |
| **Epic/story creation** | Automatic after pipeline is triggered | N/A — creation is part of the automated workflow | `create_or_correct_epic.py`, `create_story_tasks.py` |
| **Status updates** | None — informational comments only | N/A | `graph.py` step notifications |

**Jira status updates** (e.g., "🚀 Process started", "✅ Step completed") are one-way informational notifications. They do not modify issue status beyond what the pipeline requires and do not make decisions that affect production systems.

**Epic and story creation** occurs automatically once the pipeline is triggered. The human gate is at the **trigger point** (GitHub Actions dispatch or CLI confirmation), not at the individual Jira artifact level.

### 3.3 Slack Interface

| Gate | Human Action Required | Can Be Bypassed? | Reference |
|------|----------------------|-------------------|-----------|
| **Retry button** | Click interactive button → triggers `/bmad retry` flow | N/A — advisory UI | `graph.py` lines 232–257 |
| **Refine button** | Click interactive button → triggers refinement | N/A — advisory UI | `graph.py` lines 258–283 |
| **Status messages** | None — informational thread updates | N/A | `graph.py` lines 189–299 |

Slack messages are posted under a **bot identity**, making the AI origin visible. Interactive buttons provide convenient human intervention points but do not bypass the GitHub-based approval gates.

### 3.4 Approval Flow Summary

```
Human triggers pipeline (GitHub Actions dispatch / CLI / Issue label)
    │
    ▼
Orchestrator creates Jira artifacts (epic, stories, tasks)
    │
    ▼
Orchestrator generates code, tests, and runs review
    │  ← Automated code review with progressive severity thresholds
    │  ← Up to 2 fix loops before failing
    │
    ▼
Orchestrator commits and pushes to feature branch
    │
    ▼
Orchestrator creates DRAFT pull request
    │  ← Slack notification with retry/refine buttons
    │  ← Jira comment with PR link
    │
    ▼
>>> HUMAN REVIEW REQUIRED <<<
    │
    ▼
Human reviews, approves, and merges PR
    │
    ▼
Standard CI/CD pipeline deploys (external to orchestrator)
```

---

## 4. Decision Reasoning & Audit Trail

### Decision Logging

| Decision Point | What Is Logged | Storage |
|---------------|----------------|---------|
| Epic routing | `epic_routing_reason` in state (e.g., "no active epics found for team") | Execution log |
| Epic correction | `EpicCorrectionDecision.reason` — whether and why epic was updated | Execution log |
| Code review severity | Review issues with severity levels and blocking thresholds | State + PR body |
| Fix loop routing | Whether to retry, fail, or proceed — based on loop count and severity | Execution log |
| Pipeline failure | `failure_state` message + `failure_diagnostic` architect analysis | State + draft PR body |

### Execution Logs

Every pipeline run produces a structured log file at:
```
~/.bmad/logs/run_{thread_id}_{timestamp}.md
```

This file contains:
- **Console output** — full structlog trace of every operation
- **Structured timeline** — per-node execution entries with timestamps
- **Agent tool traces** — every tool invocation with parameters and results
- **Token usage report** — input/output tokens and cost per agent session
- **Thinking blocks** — model reasoning captured as "agent_block" entries

### Intervention Mechanisms

| Mechanism | How It Works |
|-----------|-------------|
| **Dry-run mode** | `--dry-run` flag prevents all mutations (Jira, Git, GitHub, Slack). Logs what *would* happen. |
| **Skip nodes** | `--skip-nodes node1,node2` skips specific pipeline stages |
| **Execution timeout** | Configurable timeout (default 30 min) auto-saves checkpoint on expiry |
| **Resume** | `--resume` continues from last checkpoint with optional `--guidance` |
| **Retry** | `/bmad retry [guidance]` on PR comment restarts from code review with human guidance |
| **Max loops** | `--max-loops N` caps review/fix iterations before forcing failure |

---

## 5. Accountability Chain

### Responsibility Matrix

| Stage | Responsible Party | Accountability |
|-------|------------------|---------------|
| **Pipeline trigger** | Engineer who dispatches workflow / adds label / runs CLI | Responsible for providing correct inputs and target repository |
| **Generated code** | BMAD Orchestrator (AI system) | Produces code, tests, and review — all outputs labeled as AI-generated |
| **Code review (automated)** | BMAD Orchestrator (AI system) | Automated severity-based review; does not replace human review |
| **PR review & approval** | Reviewing engineer(s) | Responsible for verifying correctness, security, and compliance of AI-generated code |
| **PR merge** | Merging engineer | Accepts ownership of the code entering the codebase |
| **Post-merge bugs** | Team that owns the affected service/component | Standard ownership model — the merging engineer and team own remediation |
| **Security vulnerabilities** | Security team + merging engineer | Merging engineer is accountable for reviewing AI output for vulnerabilities |

### Key Principles

1. **The human who merges accepts responsibility.** AI-generated code is a draft proposal. Merging it is an explicit human decision that transfers ownership to the team.
2. **AI does not deploy.** The orchestrator's scope ends at PR creation. CI/CD and deployment are external systems with their own approval gates.
3. **Traceability is maintained.** Every AI-generated commit carries the `[BMAD-ORCHESTRATED]` tag, the `BMAD Orchestrator` git author, and a `Co-Authored-By` trailer. PRs carry the `🤖 Generated by BMAD` footer. GitHub issues carry the `bmad-orchestrated` label.
4. **Remediation follows standard process.** Bugs in AI-generated code are fixed through normal engineering workflows (new PR, review, merge).

---

## 6. AI Transparency & Labeling

### Output Labeling

| Output Type | Label | Mechanism |
|-------------|-------|-----------|
| **Git commits** | `[BMAD-ORCHESTRATED]` in subject line | Commit message template in `commit_and_push.py` |
| **Git commits** | `BMAD Orchestrator <bmad@noreply.local>` as author | Git author identity via `GitService` |
| **Git commits** | `Co-Authored-By: BMAD Orchestrator <bmad@noreply.local>` trailer | Commit message template |
| **Pull requests** | "*Generated by BMAD Autonomous Engineering Orchestrator* 🤖" footer | PR body template in `create_pull_request.py` |
| **Pull requests** | Created as **draft** by default | `Settings.draft_pr` / failure state |
| **Pull requests** | Hidden HTML metadata (`bmad:target_repo`, `bmad:prompt`, `bmad:team_id`) | PR body template |
| **GitHub issues** | "*Created by BMAD Autonomous Engineering Orchestrator* 🤖" footer | Issue body template in `create_github_issue.py` |
| **GitHub issues** | `bmad-orchestrated` label | Automatically applied label |
| **Jira comments** | Emoji-prefixed status updates (🚀, ✅) | Step notification system in `graph.py` |
| **Slack messages** | Posted under bot identity | Slack bot token authentication |

### EU AI Act Transparency Compliance

Per Article 50 of the EU AI Act, persons interacting with AI-generated content must be informed. This system addresses the requirement through:

1. **Commit attribution** — Git author and `Co-Authored-By` trailer clearly identify AI origin
2. **PR labeling** — Footer text and draft status signal AI-generated content to reviewers
3. **Issue labeling** — GitHub label `bmad-orchestrated` and footer text identify AI origin
4. **Slack bot identity** — Messages are posted from a bot account, not impersonating a human
5. **Jira comments** — Posted programmatically with emoji markers distinguishing from human comments

---

## 7. Internal AI Inventory Entry

| Field | Value |
|-------|-------|
| **System Name** | BMAD Autonomous Engineering Orchestrator |
| **Purpose** | Automates engineering workflow: Jira planning → code generation → QA → code review → PR creation |
| **AI Provider** | Anthropic (Claude API + Claude Agent SDK) |
| **Models Used** | Claude Opus 4.6 (configurable per agent role) |
| **Data Processed** | Source code, Jira project metadata, GitHub repository metadata |
| **PII Processed** | None |
| **Risk Category** | Limited / Minimal Risk |
| **Human Oversight** | Required — all code delivered as draft PR requiring human merge |
| **Deployment** | Internal tool — GitHub Actions, CLI, Slack bot |
| **Data Retention** | Execution logs stored locally at `~/.bmad/logs/`. No data sent to external systems beyond Anthropic API, Jira, GitHub, and Slack. |
| **Responsible Team** | Engineering Platform / DevEx |
| **Review Frequency** | Reassess on scope changes or when agent capabilities are expanded |
