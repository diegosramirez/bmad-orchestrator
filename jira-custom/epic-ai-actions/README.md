# epic-ai-actions (Jira issue panel)

Forge UI Kit app: **AI Actions** panel on Jira issues (including Epics). **Run Discovery** dispatches the BMAD orchestrator in *Discovery* mode (epic-only: `check_epic_state` + `create_or_correct_epic`) via your self-hosted FastAPI webhook, which triggers GitHub Actions.

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
| `BMAD_DISCOVERY_WEBHOOK_SECRET` | Shared secret; must match the Forge variable below |

Discovery endpoint: `POST /bmad/discovery-run` with header `X-BMAD-Discovery-Secret` and JSON body `{"issue_key":"PROJ-123"}`.

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
forge variables set --environment development BMAD_DISCOVERY_WEBHOOK_URL 'https://your-host'
forge variables set --environment development BMAD_DISCOVERY_WEBHOOK_SECRET 'same-secret-as-BMAD_DISCOVERY_WEBHOOK_SECRET'
```

- `BMAD_DISCOVERY_WEBHOOK_URL` — same origin as in the manifest (no trailing slash, no `/bmad/discovery-run` path; the resolver appends that path).
- `BMAD_DISCOVERY_WEBHOOK_SECRET` — must match `BMAD_DISCOVERY_WEBHOOK_SECRET` on the server.

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

- **Run Discovery** — confirms, then calls the webhook to dispatch GitHub Actions Discovery run for the **current issue key** (works on Epic issue view).
- **Design Architect** / **Generate Stories** — not wired in this version (informational message after confirm).

## Support

See [Forge documentation](https://developer.atlassian.com/platform/forge/) and the main BMAD orchestrator repo for pipeline details.
