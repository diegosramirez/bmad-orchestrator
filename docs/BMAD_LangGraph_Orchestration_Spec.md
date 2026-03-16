# BMAD LangGraph Orchestration System

## Objective

Build a command-line Python application using **LangGraph** that
automates the BMAD workflow end-to-end.

### Input

-   `team_id`
-   `prompt`

### Output

-   Updated BMAD artifacts (epics/stories/tasks)
-   Code implementation
-   QA automation
-   Code review fixes resolved
-   Committed branch
-   GitHub PR created with summary

------------------------------------------------------------------------

## Core System Requirements

This system must:

-   Be deterministic in structure
-   Be resumable
-   Be safe to re-run
-   Enforce quality gates before advancing

> This is not just chaining prompts. This is workflow orchestration with
> state.

------------------------------------------------------------------------

# 1. High-Level Architecture

Think in terms of **stateful graph orchestration**, not linear
scripting.

### Required Components

-   LangGraph for workflow graph
-   Structured state object (TypedDict)
-   Explicit node transitions
-   Tool abstractions for BMAD commands
-   GitHub CLI wrapper service
-   Git abstraction layer

------------------------------------------------------------------------

## Core Components

### CLI Entrypoint

-   Accepts `team_id` + `prompt`
-   Creates execution thread (LangGraph session)
-   Initializes state

### State Model (Critical)

Must track:

-   `team_id`
-   `input_prompt`
-   `current_epic_id`
-   `current_story_id`
-   `new_story_created` (bool)
-   `branch_name`
-   `code_review_issues` (list)
-   `qa_results`
-   `commit_sha`
-   `pr_url`
-   `execution_log`
-   `failure_state`

This prevents hallucinated transitions and enables resuming.

------------------------------------------------------------------------

# 2. Execution Flow as a Graph

Implement as a graph with conditional edges --- NOT a linear script.

    START
      ↓
    CheckEpicState
      ↓
    CreateOrCorrectEpic
      ↓
    CreateStoryTasks
      ↓
    PartyModeRefinement
      ↓
    DevStory
      ↓
    QAAutomation
      ↓
    CodeReview
      ↳ If issues → DevStoryFixLoop
      ↓
    CommitAndPush
      ↓
    CreatePullRequest
      ↓
    END

Key intelligence lives in branching and looping.

------------------------------------------------------------------------

# 3. Detailed Phase Guidance

## 3.1 Epic Determination

**Node:** `CheckEpicState`

### Logic

-   Query BMAD for active epic by team prefix
-   If none → create new epic
-   If one exists → evaluate prompt relevance

### Structured Decision Output

``` json
{
  "decision": "add_to_existing" | "create_new",
  "reason": "..."
}
```

Avoid free-form responses.

------------------------------------------------------------------------

## 3.2 Epic Creation / Course Correction

### If New Epic

-   Run `bmad-create-epics-and-stories`
-   Ensure prefix matches `team_id`
-   Capture `epic_id`

### If Existing

-   Run `bmad-correct-course`
-   Add story only if appropriate
-   Otherwise create new epic

**Rule:** Never silently mutate an epic without tracking in state.

------------------------------------------------------------------------

## 3.3 Story Creation

Run `/bmad-create-story`.

Must produce: - Clear acceptance criteria - Defined tasks -
Dependencies - QA scope - Definition of done

Enforce validation. If vague → refinement loop (quality gate).

------------------------------------------------------------------------

## 3.4 Party Mode (Multi-Agent Refinement)

### Agents

-   Designer
-   Architect
-   Developer

Each outputs structured: - concerns - improvements - risks

Aggregator merges into: - improved story - updated tasks - clarified
acceptance criteria

Max 1--2 iterations. No open-ended loops.

------------------------------------------------------------------------

## 3.5 Development Phase

Run `/bmad-dev-story`.

Constraints: - All tasks completed - Code compiles - Tests pass

Capture: - File diffs - Changed files list

Block advancement on: - Lint errors - Build failures - Test failures

------------------------------------------------------------------------

## 3.6 QA Automation

Run `/bmad-qa-automate`.

Requirements: - New tests exist - Coverage does not decrease - Edge
cases included

Store test summary in state.

------------------------------------------------------------------------

## 3.7 Code Review Phase

Run `/bmad-code-review`.

### Structured Output

``` json
{
  "issues": [
    {
      "severity": "low|medium|high|critical",
      "description": "...",
      "file": "...",
      "fix_required": true
    }
  ]
}
```

### Fix Loop Rules

-   If severity ≥ medium → enter fix loop
-   Re-run review after fixes
-   Max 3 loops
-   After 3 failures → set `failure_state`

Prevents infinite patch spirals.

------------------------------------------------------------------------

## 3.8 Commit & Push

Branch format:

    bmad/{team_id}/{story_id}-{slug}

Commit message:

    feat(team_id): implement story {story_id}

    Summary:
    - ...
    - ...

    Artifacts:
    - epic updated
    - story updated
    - qa added

Then: - `git push origin branch` - Capture branch name + commit SHA

------------------------------------------------------------------------

## 3.9 Pull Request Creation

Use GitHub CLI:

    gh pr create --title ...
                 --body ...
                 --base main
                 --head branch

PR body must include: - Story summary - Acceptance criteria -
Implementation summary - QA additions - Code review resolution statement

Store PR URL in state.

------------------------------------------------------------------------

# 4. Engineering Best Practices

## Deterministic Interfaces

-   Structured input/output per node
-   No prose-only agent communication

## Observability

Log: - Prompt inputs - Agent outputs - State transitions - Tool calls

## Idempotency

Re-running must NOT: - Duplicate epics - Duplicate stories - Recreate
PRs

Use: - Epic IDs - Story IDs - Branch existence checks

## Failure Handling

-   Persist state after every node
-   Resume from last successful node
-   Use LangGraph checkpointing

## Rate Limiting & Cost Controls

-   Max iterations
-   Max tokens per agent
-   Hard timeout per execution

------------------------------------------------------------------------

# 5. Non-Functional Requirements

-   Python 3.11+
-   Fully typed (TypedDict state, Pydantic structured outputs)
-   90%+ unit test coverage (orchestration layer)
-   Dry-run mode
-   Configurable model provider
-   Secrets via environment variables
-   CI to test orchestration logic

------------------------------------------------------------------------

# 6. Major Risks

Potential failure points:

-   Hallucinated state transitions
-   Infinite correction loops
-   Silent quality regression
-   Git automation failure modes
    -   Detached HEAD
    -   Conflicting branches
    -   Dirty working directory
-   Prompt drift

------------------------------------------------------------------------

## Final Note

This system requires strict guardrails, deterministic state transitions,
and structured agent communication to operate safely and reliably.
