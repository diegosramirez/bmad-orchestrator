/**
 * POST /api/jira-comment — Jira comment webhook; /bmad retry|refine → workflow_dispatch.
 *
 * Env: same as jira-issue plus JIRA_BRANCH_CUSTOM_FIELD_ID (default customfield_10145).
 * Optional: BMAD_JIRA_WEBHOOK_SECRET + header X-BMAD-Jira-Secret.
 */
import {
  buildGithubActionsWorkflowUrl,
  dispatchBmadWorkflow,
  getDefaultTargetRepo,
  getDefaultTeamId,
  hasActiveBmadRunForPrompt,
  jiraBranchFieldId,
  jiraTargetRepoFieldId,
  normalizeTargetRepo,
  parseBmadCommentCommand,
  readJsonBody,
  verifyJiraWebhookSecret,
  FORGE_RUN_IN_PROGRESS_MESSAGE,
} from "./lib/jira-webhooks";

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

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

  if (!isRecord(body)) {
    res.status(400).json({ ok: false, run_started: false, message: "Expected JSON object" });
    return;
  }

  const comment = isRecord(body.comment) ? body.comment : {};
  const comment_body = (typeof comment.body === "string" ? comment.body : "").trim();

  if (!comment_body.startsWith("/bmad")) {
    res.status(200).json({
      ok: true,
      run_started: false,
      persisted: false,
      message: "Comment does not contain a /bmad command; no run started.",
    });
    return;
  }

  const parsed = parseBmadCommentCommand(comment_body);
  if (!parsed.ok) {
    if (parsed.message === "not_bmad") {
      res.status(200).json({
        ok: true,
        run_started: false,
        persisted: false,
        message: "Comment does not contain a /bmad command; no run started.",
      });
      return;
    }
    res.status(400).json({
      ok: false,
      run_started: false,
      persisted: false,
      message: parsed.message,
    });
    return;
  }

  const issue = isRecord(body.issue) ? body.issue : {};
  const issue_key =
    typeof issue.key === "string" && issue.key ? issue.key : "unknown";
  const fields = isRecord(issue.fields) ? issue.fields : {};

  const branch_fid = jiraBranchFieldId();
  const target_fid = jiraTargetRepoFieldId();

  const branch_val = fields[branch_fid];
  const branch =
    typeof branch_val === "string" && branch_val.trim() ? branch_val.trim() : "";

  if (!branch) {
    res.status(400).json({
      ok: false,
      run_started: false,
      persisted: false,
      message:
        `Missing branch. Ensure the issue has ${branch_fid} (BMAD Branch) set, ` +
        "e.g. by running the pipeline once so BMAD can save the branch.",
    });
    return;
  }

  let team_id = getDefaultTeamId();
  if (issue_key.includes("-")) {
    team_id = issue_key.split("-", 1)[0];
  }

  let target_repo_raw = "";
  const custom_target = fields[target_fid];
  if (isRecord(custom_target)) {
    const value = custom_target.value;
    if (typeof value === "string" && value.trim()) target_repo_raw = value.trim();
  }
  if (!target_repo_raw) target_repo_raw = getDefaultTargetRepo();
  const target_repo = normalizeTargetRepo(target_repo_raw);

  const conflict = await hasActiveBmadRunForPrompt(issue_key);
  if (conflict) {
    res.status(409).json({
      ok: false,
      run_started: false,
      code: "run_in_progress",
      issue_key,
      message: FORGE_RUN_IN_PROGRESS_MESSAGE,
    });
    return;
  }

  const inputs: Record<string, string> = {
    target_repo,
    team_id,
    prompt: issue_key,
    slack_verbose: "false",
    branch,
    guidance: parsed.guidance,
  };

  for (const node of [
    "check_epic_state",
    "create_or_correct_epic",
    "create_story_tasks",
    "party_mode_refinement",
    "detect_commands",
  ]) {
    inputs[`skip_${node}`] = "true";
  }

  const { ok, dispatch_status, dispatch_error } = await dispatchBmadWorkflow(inputs);
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
