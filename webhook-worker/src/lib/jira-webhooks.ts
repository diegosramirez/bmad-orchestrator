/**
 * Jira webhook helpers for Vercel (TypeScript only). Parses Jira payloads, dispatches
 * bmad-start-run.yml via GitHub API, and detects in-flight runs.
 *
 * Lives outside `api/` so Vercel ships this module next to the compiled handlers (Node ESM
 * does not resolve `api/lib/*` in the serverless bundle).
 */
import { timingSafeEqual } from "node:crypto";

import { getGitHubAuth } from "./github-auth.js";

// ── Constants (defaults match bmad_orchestrator Settings) ─────────────────────

export const BMAD_WORKFLOW_FILE = "bmad-start-run.yml";

const ACTIVE_RUN_STATUSES = new Set([
  "queued",
  "in_progress",
  "waiting",
  "requested",
  "pending",
]);

const GITHUB_ERROR_BODY_MAX = 4000;

export const FORGE_RUN_IN_PROGRESS_MESSAGE =
  "A workflow orchestrator run is already in progress for this issue. " +
  "Wait for it to finish before starting another.";

export const BMAD_COMMENT_USAGE =
  'Usage: /bmad retry "guidance" or /bmad refine "guidance"';

// ── Types ───────────────────────────────────────────────────────────────────

export interface JiraWebhookContext {
  team_id: string;
  target_repo: string | null;
  story_key: string;
  epic_key: string | null;
  prompt: string;
}

export interface DispatchResult {
  ok: boolean;
  dispatch_status: number | null;
  dispatch_error: string | null;
}

// ── Env helpers ─────────────────────────────────────────────────────────────

export function envString(name: string, defaultValue = ""): string {
  const v = process.env[name];
  return typeof v === "string" ? v : defaultValue;
}

export function jiraTargetRepoFieldId(): string {
  return envString("JIRA_TARGET_REPO_CUSTOM_FIELD_ID", "customfield_10112");
}

export function jiraBranchFieldId(): string {
  return envString("JIRA_BRANCH_CUSTOM_FIELD_ID", "customfield_10145");
}

export function getGithubOwner(): string {
  return envString("BMAD_GITHUB_OWNER", "");
}

export function getGithubRepo(): string {
  return envString("BMAD_GITHUB_REPO", "");
}

export function getDefaultRef(): string {
  return envString("BMAD_GITHUB_BASE_BRANCH", "main");
}

export function getDefaultTargetRepo(): string {
  return envString("DEFAULT_TARGET_REPO", "");
}

export function getDefaultTeamId(): string {
  return envString("DEFAULT_TEAM_ID", "");
}

/** If set, requests must send X-BMAD-Jira-Secret with this value. */
export function getJiraWebhookSecret(): string {
  return envString("BMAD_JIRA_WEBHOOK_SECRET", "");
}

/** Forge JSON endpoints: `BMAD_FORGE_WEBHOOK_SECRET` or `BMAD_DISCOVERY_WEBHOOK_SECRET`. */
export function getForgeWebhookSecret(): string {
  const forge = envString("BMAD_FORGE_WEBHOOK_SECRET", "");
  const discovery = envString("BMAD_DISCOVERY_WEBHOOK_SECRET", "");
  return forge || discovery;
}

export function forgeWebhookSecretConfigured(): boolean {
  return Boolean(getForgeWebhookSecret().trim());
}

export const FORGE_SECRET_ENV_MESSAGE =
  "Set BMAD_FORGE_WEBHOOK_SECRET or BMAD_DISCOVERY_WEBHOOK_SECRET on the server.";

// ── Secret verification ─────────────────────────────────────────────────────

