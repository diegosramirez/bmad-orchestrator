# Slack Slash Commands — Setup & Deployment

Trigger BMAD Orchestrator runs directly from Slack using `/bmad` slash commands. A Vercel serverless function bridges Slack and GitHub Actions.

## Architecture

```
User types: /bmad run SAM1 "Add dashboard feature"
  → Slack sends POST to Vercel function
  → Function verifies Slack signature
  → Function dispatches GitHub Actions workflow (bmad-start-run.yml)
  → Slack shows confirmation with link to Actions run
```

The function is a single TypeScript file (`slack-worker/api/slack.ts`) deployed to Vercel's free tier. It's stateless — it just translates Slack commands into GitHub Actions `workflow_dispatch` API calls.

## Prerequisites

- **Slack app** with a bot user (see [slack-setup.md](slack-setup.md) for creating one)
- **Vercel account** — free tier at [vercel.com](https://vercel.com)
- **GitHub Personal Access Token** with `actions:write` and `repo` scope
- **Node.js** 18+ installed locally

## Local Development

```bash
cd slack-worker
npm install
npx vercel dev
```

This starts a local server (usually `http://localhost:3000`). You can test with curl:

```bash
# Should return {"error":"SLACK_SIGNING_SECRET not configured"}
curl -X POST http://localhost:3000/api/slack
```

To test with real Slack signatures locally, create a `.env` file in `slack-worker/`:

```env
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_BOT_TOKEN=xoxb-your-bot-token
GITHUB_TOKEN=ghp_your-pat
GITHUB_REPO=diegosramirez/bmad-orchestrator
DEFAULT_TARGET_REPO=diegosramirez/my-test-app
DEFAULT_TEAM_ID=SAM1
```

## Production Deployment

### 1. First-time setup

```bash
cd slack-worker
npm install
npx vercel login          # Authenticates via browser (OAuth 2.0 Device Flow)
npx vercel --prod         # Deploy — follow prompts to create project
```

Note the production URL (e.g., `https://slack-worker.vercel.app`).

### 2. Set environment variables

Go to your Vercel project dashboard → **Settings** → **Environment Variables** and add:

| Variable | Value | Sensitive? |
|----------|-------|------------|
| `SLACK_SIGNING_SECRET` | Slack app → Basic Information → Signing Secret | Yes |
| `SLACK_BOT_TOKEN` | Slack app → OAuth → Bot User OAuth Token (`xoxb-...`) | Yes |
| `GITHUB_TOKEN` | GitHub PAT with `actions:write` + `repo` scope | Yes |
| `GITHUB_REPO` | `diegosramirez/bmad-orchestrator` | No |
| `DEFAULT_TARGET_REPO` | `diegosramirez/my-test-app` | No |
| `DEFAULT_TEAM_ID` | `SAM1` | No |

After adding variables, redeploy:

```bash
npx vercel --prod
```

### 3. Configure Slack app

**Slash command** (if not already set up):
1. Go to [api.slack.com/apps](https://api.slack.com/apps) → your app
2. Click **Slash Commands** → **Create New Command**
3. Fill in:
   - **Command:** `/bmad`
   - **Request URL:** `https://slack-worker.vercel.app/api/slack`
   - **Short Description:** `Run BMAD Orchestrator`
   - **Usage Hint:** `run SAM1 "prompt" | retry | status | help`
4. Save

**Interactivity** (required for wizard modal + retry buttons):
1. Go to **Interactivity & Shortcuts** in the sidebar
2. Toggle **Interactivity** → **On**
3. Set **Request URL** to: `https://slack-worker.vercel.app/api/slack`
4. Save

**Reinstall the app** to your workspace after making these changes.

### 4. Verify

In any Slack channel where the bot is invited:

```
/bmad help
```

You should see the command reference.

## How We Configured Everything

### Slack App

1. Created a Slack app at [api.slack.com/apps](https://api.slack.com/apps) with bot scopes: `chat:write`
2. Installed the app to the workspace, invited the bot to the target channel
3. Added `/bmad` slash command pointing to the Vercel function URL
4. Enabled **Interactivity** with the same Request URL (for modals + buttons)
5. Grabbed the **Signing Secret** from Basic Information (used for request verification)
6. Grabbed the **Bot User OAuth Token** (`xoxb-...`) from OAuth & Permissions (needed to open modals)

### Vercel

1. Ran `npx vercel login` to authenticate (OAuth 2.0 Device Flow opens browser)
2. Ran `npx vercel --prod` from `slack-worker/` to create the project and deploy
3. Set 6 environment variables in the Vercel dashboard (see table above)
4. Redeployed after setting env vars

### GitHub

1. Used an existing PAT (`BMAD_GH_PAT`) with `actions:write` + `repo` scope
2. Added `slack_thread_ts` input to `bmad-start-run.yml` workflow so Slack-initiated runs can thread replies back

### Project structure

```
slack-worker/
├── api/
│   └── slack.ts         # Serverless function (single file, all logic)
├── package.json         # type: "module", devDeps only
├── tsconfig.json        # TypeScript config
└── vercel.json          # Minimal Vercel config
```

Key decisions:
- **No framework** — plain Vercel serverless function, zero runtime dependencies
- **`"type": "module"`** in package.json — required for ESM `export default`
- **Raw body reading** — we read the request body manually (not via Vercel's auto-parser) to verify the Slack HMAC signature
- **`node:crypto`** — Node.js built-in for HMAC-SHA256 signature verification

## Interactive Features

### Wizard Modal

Type `/bmad` (with no arguments) to open an interactive form:
- **Team ID** — pre-filled with default
- **Prompt** — feature description or Jira key
- **Target Repository** — pre-filled with default, override if needed
- **Verbose mode** — checkbox to enable Slack thread streaming
- **Skip nodes** — checkboxes for each pipeline node

### Retry Button

When a pipeline run fails, the Slack failure message includes a **Retry** button. Clicking it opens a modal where you can optionally add guidance (e.g., "fix the auth middleware") before re-dispatching. The retry button only appears when a branch exists (i.e., after code has been committed).

### Refine Button

When a run succeeds and creates a PR, the success message includes a **Refine** button. If you test the PR locally and aren't happy with the results, click Refine to provide guidance (e.g., "add loading states and error boundaries") and re-run the dev/QA/review pipeline on the existing branch. The PR is updated in place.

## Command Reference

| Command | Description |
|---------|-------------|
| `/bmad` | Open the interactive run wizard |
| `/bmad run <team> "<prompt>"` | Start a new orchestrator run |
| `/bmad run <team> "<prompt>" --verbose` | Start with verbose Slack thread updates |
| `/bmad run <team> "<prompt>" --skip dev_story,qa_automation` | Skip specific pipeline nodes |
| `/bmad run <team> "<prompt>" --target owner/repo` | Override the target repository |
| `/bmad retry <team> <branch> "<guidance>"` | Retry on an existing branch (skips planning nodes) |
| `/bmad retry <team> <branch>` | Retry without additional guidance |
| `/bmad status` | Get link to GitHub Actions workflow runs |
| `/bmad help` | Show available commands |

### Examples

```
/bmad run SAM1 "Add user dashboard with analytics"
/bmad run SAM1 SAM1-54
/bmad run SAM1 "Improve search performance" --verbose
/bmad run SAM1 "Add login page" --target myorg/frontend-app
/bmad run SAM1 "Add tests" --skip party_mode_refinement --verbose
/bmad retry SAM1 bmad/sam1/SAM1-54-dashboard "fix the auth middleware"
/bmad retry SAM1 bmad/sam1/SAM1-54-dashboard
```

### Valid skip node names

| Node | What it skips |
|------|--------------|
| `check_epic_state` | Validate epic status in Jira |
| `create_or_correct_epic` | Create or update the epic |
| `create_story_tasks` | Generate stories and tasks |
| `party_mode_refinement` | Multi-agent story refinement |
| `detect_commands` | AI-detect build/test/lint commands |
| `dev_story` | Generate implementation code |
| `qa_automation` | Generate QA tests |
| `code_review` | Architect code review loop |
| `commit_and_push` | Git commit and push |
| `create_pull_request` | Create GitHub PR |

## Updating the function

After making changes to `slack-worker/api/slack.ts`:

```bash
cd slack-worker && npx vercel --prod
```

That's it — Vercel rebuilds and redeploys in seconds.

## Troubleshooting

### "dispatch_failed" or no workflow starts
- Verify `GITHUB_TOKEN` has `actions:write` and `repo` permissions
- Verify `GITHUB_REPO` is set to the correct `owner/repo` (the repo containing the workflow)
- Check GitHub Actions is enabled for the repository

### "Invalid signature" from Slack
- Verify `SLACK_SIGNING_SECRET` in Vercel matches your Slack app's signing secret (Basic Information page, not the bot token)
- Redeploy after changing env vars

### FUNCTION_INVOCATION_FAILED
- Check Vercel function logs: Vercel dashboard → your project → **Logs** tab
- Common causes: missing env vars, TypeScript compilation errors

### Slash command not appearing in Slack
- Reinstall the app after adding the slash command
- Make sure the bot is invited to the channel where you're using `/bmad`
