# webhook-worker

Inbound webhook gateway for BMAD. Receives Slack slash commands, Slack interactivity, Slack DM events, Jira issue/comment webhooks, and Forge panel dispatches — forwards them to the Python orchestrator by triggering GitHub Actions `workflow_dispatch`.

Deployed as a **container on Google Cloud Run**. The same image runs unchanged on any container host (GKE, ECS/Fargate, Fly.io, Render, plain Kubernetes).

Successor to `slack-worker/` (Vercel). Functionally identical — same routes, same env vars, same HMAC signature verification.

---

## Routes

| Path | Purpose |
|---|---|
| `/healthz` | Liveness probe |
| `/api/slack` | Slack slash commands + interactivity + Events API |
| `/bmad/jira-webhook` | Jira issue webhook |
| `/bmad/jira-comment-webhook` | Jira comment webhook (`/bmad retry|refine`) |
| `/workflow/discovery-run`, `/bmad/discovery-run` | Forge panel: Discovery |
| `/workflow/architect-run`, `/bmad/architect-run` | Forge panel: Epic Architect |
| `/workflow/stories-run`, `/bmad/stories-run` | Forge panel: Stories breakdown |
| `/workflow/dev-run`, `/bmad/dev-run` | Forge panel: Dev pipeline |

---

## Local development

```bash
# 1. Install
npm install

# 2. Configure env
cp .env.example .env
# → fill in SLACK_SIGNING_SECRET, SLACK_BOT_TOKEN, GITHUB_TOKEN, etc.

# 3. Run with hot-reload
npm run dev

# 4. Smoke-test
curl http://localhost:8080/healthz
# → {"ok":true}

# 5. Type-check / build
npm run typecheck
npm run build    # emits dist/
npm start        # runs dist/server.js
```

---

## Google Cloud deployment — full walkthrough

This section assumes **you have never used Google Cloud before**. It takes you from zero to a live HTTPS endpoint.

### Part 1 — Create a Google account (skip if you have one)

1. Go to <https://accounts.google.com/signup>.
2. Create a personal or work Google account. You can use a `@digistore24.com` email if your org allows — but Cloud Run billing is per-project, so a personal Google account is fine too.

### Part 2 — Activate Google Cloud & create a project

1. Visit <https://console.cloud.google.com/>. Accept the terms.
2. **Free trial**: new accounts get $300 in credits for 90 days. Click **Start free** when prompted. You must add a credit card — Google will not charge it during the trial.
3. Top navbar → project selector (says "Select a project") → **New Project**.
   - **Project name**: `bmad-webhook-worker` (or anything you like).
   - **Project ID**: Google auto-generates one (e.g. `bmad-webhook-worker-123456`). **Copy this ID** — you will use it everywhere. Call it `$PROJECT_ID` below.
   - Click **Create**. Wait ~30 seconds.
4. Make sure the new project is selected in the top-left project picker.

### Part 3 — Install & authenticate `gcloud`

`gcloud` is Google's CLI. You need it for deploying.

```bash
# macOS (Homebrew)
brew install --cask google-cloud-sdk

# Verify
gcloud --version

# Log in (opens a browser)
gcloud auth login

# Set your project as the default
gcloud config set project $PROJECT_ID

# Set the default region (pick one close to Slack/Jira/GitHub — e.g. europe-west1 for EU)
gcloud config set run/region europe-west1
```

> Tip: if you'd rather not install the CLI, Cloud Shell (<https://shell.cloud.google.com>) gives you a browser terminal with `gcloud` pre-installed. Everything below works there.

### Part 4 — Enable the required APIs

Cloud Run, Artifact Registry (container image storage), Cloud Build (image building), and Secret Manager must be enabled in your project.

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com
```

First enable takes ~1 minute. You'll see a "Operation finished" message per service.

### Part 5 — Create an Artifact Registry repo (one time)

This is where your container images live.

```bash
gcloud artifacts repositories create bmad \
  --repository-format=docker \
  --location=europe-west1 \
  --description="BMAD container images"
```

### Part 6 — Create secrets in Secret Manager

**Never bake secrets into the image.** Store them in Secret Manager, then mount them into Cloud Run as env vars.

```bash
cd /path/to/webhook-worker

