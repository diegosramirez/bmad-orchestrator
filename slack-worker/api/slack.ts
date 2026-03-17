import { createHmac, timingSafeEqual } from "node:crypto";

// ── Types ────────────────────────────────────────────────────────────────────

interface ParsedCommand {
  action: "run" | "retry" | "status" | "help";
  teamId: string;
  prompt: string;
  verbose: boolean;
  skipNodes: string[];
  branch: string;
  targetRepo: string;
}

// ── Slack signature verification ─────────────────────────────────────────────

function verifySlackSignature(
  rawBody: string,
  timestamp: string,
  signature: string,
  secret: string
): boolean {
  if (Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) return false;
  const sigBasestring = `v0:${timestamp}:${rawBody}`;
  const computed =
    "v0=" + createHmac("sha256", secret).update(sigBasestring).digest("hex");
  return timingSafeEqual(Buffer.from(computed), Buffer.from(signature));
}

// ── Command parser ───────────────────────────────────────────────────────────

const HELP_TEXT = `*BMAD Orchestrator — Slash Commands*

\`/bmad run <team> "<prompt>"\` — Start a new orchestrator run
\`/bmad run <team> "<prompt>" --verbose\` — Start with verbose Slack updates
\`/bmad run <team> "<prompt>" --skip dev_story,qa_automation\` — Skip specific nodes
\`/bmad run <team> "<prompt>" --target <owner/repo>\` — Override target repository
\`/bmad retry <team> <branch> "<guidance>"\` — Retry a failed run on an existing branch
\`/bmad status\` — Link to GitHub Actions runs
\`/bmad help\` — Show this message

*Examples:*
\`/bmad run SAM1 "Add user dashboard with analytics"\`
\`/bmad run SAM1 "SAM1-54" --verbose\`
\`/bmad retry SAM1 bmad/sam1/SAM1-54-dashboard "fix the auth middleware"\``;

function parseCommand(text: string): ParsedCommand | { error: string } {
  const trimmed = text.trim();

  if (!trimmed || trimmed === "help") {
    return { action: "help", teamId: "", prompt: "", verbose: false, skipNodes: [], branch: "", targetRepo: "" };
  }

  if (trimmed === "status") {
    return { action: "status", teamId: "", prompt: "", verbose: false, skipNodes: [], branch: "", targetRepo: "" };
  }

  const verbose = /--verbose\b/.test(trimmed);
  let remaining = trimmed.replace(/--verbose\b/, "").trim();

  let skipNodes: string[] = [];
  const skipMatch = remaining.match(/--skip\s+([\w,]+)/);
  if (skipMatch) {
    skipNodes = skipMatch[1].split(",").filter(Boolean);
    remaining = remaining.replace(/--skip\s+[\w,]+/, "").trim();
  }

  let targetRepo = "";
  const targetMatch = remaining.match(/--target\s+(\S+)/);
  if (targetMatch) {
    targetRepo = targetMatch[1];
    remaining = remaining.replace(/--target\s+\S+/, "").trim();
  }

  const runMatch = remaining.match(/^run\s+(\S+)\s+"([^"]+)"$/);
  if (runMatch) {
    return { action: "run", teamId: runMatch[1], prompt: runMatch[2], verbose, skipNodes, branch: "", targetRepo };
  }

  const runSimple = remaining.match(/^run\s+(\S+)\s+(\S+)$/);
  if (runSimple) {
    return { action: "run", teamId: runSimple[1], prompt: runSimple[2], verbose, skipNodes, branch: "", targetRepo };
  }

  const retryMatch = remaining.match(/^retry\s+(\S+)\s+(\S+)\s+"([^"]+)"$/);
  if (retryMatch) {
    return { action: "retry", teamId: retryMatch[1], prompt: retryMatch[3], verbose, skipNodes, branch: retryMatch[2], targetRepo };
  }

  const retrySimple = remaining.match(/^retry\s+(\S+)\s+(\S+)$/);
  if (retrySimple) {
    return { action: "retry", teamId: retrySimple[1], prompt: "", verbose, skipNodes, branch: retrySimple[2], targetRepo };
  }

  return { error: "Could not parse command. Try `/bmad help` for usage examples." };
}

// ── GitHub Actions dispatch ──────────────────────────────────────────────────

const SKIP_NODE_NAMES = [
  "check_epic_state", "create_or_correct_epic", "create_story_tasks",
  "party_mode_refinement", "detect_commands", "dev_story",
  "qa_automation", "code_review", "commit_and_push", "create_pull_request",
] as const;

