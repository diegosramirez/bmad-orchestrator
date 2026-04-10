/**
 * POST /api/jira-issue — Jira issue webhook → GitHub Actions workflow_dispatch.
 *
 * Env: BMAD_GITHUB_REPO, BMAD_GITHUB_TOKEN, BMAD_GITHUB_BASE_BRANCH, BMAD_GITHUB_OWNER,
 * DEFAULT_TARGET_REPO, DEFAULT_TEAM_ID, JIRA_*_CUSTOM_FIELD_ID (optional),
 * BMAD_JIRA_WEBHOOK_SECRET (optional; if set, require header X-BMAD-Jira-Secret).
 */
import {
  buildGithubActionsWorkflowUrl,
  dispatchGithubWorkflowFromJira,
  hasActiveBmadRunForPrompt,
  parseJiraWebhook,
  readJsonBody,
  verifyJiraWebhookSecret,
  FORGE_RUN_IN_PROGRESS_MESSAGE,
} from "../lib/jira-webhooks.js";

export default async function handler(req: any, res: any): Promise<void> {
  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  if (!verifyJiraWebhookSecret(req.headers["x-bmad-jira-secret"])) {
    res.status(401).json({ ok: false, run_started: false, message: "Unauthorized" });
    return;
  }

  let body: unknown;
  try {
    body = await readJsonBody(req);
  } catch {
    res.status(400).json({ ok: false, run_started: false, message: "Invalid JSON body" });
    return;
  }

  const ctx = parseJiraWebhook(body);
  if (ctx === null || ctx.epic_key === null) {
    res.status(200).json({
      ok: true,
      run_started: false,
      persisted: false,
      message:
        "Run not started (missing context or story has no parent epic). " +
        "Payload is not persisted on Vercel.",
    });
    return;
  }

  const conflict = await hasActiveBmadRunForPrompt(ctx.story_key);
  if (conflict) {
    res.status(409).json({
      ok: false,
      run_started: false,
      code: "run_in_progress",
      issue_key: ctx.story_key,
      message: FORGE_RUN_IN_PROGRESS_MESSAGE,
    });
    return;
  }

  const { ok, dispatch_status, dispatch_error } = await dispatchGithubWorkflowFromJira(ctx);
  const actions_url = buildGithubActionsWorkflowUrl();

  const content: Record<string, unknown> = {
    ok: true,
    persisted: false,
    run_started: ok,
    message: ok
      ? "GitHub Actions workflow dispatched."
      : "Failed to dispatch GitHub Actions workflow.",
  };
  if (actions_url) content.actions_url = actions_url;
  if (dispatch_status !== null) content.dispatch_status = dispatch_status;
  if (dispatch_error !== null) content.dispatch_error = dispatch_error;

  res.status(ok ? 202 : 500).json(content);
}
