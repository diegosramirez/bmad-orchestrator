# BMAD Orchestrator: Legal and Compliance Use-Case Documentation

## 1) Purpose and scope

This document describes how `bmad-orchestrator` is used, what the AI-assisted workflow can do, where humans can intervene, and which controls apply before any change reaches production-facing code paths.

Scope covered here:
- AI-assisted software delivery orchestration
- Integrations through GitHub Actions, Jira Automation, and Slack App
- Controls for code changes, workflow actions, and user-facing communication

Out of scope:
- Autonomous production deployment without human approval
- Direct financial transaction execution
- Any safety-critical autonomous decision-making

## 2) AI system classification rationale (working assessment)

Current working assessment: internal developer-assistance/orchestration use case, expected to be **limited-risk or minimal-risk** under normal operation, subject to final legal review.

Reasoning:
- Primary function is developer workflow support, not direct end-user profiling, eligibility decisions, or other high-risk AI Act categories.
- Outputs are intended for internal engineering operations and are reviewable by humans before merge/deploy.
- System behavior is constrained by integration permissions and process gates, not unconstrained autonomous execution.

Reassessment triggers:
- New access to personal data at scale, payment systems, or security-sensitive production controls
- Any change that enables autonomous merge/deploy or high-impact Jira transitions without human validation
- New use case involving legal or similarly high-impact decisions

## 3) What the tool can access

The orchestrator accesses only what is granted by configured credentials and integration scopes.

### GitHub Actions interface
- Repository metadata, workflow context, pull request/commit state
- CI status, logs, and artifacts (as permitted)
- Branch and PR operations permitted by token scope

### Jira Automation interface
- Issue fields, statuses, comments, labels, and workflow transitions (scope-dependent)
- Project-level permissions defined in Jira role configuration

### Slack App interface
- Channel messages/events where installed and authorized
- Ability to post bot/user-visible messages in allowed channels

### Data handling boundary
- Access is integration-scope based, not global organization-wide by default.
- No implicit right to access systems outside granted API scopes.

## 4) What the tool can modify

### Allowed modification types (controlled)
- Drafting code suggestions or creating/updating PR content
- Posting or updating workflow status messages (Slack/Jira)
- Performing permitted low-risk automations (for example, non-destructive status synchronization)

### Prohibited or restricted without explicit human action
- Direct merge into protected branches
- Production deployment actions
- High-impact Jira changes (for example, approvals/sign-offs, incident closure, release-go decisions)
- Security policy exceptions or permission escalation

## 5) Human oversight and intervention points

Human intervention is available at multiple points and is mandatory for high-impact actions.

### A. GitHub Actions checkpoints
- Branch protection rules enforce reviewer approval before merge.
- Required checks must pass before merge is permitted.
- Maintainer or designated reviewer must explicitly approve PR.
- Optional: CODEOWNERS review for sensitive paths.

### B. Jira Automation checkpoints
- AI-initiated changes are limited to pre-approved automation classes.
- Any transition beyond routine status updates requires explicit human validation/approval.
- Final accountable role for issue lifecycle remains assigned human owner (for example, assignee/release manager).

### C. Slack App checkpoints and transparency
- AI-generated messages are labeled as AI-generated (or posted from clearly AI-identified bot identity).
- Slack notifications are informational; they do not replace formal approvals in GitHub/Jira.
- Human operators can interrupt, override, or request correction through normal operational channels.

## 6) Approval gates before production-impacting branches

Minimum required gates before code reaches a branch that can feed production:
- At least one qualified human reviewer approval
- All required CI/security checks green
- Protected-branch policy enforcement active
- Merge performed by authorized human or policy-controlled merge action after approvals are satisfied

No AI-only path to production:
- AI output may propose or prepare changes.
- Human approval remains required for merge and release progression.

## 7) Responsibility and accountability chain

Responsibility model:
- **System owners (engineering/platform):** maintain configuration, permissions, monitoring, and control design.
- **Code reviewers/maintainers:** accept or reject AI-proposed code changes.
- **Issue owners (Jira):** remain accountable for non-trivial workflow decisions and business impact.
- **Security/compliance stakeholders:** define control requirements, perform periodic control verification.

Defect/vulnerability handling:
- Any bug or vulnerability introduced through AI-assisted output is handled under normal incident and remediation ownership.
- Accountability follows the approving/owning human roles and established engineering governance, not the AI tool itself.

## 8) Transparency and documentation obligations

To support legal and auditability expectations:
- Maintain this use-case record in internal AI inventory.
- Keep AI-generated communication labeled in Slack or equivalent channels.
- Record key decision points through existing systems of record (PR reviews, Jira history, CI logs).
- Keep integration scopes and permission grants documented and periodically reviewed.

## 9) Operational controls checklist

- [ ] Protected branches enabled for production-relevant branches
- [ ] Mandatory PR review and required checks configured
- [ ] Jira automations restricted to approved action classes
- [ ] Human approval step enforced for non-routine Jira transitions
- [ ] Slack AI output labeling enabled
- [ ] Integration tokens scoped to least privilege
- [ ] Ownership matrix documented (system owner, reviewer roles, incident owner)
- [ ] Periodic access/control review scheduled

## 10) Residual risk statement

Residual risk remains from:
- Incorrect or insecure AI-generated suggestions accepted by humans
- Misconfigured permissions or automation scopes
- Over-reliance on informational Slack outputs without formal gate checks

Primary mitigations are human approval gates, branch protection, least-privilege access, and auditable workflow records.