export function verifyJiraWebhookSecret(headerValue: string | undefined): boolean {
  const secret = getJiraWebhookSecret();
  if (!secret) return true;
  if (!headerValue || typeof headerValue !== "string") return false;
  try {
    const a = Buffer.from(headerValue, "utf8");
    const b = Buffer.from(secret, "utf8");
    if (a.length !== b.length) return false;
    return timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

// ── Target repo normalization ───────────────────────────────────────────────

export function normalizeTargetRepo(raw: string | null | undefined): string {
  const value = (raw ?? "").trim();
  if (!value) return "";
  if (value.includes("/")) return value;
  const owner = getGithubOwner();
  if (owner) return `${owner}/${value}`;
  return value;
}

// ── Parse Jira issue webhook body ───────────────────────────────────────────

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function parseJiraWebhook(body: unknown): JiraWebhookContext | null {
  try {
    if (!isRecord(body)) return null;
    const issue = body.issue;
    if (!isRecord(issue)) return null;
    const fields = issue.fields;
    if (!isRecord(fields)) return null;
    const story_key = issue.key;
    if (typeof story_key !== "string" || !story_key) return null;
    const project = fields.project;
    if (!isRecord(project)) return null;
    const team_id = project.key;
    if (typeof team_id !== "string" || !team_id) return null;

    let target_repo: string | null = null;
    const targetFid = jiraTargetRepoFieldId();
    const custom_target = fields[targetFid];
    if (isRecord(custom_target)) {
      const value = custom_target.value;
      if (typeof value === "string" && value.trim()) target_repo = value.trim();
    }

    let epic_key: string | null = null;
    const parent = fields.parent;
    if (isRecord(parent)) {
      const pk = parent.key;
      epic_key = typeof pk === "string" ? pk : null;
    }

    const summary = fields.summary;
    const prompt =
      typeof summary === "string" && summary.trim()
        ? summary.trim()
        : story_key;

    return {
      team_id,
      target_repo,
      story_key,
      epic_key,
      prompt,
    };
  } catch {
    return null;
  }
}

// ── Parse /bmad retry|refine (mirrors bmad_comment_parse.py) ────────────────

export type ParseCommentResult =
  | { ok: true; guidance: string }
  | { ok: false; message: string };

export function parseBmadCommentCommand(text: string): ParseCommentResult {
  const raw = text.trim();
  const re = /^\/?bmad\s+(retry|refine)\b\s*(.*)$/is;
  const m = raw.match(re);
  if (m) {
    const sub = m[1].toLowerCase();
    if (sub !== "retry" && sub !== "refine") {
      return { ok: false, message: BMAD_COMMENT_USAGE };
    }
    let rest = m[2].trim();
    if (rest.length >= 2) {
      const first = rest[0];
      const last = rest[rest.length - 1];
      if (
        (first === '"' && last === '"') ||
        (first === "\u201c" && last === "\u201d")
      ) {
        rest = rest.slice(1, -1);
      }
    }
    return { ok: true, guidance: rest };
  }

  if (!raw.toLowerCase().startsWith("/bmad")) {
    return { ok: false, message: "not_bmad" };
  }

  const mw = raw.match(/^\/?bmad\s+(\S+)/i);
  if (mw && !["retry", "refine"].includes(mw[1].toLowerCase())) {
    return { ok: false, message: `Unknown /bmad subcommand: ${mw[1]}` };
  }

  return { ok: false, message: BMAD_COMMENT_USAGE };
}

// ── GitHub workflow dispatch ─────────────────────────────────────────────────

function truncateGithubBody(text: string | null | undefined): string {
  if (!text) return "";
  if (text.length <= GITHUB_ERROR_BODY_MAX) return text;
  return text.slice(0, GITHUB_ERROR_BODY_MAX) + "…(truncated)";
}

export function buildGithubActionsWorkflowUrl(): string | null {
  const repo = getGithubRepo();
  if (!repo) return null;
  return `https://github.com/${repo}/actions/workflows/${BMAD_WORKFLOW_FILE}`;
}

export async function dispatchBmadWorkflow(
  inputs: Record<string, string>
): Promise<DispatchResult> {
  const GITHUB_REPO = getGithubRepo();
  if (!GITHUB_REPO) {
    return {
      ok: false,
      dispatch_status: null,
      dispatch_error: "Missing BMAD_GITHUB_REPO",
    };
  }

  let authHeader: string;
  try {
    authHeader = await getGitHubAuth().getAuthHeader();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, dispatch_status: null, dispatch_error: `Auth error: ${msg}` };
  }

  const ref = getDefaultRef();
  const url = `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/${BMAD_WORKFLOW_FILE}/dispatches`;

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: authHeader,
        Accept: "application/vnd.github.v3+json",
        "User-Agent": "bmad-jira-webhook",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref, inputs }),
    });

    if (resp.status !== 204) {
      const bodyText = await resp.text();
      return {
        ok: false,
        dispatch_status: resp.status,
        dispatch_error: truncateGithubBody(bodyText),
      };
    }
    return { ok: true, dispatch_status: resp.status, dispatch_error: null };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, dispatch_status: null, dispatch_error: `Request error: ${msg}` };
  }
}

