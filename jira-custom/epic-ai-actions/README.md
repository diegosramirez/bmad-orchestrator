# epic-ai-actions (Jira issue panel)

Forge UI Kit app: **AI Actions** panel on Jira issues (including Epics). Dispatches the BMAD orchestrator via your self-hosted FastAPI webhook, which triggers GitHub Actions.

| Button | Orchestrator mode | Workflow |
|--------|-------------------|----------|
| **Run Discovery** | `discovery` | `check_epic_state` + `create_or_correct_epic`, then END |
| **Design Architect** | `epic_architect` | `epic_architect` only (appends `## Epic Architect` to the Epic description), then END |

## Requirements

- [Forge CLI](https://developer.atlassian.com/platform/forge/set-up-forge/) and an Atlassian developer account
- A **public HTTPS** URL for the BMAD webhook server (e.g. reverse proxy or tunnel in development)

## Configure the BMAD webhook server

On the machine running `webhook_server.py`, set:

| Variable | Purpose |
|----------|---------|
| `BMAD_GITHUB_REPO` | Repo that contains `.github/workflows/bmad-start-run.yml` |
| `BMAD_GITHUB_TOKEN` | PAT with `workflow` scope (dispatch workflows) |
| `BMAD_GITHUB_BASE_BRANCH` | Branch of **bmad-orchestrator** used as `workflow_dispatch` `ref` |
| `DEFAULT_TARGET_REPO` | Default `owner/repo` to clone for the run (if Forge does not send `target_repo`) |
| `BMAD_FORGE_WEBHOOK_SECRET` | Shared secret for Forge (preferred) |
| `BMAD_DISCOVERY_WEBHOOK_SECRET` | Legacy fallback if `BMAD_FORGE_WEBHOOK_SECRET` is unset |

Endpoints:

- Discovery: `POST /bmad/discovery-run` — JSON `{"issue_key":"PROJ-123"}`
- Epic Architect: `POST /bmad/architect-run` — same body

Header (both endpoints): `X-BMAD-Forge-Secret` with the same secret value as on the server.

## Configure this Forge app

### 1. Egress (manifest)

Edit [`manifest.yml`](manifest.yml) under `permissions.external.fetch.backend` and replace `https://webhook.example.com` with the **origin only** of your FastAPI server (scheme + host, no path). Example: `https://bmad-hooks.mycompany.com`.

Redeploy after any change:

```bash
forge deploy --non-interactive --environment development
```

### 2. Environment variables (resolver)

Set variables for the environment you use (e.g. development):

```bash
forge variables set --environment development BMAD_FORGE_WEBHOOK_URL 'https://your-host'
forge variables set --environment development BMAD_FORGE_WEBHOOK_SECRET 'your-shared-secret'
```

You may keep using `BMAD_DISCOVERY_WEBHOOK_URL` and `BMAD_DISCOVERY_WEBHOOK_SECRET` instead; the resolver accepts either name (see `src/resolvers/index.js`).

- URL: origin only (no trailing slash, no path; resolvers append `/bmad/discovery-run` or `/bmad/architect-run`).
- Secret: must match `BMAD_FORGE_WEBHOOK_SECRET` or `BMAD_DISCOVERY_WEBHOOK_SECRET` on the server.

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

- **Run Discovery** — confirms, then dispatches Discovery for the current issue key (Epic view).
- **Design Architect** — confirms, then dispatches Epic Architect (requires prior Discovery: `<!-- bmad:discovery -->` in the Epic description).
- **Generate Stories** — not wired in this version (informational message after confirm).

## Support

See [Forge documentation](https://developer.atlassian.com/platform/forge/) and the main BMAD orchestrator repo for pipeline details.