const RETRY_SKIP_NODES = [
  "check_epic_state", "create_or_correct_epic",
  "create_story_tasks", "party_mode_refinement",
];

async function dispatchWorkflow(cmd: ParsedCommand): Promise<boolean> {
  const ghRepo = process.env.GITHUB_REPO;
  const ghToken = process.env.GITHUB_TOKEN;
  if (!ghRepo || !ghToken) {
    throw new Error("GITHUB_REPO and GITHUB_TOKEN must be configured");
  }

  const inputs: Record<string, string> = {
    target_repo: cmd.targetRepo || process.env.DEFAULT_TARGET_REPO || "",
    team_id: cmd.teamId || process.env.DEFAULT_TEAM_ID || "",
    prompt: cmd.prompt,
    slack_verbose: cmd.verbose ? "true" : "false",
  };

  if (cmd.branch) inputs.branch = cmd.branch;

  if (cmd.action === "retry") {
    const parts = ["--retry"];
    if (cmd.prompt) parts.push(`--guidance "${cmd.prompt}"`);
    inputs.extra_flags = parts.join(" ");
    inputs.prompt = inputs.prompt || cmd.teamId;
  }

  const allSkips = cmd.action === "retry"
    ? [...new Set([...RETRY_SKIP_NODES, ...cmd.skipNodes])]
    : cmd.skipNodes;

  for (const node of allSkips) {
    if (SKIP_NODE_NAMES.includes(node as typeof SKIP_NODE_NAMES[number])) {
      inputs[`skip_${node}`] = "true";
    }
  }

  const res = await fetch(
    `https://api.github.com/repos/${ghRepo}/actions/workflows/bmad-start-run.yml/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ghToken}`,
        Accept: "application/vnd.github.v3+json",
        "User-Agent": "bmad-slack-worker",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    }
  );

  return res.status === 204;
}

// ── Main handler ─────────────────────────────────────────────────────────────

function readRawBody(req: any): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf-8")));
    req.on("error", reject);
  });
}

export default async function handler(req: any, res: any): Promise<void> {
  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const secret = process.env.SLACK_SIGNING_SECRET;
  if (!secret) {
    res.status(500).json({ error: "SLACK_SIGNING_SECRET not configured" });
    return;
  }

  // Read raw body for signature verification
  const rawBody = await readRawBody(req);
  const timestamp = req.headers["x-slack-request-timestamp"] as string;
  const signature = req.headers["x-slack-signature"] as string;

  if (!timestamp || !signature || !verifySlackSignature(rawBody, timestamp, signature, secret)) {
    res.status(401).json({ error: "Invalid signature" });
    return;
  }

  const params = new URLSearchParams(rawBody);
  const text = params.get("text") || "";
  const parsed = parseCommand(text);

  if ("error" in parsed) {
    res.status(200).json({ response_type: "ephemeral", text: parsed.error });
    return;
  }

  if (parsed.action === "help") {
    res.status(200).json({ response_type: "ephemeral", text: HELP_TEXT });
    return;
  }

  if (parsed.action === "status") {
    const ghRepo = process.env.GITHUB_REPO || "unknown/repo";
    res.status(200).json({
      response_type: "ephemeral",
      text: `<https://github.com/${ghRepo}/actions/workflows/bmad-start-run.yml|View BMAD Orchestrator runs>`,
    });
    return;
  }

  try {
    const ok = await dispatchWorkflow(parsed);
    if (!ok) {
      res.status(200).json({ response_type: "ephemeral", text: "Failed to dispatch workflow. Check GitHub token permissions." });
      return;
    }

    const ghRepo = process.env.GITHUB_REPO || "unknown/repo";
    const actionsUrl = `https://github.com/${ghRepo}/actions/workflows/bmad-start-run.yml`;
    const actionLabel = parsed.action === "retry" ? "Retry" : "Run";
    const parts = [`*${actionLabel} dispatched!*`, `Team: \`${parsed.teamId}\``];
    if (parsed.prompt) parts.push(`Prompt: "${parsed.prompt}"`);
    if (parsed.branch) parts.push(`Branch: \`${parsed.branch}\``);
    if (parsed.verbose) parts.push("Verbose: enabled");
    if (parsed.skipNodes.length) parts.push(`Skip: ${parsed.skipNodes.join(", ")}`);
    parts.push(`<${actionsUrl}|View workflow runs>`);

    res.status(200).json({ response_type: "in_channel", text: parts.join("\n") });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    res.status(200).json({ response_type: "ephemeral", text: `Error dispatching workflow: ${msg}` });
  }
}