export async function dispatchGithubWorkflowFromJira(
  ctx: JiraWebhookContext
): Promise<DispatchResult> {
  const target_repo_raw = ctx.target_repo || getDefaultTargetRepo();
  const target_repo = normalizeTargetRepo(target_repo_raw);

  const inputs: Record<string, string> = {
    target_repo,
    team_id: ctx.team_id || getDefaultTeamId(),
    prompt: ctx.prompt,
    slack_verbose: "false",
  };

  const extra: string[] = [];
  if (ctx.epic_key) extra.push("--epic-key", ctx.epic_key);
  if (ctx.story_key) extra.push("--story-key", ctx.story_key);
  if (extra.length) inputs.extra_flags = extra.join(" ");

  for (const node of ["check_epic_state", "create_or_correct_epic", "create_story_tasks"]) {
    inputs[`skip_${node}`] = "true";
  }

  return dispatchBmadWorkflow(inputs);
}

// ── Active run detection (mirrors github_active_run.py) ─────────────────────

function runMatchesIssueKey(runData: Record<string, unknown>, key: string): boolean {
  const inputs = runData.inputs;
  if (isRecord(inputs)) {
    const pv = inputs.prompt;
    if (typeof pv === "string" && pv.trim() === key) return true;
  }
  const display_title = runData.display_title;
  if (typeof display_title === "string" && display_title.includes(key)) return true;
  return false;
}

export async function hasActiveBmadRunForPrompt(issueKey: string): Promise<boolean> {
  const repo = getGithubRepo().trim();
  const key = issueKey.trim();
  if (!repo || !key) return false;

  let authHeader: string;
  try {
    authHeader = await getGitHubAuth().getAuthHeader();
  } catch {
    return false;
  }

  const listUrl = `https://api.github.com/repos/${repo}/actions/workflows/${BMAD_WORKFLOW_FILE}/runs?per_page=30`;
  const headers: Record<string, string> = {
    Accept: "application/vnd.github.v3+json",
    Authorization: authHeader,
    "User-Agent": "bmad-jira-webhook",
  };

  try {
    const listResp = await fetch(listUrl, { headers });
    if (!listResp.ok) return false;

    const payload = (await listResp.json()) as Record<string, unknown>;
    const runs = payload.workflow_runs;
    if (!Array.isArray(runs)) return false;

    for (const wr of runs) {
      if (!isRecord(wr)) continue;
      const status = wr.status;
      if (typeof status !== "string" || !ACTIVE_RUN_STATUSES.has(status)) continue;
      const runId = wr.id;
      if (typeof runId !== "number") continue;

      const runUrl = `https://api.github.com/repos/${repo}/actions/runs/${runId}`;
      const runResp = await fetch(runUrl, { headers });
      if (!runResp.ok) continue;

      let runData: Record<string, unknown>;
      try {
        runData = (await runResp.json()) as Record<string, unknown>;
      } catch {
        continue;
      }

      if (runMatchesIssueKey(runData, key)) return true;
    }
    return false;
  } catch {
    return false;
  }
}

/** Read raw body string from Node HTTP request (Vercel). */
export function readRawBodyString(req: {
  on: (ev: string, fn: (chunk?: Buffer) => void) => void;
}): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk?: Buffer) => {
      if (chunk) chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf-8")));
    req.on("error", reject);
  });
}

/** Parse JSON body; supports pre-parsed req.body or streamed body. */
export async function readJsonBody(req: any): Promise<unknown> {
  if (req.body != null && typeof req.body === "object" && !Buffer.isBuffer(req.body)) {
    return req.body;
  }
  if (typeof req.body === "string") {
    try {
      return JSON.parse(req.body) as unknown;
    } catch {
      return {};
    }
  }
  if (typeof req.on !== "function") {
    return {};
  }
  const raw = await readRawBodyString(req);
  if (!raw || !raw.trim()) return {};
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return {};
  }
}
