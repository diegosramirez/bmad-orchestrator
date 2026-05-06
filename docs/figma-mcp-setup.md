# Figma MCP Setup

The orchestrator can read Figma designs directly during code generation via Figma's **remote** Dev Mode MCP server. When enabled, the dev and UX agents have access to `mcp__figma__*` tools that return frame metadata, design tokens, generated code snippets, and component info — they use this to match the design while writing UI code.

This works in any environment with internet access (local CLI, GitHub Actions, Cloud Run) — no Figma desktop app required at runtime.

## Prerequisites

- A **Figma Dev or Full seat** on your Figma plan. The remote MCP server is gated behind paid seats — Viewer/Free won't work. Check at <https://www.figma.com/settings/billing>.
- Access to whichever Figma file the orchestrator will read. The MCP server inherits your user's permissions; if you can open the file in Figma, MCP can read it.

## Step 1 — Obtain a Bearer token (one-time, manual)

The Figma remote MCP server uses OAuth 2.1 with browser consent. There is **no headless / API-key alternative today** — you authenticate in a browser and capture the resulting Bearer token, then store it.

Follow Figma's setup walkthrough:

> <https://help.figma.com/hc/en-us/articles/35281350665623-Figma-MCP-collection-How-to-set-up-the-Figma-remote-MCP-server-preferred>

The exact steps depend on which MCP client you use to perform the initial OAuth, but the goal in every variant is to end up with a Bearer token (string starting with `figd_…` or similar). Copy that token — you'll set it as an env var.

## Step 2 — Set env vars locally

In your `.env` (or exported in your shell):

```bash
BMAD_FIGMA_MCP_ENABLED=true
BMAD_FIGMA_MCP_TOKEN=figd_...your_token_here...
# BMAD_FIGMA_MCP_URL=https://mcp.figma.com/mcp   # default; override only for staging/proxies
```

Test it locally:

```bash
unset BMAD_GITHUB_TOKEN  # avoid stale env from older runs
uv run bmad-orchestrator run --team-id TEST \
  --prompt "Implement the design at https://www.figma.com/design/<file-id>/<file-name>" \
  --dummy-jira --dummy-github --execution-mode discovery
```

You should see the `ux_design_handoff` node execute and Sally call `mcp__figma__*` tools. If you see "Skipped — no figma_url or Figma MCP disabled" in the logs, double-check that `BMAD_FIGMA_MCP_ENABLED=true` is in your env and that the prompt contains a `figma.com/{file,design,proto,board}/...` URL.

If the orchestrator hard-fails at startup with `BMAD_FIGMA_MCP_TOKEN is required when BMAD_FIGMA_MCP_ENABLED=true`, the token isn't set.

## Step 3 — Configure GitHub Actions

For the cloud orchestrator pipeline to use Figma MCP, set the secret and the toggle on your GitHub repo:

```bash
# Repo-level secret (sensitive)
gh secret set BMAD_FIGMA_MCP_TOKEN --body "figd_...your_token_here..."

# Repo-level variable (non-sensitive on/off switch)
gh variable set BMAD_FIGMA_MCP_ENABLED --body "true"
```

The [bmad-start-run.yml](../.github/workflows/bmad-start-run.yml) workflow already wires both into the orchestrator step's env block — no further changes needed.

To turn the integration off in CI without removing the secret, just set the variable to `false`:

```bash
gh variable set BMAD_FIGMA_MCP_ENABLED --body "false"
```

## Token rotation

Figma OAuth tokens may expire; the docs don't currently specify a fixed lifetime. If runs start failing with auth errors from `mcp.figma.com`:

1. Re-run Step 1 to obtain a fresh token.
2. Update both your local `.env` and the GH repo secret.

There's no automated refresh in v1 — if rotation becomes painful in practice, we'll add refresh-token handling (similar to the `GitHubAppTokenProvider` pattern).

## Tool surface — what's available

When the integration is on, the dev and UX agents can call (among others):

- `mcp__figma__get_design_context` (or `get_code` on some servers) — returns auto-generated component code for a frame
- `mcp__figma__get_variable_defs` — returns the file's design-token map (colors, spacing, typography)
- `mcp__figma__get_screenshot` — returns a rendered PNG of a frame for visual reference
- `mcp__figma__get_metadata` — frame/component metadata, layer hierarchy

Plus several remote-only tools (`generate_figma_design`, `search_design_system`, etc.). Tool names are wildcard-matched in our prompts — the orchestrator doesn't hardcode which specific tools the agent uses, so server-side renames are usually invisible to us.

## What if the MCP server is unreachable?

If `mcp.figma.com` is down or returns auth errors mid-run:
- The `ux_design_handoff` node logs the failure and produces an empty `state.ux_handoff`. The pipeline continues — the dev agent still sees the Figma URL in the prompt but won't have the structured handoff.
- For unrecoverable auth issues, rotate the token (above).

## Troubleshooting

**"Skipped — no figma_url or Figma MCP disabled" in logs**
- Either `BMAD_FIGMA_MCP_ENABLED` isn't `true`, or the prompt/story didn't contain a Figma URL the regex caught (`utils/figma_url.py`).

**Auth errors from `api.figma.com` / `mcp.figma.com`**
- Token expired, was revoked, or is for a Free-seat account that doesn't have Dev Mode access. Re-run Step 1.

**Agent generates UI code but it doesn't match the design**
- See "What 'good' looks like" in the broader docs. First-pass match is typically 70–85%; expect a polish pass. Quality depends heavily on Figma file structure (auto-layout, named components, variables for tokens). If your Figma file is a "drawing" rather than a structured design system, the agent has less to work with.

**Want to disable Figma in a single run without unsetting the global env**
- Pass `BMAD_FIGMA_MCP_ENABLED=false` for that invocation only.
