# BMAD Slack + Jira workers (Vercel)

Serverless functions for **Slack** slash commands / interactivity and **Jira** webhooks. Everything here is **TypeScript** only; deploy with Vercel (`vercel deploy` or connect the repo). Shared Jira helpers live in `lib/jira-webhooks.ts` (outside `api/` so Vercel bundles them with Node ESM).

## Endpoints

| Path | Purpose |
|------|---------|
| `/api/slack` | Slack signing secret + slash commands / interactive payloads |
| `/api/jira-issue` | Jira **issue** webhooks → dispatches `bmad-start-run.yml` when a story has a parent epic |
| `/api/jira-comment` | Jira **comment** webhooks → `/bmad retry\|refine` commands |
| `/api/workflow-discovery-run` | Forge / panel: **Discovery** only (`execution_mode`: `discovery`) |
| `/api/workflow-architect-run` | Forge: **Epic Architect** only (`epic_architect`) |
| `/api/workflow-stories-run` | Forge: **Stories** breakdown + party (`stories_breakdown`) |
| `/api/workflow-dev-run` | Forge: **Dev** pipeline on a Story (`inline`) |

All Forge routes expect **POST** JSON: `{"issue_key":"PROJ-123","target_repo":"optional/override","team_id":"optional"}`. They require **`BMAD_FORGE_WEBHOOK_SECRET` or `BMAD_DISCOVERY_WEBHOOK_SECRET`** to be set (otherwise **503**).

Legacy-style paths (rewrites in `vercel.json`):

| Rewrite source | Destination |
|----------------|-------------|
| `/bmad/jira-webhook` | `/api/jira-issue` |
| `/bmad/jira-comment-webhook` | `/api/jira-comment` |
| `/workflow/discovery-run` | `/api/workflow-discovery-run` |
| `/workflow/architect-run` | `/api/workflow-architect-run` |
| `/workflow/stories-run` | `/api/workflow-stories-run` |
| `/workflow/dev-run` | `/api/workflow-dev-run` |

Legacy **`/bmad/discovery-run`**, **`/bmad/architect-run`**, **`/bmad/stories-run`**, **`/bmad/dev-run`** rewrites point to the same handlers (Forge UI in `jira-custom` may still use those paths).

## Environment variables

### Shared (Slack + Jira where applicable)

| Variable | Description |
|----------|-------------|
| `SLACK_SIGNING_SECRET` | Slack app signing secret (required for `/api/slack`) |
| `SLACK_BOT_TOKEN` | Bot token for Slack API (required for `/api/slack`) |

### Jira webhooks + GitHub dispatch

| Variable | Description |
|----------|-------------|
| `BMAD_GITHUB_REPO` | Orchestrator repo `owner/name` (workflow lives here) |
| `BMAD_GITHUB_TOKEN` | GitHub token with `workflow` scope for dispatch; `actions:read` helps duplicate-run detection |
| `BMAD_GITHUB_BASE_BRANCH` | Ref for `workflow_dispatch` (default `main`) |
| `BMAD_GITHUB_OWNER` | Used to normalize target repo when Jira only has a repo slug |
| `DEFAULT_TARGET_REPO` | Fallback `owner/repo` for the app under development |
| `DEFAULT_TEAM_ID` | Fallback team id when it cannot be inferred from the issue key |
| `BMAD_JIRA_WEBHOOK_SECRET` | Optional. If set, every Jira webhook request must send header `X-BMAD-Jira-Secret` with the same value |
| `BMAD_FORGE_WEBHOOK_SECRET` | Set this or `BMAD_DISCOVERY_WEBHOOK_SECRET` for Forge routes (`/api/workflow-*-run`); same as Python orchestrator |
| `BMAD_DISCOVERY_WEBHOOK_SECRET` | Alternative Forge secret (either this or `BMAD_FORGE_WEBHOOK_SECRET`) |
| `JIRA_TARGET_REPO_CUSTOM_FIELD_ID` | Default `customfield_10112` |
| `JIRA_BRANCH_CUSTOM_FIELD_ID` | Default `customfield_10145` (BMAD Branch; required for comment retry/refine) |

## Jira configuration

1. **Issue webhook** — URL: `https://<your-deployment>/api/jira-issue` (or rewrite URL above). Subscribe to the issue events you need (e.g. issue updated) so the payload includes `issue.fields.parent` for stories under an epic.
2. **Comment webhook** — URL: `https://<your-deployment>/api/jira-comment`. Subscribe to comment created (or updated, as needed).

Comments must use `/bmad retry "..."` or `/bmad refine "..."` per your BMAD docs.

## Local development

```bash
cd slack-worker
npm install
vercel dev
```

Use `curl` to POST sample Jira JSON bodies to `http://localhost:3000/api/jira-issue` and `/api/jira-comment`.

Payloads are **not** written to disk on Vercel (responses include `persisted: false`).