# Create one secret per sensitive env var. Pipe the value in from stdin:
printf '%s' 'xoxb-your-token'              | gcloud secrets create SLACK_BOT_TOKEN             --data-file=-
printf '%s' 'your-slack-signing-secret'    | gcloud secrets create SLACK_SIGNING_SECRET        --data-file=-
printf '%s' 'ghp_your_github_token'        | gcloud secrets create GITHUB_TOKEN                --data-file=-
printf '%s' 'ghp_your_github_token'        | gcloud secrets create BMAD_GITHUB_TOKEN           --data-file=-
printf '%s' 'your-forge-webhook-secret'    | gcloud secrets create BMAD_FORGE_WEBHOOK_SECRET   --data-file=-
printf '%s' 'your-jira-webhook-secret'     | gcloud secrets create BMAD_JIRA_WEBHOOK_SECRET    --data-file=-   # optional; skip if you don't use it
```

To update a secret later (adds a new version):
```bash
printf '%s' 'new-value' | gcloud secrets versions add SLACK_BOT_TOKEN --data-file=-
```

### Part 7 — Build & push the container image

```bash
cd /path/to/webhook-worker

# Single command: Cloud Build packages source, builds the Dockerfile, and pushes to Artifact Registry.
gcloud builds submit \
  --tag europe-west1-docker.pkg.dev/$PROJECT_ID/bmad/webhook-worker:latest
```

First build takes ~3–5 minutes (uploading source + building). Subsequent builds are faster because layers are cached.

> Alternative if you have Docker locally: `docker build -t europe-west1-docker.pkg.dev/$PROJECT_ID/bmad/webhook-worker:latest .` then `gcloud auth configure-docker europe-west1-docker.pkg.dev` and `docker push …`.

### Part 8 — Deploy to Cloud Run

```bash
gcloud run deploy webhook-worker \
  --image europe-west1-docker.pkg.dev/$PROJECT_ID/bmad/webhook-worker:latest \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5 \
  --timeout 120s \
  --concurrency 80 \
  --set-env-vars "GITHUB_REPO=owner/repo,BMAD_GITHUB_REPO=owner/repo,BMAD_GITHUB_OWNER=owner,BMAD_GITHUB_BASE_BRANCH=main,DEFAULT_TARGET_REPO=owner/target,DEFAULT_TEAM_ID=SAM1,JIRA_TARGET_REPO_CUSTOM_FIELD_ID=customfield_10112,JIRA_BRANCH_CUSTOM_FIELD_ID=customfield_10145" \
  --set-secrets "SLACK_BOT_TOKEN=SLACK_BOT_TOKEN:latest,SLACK_SIGNING_SECRET=SLACK_SIGNING_SECRET:latest,GITHUB_TOKEN=GITHUB_TOKEN:latest,BMAD_GITHUB_TOKEN=BMAD_GITHUB_TOKEN:latest,BMAD_FORGE_WEBHOOK_SECRET=BMAD_FORGE_WEBHOOK_SECRET:latest,BMAD_JIRA_WEBHOOK_SECRET=BMAD_JIRA_WEBHOOK_SECRET:latest"
```

When the deploy finishes gcloud prints the **service URL**, e.g.:

```
Service URL: https://webhook-worker-abc123-ew.a.run.app
```

**Save this URL.** It's where you point Slack/Jira/Forge.

> Flag notes:
> - `--allow-unauthenticated` — Slack and Jira need to reach the service without a Google identity. Security comes from HMAC signatures (Slack) and shared secrets (Jira/Forge).
> - `--min-instances 0` — scales to zero, costs nothing when idle. First request after idle has ~1-2s cold start. Set to `1` if you need sub-second first response.
> - `--max-instances 5` — caps cost in case of a bad loop or DoS. Raise if you get legitimate burst traffic.
> - `--timeout 120s` — Slack expects a response within 3s on slash commands; Cloud Run's outer timeout just bounds runaway handlers.
> - `--concurrency 80` — one instance handles up to 80 concurrent requests. Good default for I/O-bound handlers like these.

### Part 9 — Grant Cloud Run access to Secret Manager (one time)

Cloud Run runs as a service account. That account needs permission to read the secrets you created. Cloud Run usually auto-grants this during `--set-secrets`, but if you see `PERMISSION_DENIED`:

```bash
# Find the Cloud Run service account (usually <PROJECT_NUMBER>-compute@developer.gserviceaccount.com)
SA=$(gcloud run services describe webhook-worker --region europe-west1 --format='value(spec.template.spec.serviceAccountName)')
echo "Service account: $SA"

