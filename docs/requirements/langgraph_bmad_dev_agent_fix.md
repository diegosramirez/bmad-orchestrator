# Making a LangGraph + BMAD + Claude Code Dev Agent Work Correctly in an Existing Repo

## Problem

When running the workflow on an existing project, the Dev agent:

-   Doesn't understand the existing codebase
-   Doesn't try to build the app
-   Doesn't run unit tests
-   Doesn't run linting
-   Doesn't properly fix failures

This happens because the agent does not automatically receive repository
context and is not forced to execute build/test obligations.

------------------------------------------------------------------------

# Solution Architecture

## 1️⃣ Add a First-Class Node: RepoContextScan (Mandatory)

Before any implementation node runs, force a repository scan that
produces a **Repo Context Packet** and stores it in state.

### What to Collect

-   Repository tree (top 3--4 levels)
-   Detected stack (Node, .NET, Python, monorepo, etc.)
-   Build/test/lint commands (from package.json, Makefile, dotnet sln,
    pyproject, etc.)
-   Test locations and conventions
-   CI configuration hints (.github/workflows, azure-pipelines, etc.)
-   Entry points and important folders

### Store in State

-   `repo_summary`
-   `build_commands`
-   `test_commands`
-   `lint_commands`
-   `format_commands`
-   `workspaces` (if monorepo)
-   `constraints` (Node version, SDK, etc.)

This removes guessing and makes the system deterministic.

------------------------------------------------------------------------

## 2️⃣ Add Node: DetermineExecutionPlan

Translate the repo context into explicit execution obligations.

### Example State

-   `execution_plan.preflight[]`
-   `execution_plan.build[]`
-   `execution_plan.test[]`
-   `execution_plan.lint[]`
-   `execution_plan.checks_required = ["build","test","lint"]`

The workflow decides what must run --- not the model.

------------------------------------------------------------------------

## 3️⃣ Force Tool-Based Execution (Claude Code)

The Dev node should not just "write code".

It must:

-   Execute required commands
-   Capture outputs
-   Report pass/fail status
-   If failed → fix until green

### Dev Node Contract

Input: - Story/task - Acceptance criteria - Repo context packet -
Execution plan

Output: - Commands executed - Logs - Pass/fail status - Fix attempts if
needed

The node's real responsibility becomes:

> "Make the repo green."

------------------------------------------------------------------------

## 4️⃣ Add Hard Quality Gate: VerifyGreen

After implementation:

-   Build must pass
-   Unit tests must pass
-   Lint must pass (or explicitly waived)

If any fail → transition to `FixBuildFailures` loop.

LangGraph enforces deterministic progression.

------------------------------------------------------------------------

## 5️⃣ Proper Context Injection

Every Dev prompt must include:

1.  Repo Context Packet (summary + commands)
2.  Work area scope
3.  Execution obligations
4.  Acceptance criteria
5.  "Investigate before guessing" rule

Example obligation instruction:

> You MUST run the commands listed in execution_plan. Do not claim
> success unless they pass. If they fail, capture the error and fix
> until green.

This dramatically changes agent behavior.

------------------------------------------------------------------------

## 6️⃣ Common Failure Causes

### A) Agent doesn't know what to run

Fix: Extract canonical commands from config files.

### B) Monorepo ambiguity

Fix: Detect project name and use correct workspace-specific commands.

### C) Tooling mismatch (Node/Python/.NET version)

Fix: Detect .nvmrc, global.json, etc., and add preflight setup.

### D) No quality gate

Fix: Block graph progression unless checks pass.

------------------------------------------------------------------------

## 7️⃣ Minimal MVP Fix (If You Only Do One Thing)

Insert these three nodes:

1.  `RepoContextScan`
2.  `DeriveCommandsFromRepo`
3.  `VerifyGreen` (with fix loop)

This usually solves the "AI doesn't behave like a real developer" issue.

------------------------------------------------------------------------

# Suggested State Shape

    repo_context: {
      summary,
      packages,
      detected_tools,
      commands
    }

    execution_plan: {
      preflight[],
      build[],
      test[],
      lint[]
    }

    checks: {
      build_passed,
      tests_passed,
      lint_passed,
      logs
    }

------------------------------------------------------------------------

# Core Principle

Your Dev agent should not be a code generator.

It should be a deterministic build/test/lint execution unit operating
under explicit workflow control.

LangGraph handles orchestration. BMAD handles thinking. Claude Code
handles execution. Quality gates enforce safety.
