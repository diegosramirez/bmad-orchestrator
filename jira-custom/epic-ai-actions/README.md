# epic-ai-actions (Jira issue panel)

Forge UI Kit app: issue panels on Jira (Epic actions, Story development, comment helpers). Dispatches the BMAD orchestrator via the **slack-worker** deployment (Vercel: `slack-worker/` in this repo), which triggers GitHub Actions.

| Panel | Scope | What it does |
|-------|--------|----------------|
| **BMAD Epic** | Epic issues | Run Discovery, Design Architect, Generate Stories |
| **BMAD Story** | Story issues | Full dev pipeline (detect → code → QA → review → E2E → commit → PR), skipping epic/story prep |
| **AI Comments** | Story issues | Post `/bmad refine` or `/bmad retry` comments |

| Button (Epic panel) | Orchestrator mode | Workflow |
|---------------------|-------------------|----------|
| **Run Discovery** | `discovery` | `check_epic_state` + `create_or_correct_epic`, then END |
| **Design Architect** | `epic_architect` | `epic_architect` only (appends `# Architecture` to the Epic description), then END |
| **Generate Stories** | `stories_breakdown` | `create_story_tasks` + `party_mode_refinement`, then END |

## Requirements

- [Forge CLI](https://developer.atlassian.com/platform/forge/set-up-forge/) and an Atlassian developer account
- A **public HTTPS** origin for the **slack-worker** Vercel deployment (same value you set as `BMAD_FORGE_WEBHOOK_URL` in Forge)

## Configure the BMAD slack-worker (Vercel)

On the Vercel project for `slack-worker/`, set the same variables you would have used for the old Python webhook (see `slack-worker/README.md` in this repo). Typical entries:

| Variable | Purpose |
|----------|---------|
| `BMAD_GITHUB_REPO` | Repo that contains `.github/workflows/bmad-start-run.yml` |
| `BMAD_GITHUB_TOKEN` | PAT with `workflow` scope (dispatch) and read access to Actions (list workflow runs; avoids duplicate dispatches for the same Jira issue from the Forge panel) |
| `BMAD_GITHUB_BASE_BRANCH` | Branch of **bmad-orchestrator** used as `workflow_dispatch` `ref` |
| `DEFAULT_TARGET_REPO` | Fallback `owner/repo` when the issue has no target-repo custom field or the Forge resolver cannot read it |
| `BMAD_FORGE_WEBHOOK_SECRET` | Shared secret for Forge (preferred) |
| `BMAD_DISCOVERY_WEBHOOK_SECRET` | Legacy fallback if `BMAD_FORGE_WEBHOOK_SECRET` is unset |

Endpoints (unchanged paths; served by Vercel, not `webhook_server.py`):

- Discovery: `POST /bmad/discovery-run` — JSON `{"issue_key":"PROJ-123","target_repo":"optional"}` (the Forge resolver reads the target-repo field, default `customfield_10112`, and sends `target_repo` when set)
- Epic Architect: `POST /bmad/architect-run` — same shape
- Stories: `POST /bmad/stories-run` — same shape
- Story development: `POST /bmad/dev-run` — same shape (Story key as `issue_key`; `execution_mode` `inline` with epic/story-creation nodes skipped)

Header (all endpoints): `X-BMAD-Forge-Secret` with the same secret value as on the worker.

**Duplicate run guard:** Before dispatching, the worker checks GitHub for an active `bmad-start-run.yml` run for the current `issue_key`. It matches `inputs.prompt` when the GitHub API returns workflow inputs; otherwise it matches the run’s **`display_title`** (the workflow sets `run-name` to `BMAD Orchestrator {prompt} — {execution_mode} — Start Run`, so the Jira key appears in the title). If a match exists, the endpoint returns **409** with `code: "run_in_progress"` and does not start another run. The Forge panel shows an informational banner (not an error).

## Configure this Forge app

### 1. Egress (manifest)

Edit [`manifest.yml`](manifest.yml) under `permissions.external.fetch.backend` and replace the placeholder with the **origin only** of your slack-worker deployment (scheme + host, no path). Example: `https://your-app.vercel.app`.

Redeploy after any change:

```bash
forge deploy --non-interactive --environment development
```

The app declares `read:jira-work` so the resolver can read the target-repo field on the current issue. After adding or changing scopes, run **`forge install --upgrade`** (see below) so Jira prompts for the new permission.

### 2. Environment variables (resolver)

Set variables for the environment you use (e.g. development):

```bash
forge variables set --environment development BMAD_FORGE_WEBHOOK_URL 'https://your-host'
forge variables set --environment development BMAD_FORGE_WEBHOOK_SECRET 'your-shared-secret'
# Optional — if your Jira site uses different custom field IDs than the BMAD defaults:
# forge variables set --environment development BMAD_JIRA_TARGET_REPO_CUSTOM_FIELD_ID 'customfield_10112'
# forge variables set --environment development BMAD_JIRA_BRANCH_CUSTOM_FIELD_ID 'customfield_10145'
```

You may keep using `BMAD_DISCOVERY_WEBHOOK_URL` and `BMAD_DISCOVERY_WEBHOOK_SECRET` instead; the resolver accepts either name (see `src/resolvers/index.js`).

- URL: origin only (no trailing slash, no path; resolvers append `/bmad/discovery-run`, `/bmad/architect-run`, `/bmad/stories-run`, or `/bmad/dev-run`).
- Secret: must match `BMAD_FORGE_WEBHOOK_SECRET` or `BMAD_DISCOVERY_WEBHOOK_SECRET` on the Vercel project.
- Target-repo / branch field IDs: optional `BMAD_JIRA_TARGET_REPO_CUSTOM_FIELD_ID` and `BMAD_JIRA_BRANCH_CUSTOM_FIELD_ID` (same names as the Python orchestrator `.env`); defaults match `customfield_10112` and `customfield_10145`.

After changing variables or permissions, redeploy and reinstall if prompted:

```bash
forge install --non-interactive --upgrade --site <your-site> --product jira --environment development
```

### 3. Local development

```bash
forge tunnel
```

Tunnel hot-reloads UI/resolver changes; manifest changes still require redeploy.

## UI behaviour

- **BMAD Epic** — Discovery, Design Architect, and Generate Stories (each confirms before dispatch) when the issue is an Epic.
- **BMAD Story** — confirms, then dispatches the full dev pipeline for the current Story key when the issue is a Story.
- **AI Comments** — shortcuts to post `/bmad refine` or `/bmad retry` on Story issues.

## Support

See [Forge documentation](https://developer.atlassian.com/platform/forge/) and the main BMAD orchestrator repo for pipeline details.