# Grant access to each secret
for s in SLACK_BOT_TOKEN SLACK_SIGNING_SECRET GITHUB_TOKEN BMAD_GITHUB_TOKEN BMAD_FORGE_WEBHOOK_SECRET BMAD_JIRA_WEBHOOK_SECRET; do
  gcloud secrets add-iam-policy-binding "$s" \
    --member="serviceAccount:$SA" \
    --role="roles/secretmanager.secretAccessor"
done
```

### Part 10 — Verify the deployment

```bash
SERVICE_URL=$(gcloud run services describe webhook-worker --region europe-west1 --format='value(status.url)')
echo "Deployed at: $SERVICE_URL"

# Health check
curl "$SERVICE_URL/healthz"
# → {"ok":true}

# Confirm unknown routes 404
curl "$SERVICE_URL/nope"
# → {"error":"Not found","path":"/nope"}

# Confirm Jira webhook rejects non-POST
curl -X GET "$SERVICE_URL/bmad/jira-webhook"
# → {"error":"Method not allowed"}
```

Tail the logs during a real test:

```bash
gcloud run services logs tail webhook-worker --region europe-west1
```

### Part 11 — Cut over Slack / Jira / Forge to the new URL

Until you flip these, the old Vercel worker is still handling traffic.

1. **Slack app** (<https://api.slack.com/apps>) → your BMAD app:
   - **Slash Commands** → edit `/bmad` → set Request URL to `https://<service-url>/api/slack`.
   - **Interactivity & Shortcuts** → Request URL = `https://<service-url>/api/slack`.
   - **Event Subscriptions** → Request URL = `https://<service-url>/api/slack`. Slack will re-do the URL verification handshake; the handler already responds to `type: url_verification` with the challenge.
2. **Jira webhooks** (Jira admin → System → Webhooks):
   - Update `/bmad/jira-webhook` and `/bmad/jira-comment-webhook` endpoints to `https://<service-url>/bmad/jira-webhook` and `/bmad/jira-comment-webhook`.
3. **Forge app** (panels that POST to `/workflow/*`): update the endpoints in the Forge manifest to `https://<service-url>/workflow/...`, then `forge deploy` + `forge install`.

### Part 12 — Subsequent deploys

Redeploy after a code change:

```bash
gcloud builds submit --tag europe-west1-docker.pkg.dev/$PROJECT_ID/bmad/webhook-worker:latest
gcloud run deploy webhook-worker \
  --image europe-west1-docker.pkg.dev/$PROJECT_ID/bmad/webhook-worker:latest \
  --region europe-west1
```

(All env/secret flags are remembered from the previous deploy — you only need to pass them again when they change.)

Roll back to a prior revision in seconds:

```bash
gcloud run revisions list --service webhook-worker --region europe-west1
gcloud run services update-traffic webhook-worker --region europe-west1 --to-revisions=<REVISION_NAME>=100
```

---

## What's portable if you move off Cloud Run later

The service is just "HTTP container on `$PORT`." To move:

- **GKE / any Kubernetes**: write a Deployment + Service + Ingress; image and port are unchanged.
- **AWS App Runner / ECS Fargate**: point at the same image in ECR; inject env the AWS way.
- **Fly.io / Render / Railway**: connect the repo, set env, done.

The only Cloud-Run-specific bits are the `gcloud builds submit` / `gcloud run deploy` commands and the Secret Manager references — everything inside the container is vanilla Node.

---

## Cost

At `min-instances=0`, Cloud Run costs **$0 when idle**. A burst that handles a few thousand webhooks/day typically stays under $1/month. The $300 free credit covers many months of normal usage.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `PERMISSION_DENIED` on secret access at startup | Cloud Run service account missing `roles/secretmanager.secretAccessor` | Run the loop in Part 9 |
| Slack signature `401 Invalid signature` | `SLACK_SIGNING_SECRET` mismatched or clock skew | Re-copy secret from Slack; confirm server clock is correct (Cloud Run is always NTP-synced) |
| Jira `401 Unauthorized` | `BMAD_JIRA_WEBHOOK_SECRET` set on server but not sent in `X-BMAD-Jira-Secret` header | Either set the header on the Jira side, or unset the env on the server |
| Forge panels get `503` | Neither `BMAD_FORGE_WEBHOOK_SECRET` nor `BMAD_DISCOVERY_WEBHOOK_SECRET` is set | Create the secret and redeploy |
| Cold start spikes | `min-instances=0` | Bump to `--min-instances 1` (~$5/mo baseline) |
| Logs empty | Requests not reaching Cloud Run | Double-check the Request URL on the Slack/Jira side; test with `curl` |
