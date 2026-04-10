/**
 * Shared handler for Forge panel POST JSON → workflow_dispatch (parity with FastAPI).
 */
import {
  buildGithubActionsWorkflowUrl,
  dispatchBmadWorkflow,
  forgeWebhookSecretConfigured,
  FORGE_SECRET_ENV_MESSAGE,
  FORGE_RUN_IN_PROGRESS_MESSAGE,
  getDefaultTargetRepo,
  getDefaultTeamId,
  hasActiveBmadRunForPrompt,
  normalizeTargetRepo,
  readJsonBody,
} from "./jira-webhooks.js";
import {
  buildDevStoryWorkflowInputs,
  buildDiscoveryWorkflowInputs,
  buildEpicArchitectWorkflowInputs,
  buildStoriesWorkflowInputs,
  teamIdFromIssueKey,
} from "./forge-workflows.js";

export type ForgeMode = "discovery" | "architect" | "stories" | "dev";

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function buildInputs(
  mode: ForgeMode,
  issueKey: string,
  targetRepo: string,
  teamId: string
): Record<string, string> {
  switch (mode) {
    case "discovery":
      return buildDiscoveryWorkflowInputs(issueKey, targetRepo, teamId);
    case "architect":
      return buildEpicArchitectWorkflowInputs(issueKey, targetRepo, teamId);
    case "stories":
      return buildStoriesWorkflowInputs(issueKey, targetRepo, teamId);
    case "dev":
      return buildDevStoryWorkflowInputs(issueKey, targetRepo, teamId);
    default: {
      const _exhaustive: never = mode;
      return _exhaustive;
    }
  }
}

export async function handleForgePost(req: any, res: any, mode: ForgeMode): Promise<void> {
  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  if (!forgeWebhookSecretConfigured()) {
    res.status(503).json({
      ok: false,
      run_started: false,
      message: FORGE_SECRET_ENV_MESSAGE,
    });
    return;
  }

  let body: unknown;
  try {
    body = await readJsonBody(req);
  } catch {
    res.status(400).json({ ok: false, run_started: false, message: "Invalid JSON body" });
    return;
  }

  if (!isRecord(body)) {
    res.status(400).json({ ok: false, run_started: false, message: "Expected JSON object" });
    return;
  }

  const issueKey = String(body.issue_key ?? "").trim();
  if (!issueKey) {
    res.status(400).json({ ok: false, run_started: false, message: "Missing issue_key" });
    return;
  }

  const targetRaw = String(body.target_repo ?? "").trim() || getDefaultTargetRepo();
  const targetRepo = normalizeTargetRepo(targetRaw);
  if (!targetRepo) {
    res.status(400).json({
      ok: false,
      run_started: false,
      persisted: false,
      message: "Missing target_repo (body or DEFAULT_TARGET_REPO).",
    });
    return;
  }

  if (await hasActiveBmadRunForPrompt(issueKey)) {
    res.status(409).json({
      ok: false,
      run_started: false,
      code: "run_in_progress",
      issue_key: issueKey,
      message: FORGE_RUN_IN_PROGRESS_MESSAGE,
    });
    return;
  }

  const teamOverride = String(body.team_id ?? "").trim();
  const teamId = teamOverride || teamIdFromIssueKey(issueKey, getDefaultTeamId());

  const inputs = buildInputs(mode, issueKey, targetRepo, teamId);
  const { ok, dispatch_status, dispatch_error } = await dispatchBmadWorkflow(inputs);
  const actionsUrl = buildGithubActionsWorkflowUrl();

  const content: Record<string, unknown> = {
    ok: true,
    persisted: false,
    run_started: ok,
    issue_key: issueKey,
    message: ok
      ? "GitHub Actions workflow dispatched."
      : "Failed to dispatch GitHub Actions workflow.",
  };
  if (actionsUrl) content.actions_url = actionsUrl;
  if (dispatch_status !== null) content.dispatch_status = dispatch_status;
  if (dispatch_error !== null) content.dispatch_error = dispatch_error;

  res.status(ok ? 202 : 500).json(content);
}
