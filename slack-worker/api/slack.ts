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
  slackThreadTs?: string;
  executionMode?: string;
  autoExecuteIssue?: boolean;
  codeAgent?: string;
}

interface RetryMeta {
  branch: string;
  team_id: string;
  target_repo: string;
  story_key: string;
  thread_ts?: string;
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

// ── Slack API helper ─────────────────────────────────────────────────────────

async function slackApi(method: string, body: Record<string, unknown>): Promise<any> {
  const token = process.env.SLACK_BOT_TOKEN;
  if (!token) throw new Error("SLACK_BOT_TOKEN not configured");
  const res = await fetch(`https://slack.com/api/${method}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  return res.json();
}

// ── Command parser ───────────────────────────────────────────────────────────

const HELP_TEXT = `*BMAD Orchestrator — Slash Commands*

\`/bmad\` — Open the run wizard (interactive form)
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

  if (!trimmed) {
    return { action: "help", teamId: "", prompt: "", verbose: false, skipNodes: [], branch: "", targetRepo: "" };
  }

  if (trimmed === "help") {
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

const SKIP_NODE_LABELS: Record<string, string> = {
  check_epic_state: "Check epic state",
  create_or_correct_epic: "Create/correct epic",
  create_story_tasks: "Create stories & tasks",
  party_mode_refinement: "Multi-agent refinement",
  detect_commands: "Detect build/test commands",
  dev_story: "Generate code",
  qa_automation: "Generate QA tests",
  code_review: "Code review",
  commit_and_push: "Commit & push",
  create_pull_request: "Create PR",
};

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
  if (cmd.slackThreadTs) inputs.slack_thread_ts = cmd.slackThreadTs;
  if (cmd.executionMode) inputs.execution_mode = cmd.executionMode;
  if (cmd.autoExecuteIssue) inputs.auto_execute_issue = "true";
  if (cmd.codeAgent) inputs.code_agent = cmd.codeAgent;

  if (cmd.action === "retry") {
    if (cmd.prompt) inputs.guidance = cmd.prompt;
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

  const url = `https://api.github.com/repos/${ghRepo}/actions/workflows/bmad-start-run.yml/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ghToken}`,
      Accept: "application/vnd.github.v3+json",
      "User-Agent": "bmad-slack-worker",
    },
    body: JSON.stringify({ ref: "main", inputs }),
  });

  if (res.status !== 204) {
    const body = await res.text();
    console.error(`GitHub dispatch failed: ${res.status} ${body} | URL: ${url} | Inputs: ${JSON.stringify(inputs)}`);
  }

  return res.status === 204;
}

// ── Modal definitions ────────────────────────────────────────────────────────

// Planning nodes run in both modes; execution nodes only apply to inline mode.
const PLANNING_NODES = [
  "check_epic_state", "create_or_correct_epic", "create_story_tasks",
  "party_mode_refinement", "detect_commands",
] as const;

const CODE_AGENT_OPTIONS = [
  {
    text: { type: "plain_text" as const, text: "BMAD Agents (inline pipeline)" },
    description: { type: "plain_text" as const, text: "Claude Agent SDK: dev, QA, code review, PR" },
    value: "inline",
  },
  {
    text: { type: "plain_text" as const, text: "GitHub Copilot" },
    description: { type: "plain_text" as const, text: "Assign issue to Copilot Coding Agent" },
    value: "copilot",
  },
];

const EXECUTION_MODE_OPTIONS = [
  {
    text: { type: "plain_text" as const, text: "Inline (full pipeline)" },
    description: { type: "plain_text" as const, text: "Plan, code, test, review, and create PR" },
    value: "inline",
  },
  {
    text: { type: "plain_text" as const, text: "GitHub Agent (plan + create Issue)" },
    description: { type: "plain_text" as const, text: "Plan and create a GitHub Issue for an external agent" },
    value: "github-agent",
  },
];

interface RunModalState {
  teamId?: string;
  prompt?: string;
  targetRepo?: string;
}

function buildRunModal(mode: string = "inline", prefill?: RunModalState): Record<string, unknown> {
  const defaultTeam = prefill?.teamId || process.env.DEFAULT_TEAM_ID || "SAM1";
  const defaultPrompt = prefill?.prompt || "";
  const defaultRepo = prefill?.targetRepo || process.env.DEFAULT_TARGET_REPO || "";

  const selectedMode = EXECUTION_MODE_OPTIONS.find((o) => o.value === mode) || EXECUTION_MODE_OPTIONS[0];

  const skipNodeNames = mode === "github-agent"
    ? PLANNING_NODES
    : SKIP_NODE_NAMES;

  const blocks: Record<string, unknown>[] = [
    {
      type: "input",
      block_id: "team_id",
      label: { type: "plain_text", text: "Team ID" },
      element: {
        type: "plain_text_input",
        action_id: "value",
        initial_value: defaultTeam,
      },
    },
    {
      type: "input",
      block_id: "prompt",
      label: { type: "plain_text", text: "Prompt" },
      element: {
        type: "plain_text_input",
        action_id: "value",
        ...(defaultPrompt ? { initial_value: defaultPrompt } : {}),
        placeholder: { type: "plain_text", text: "Feature description or Jira key (e.g. SAM1-54)" },
      },
    },
    {
      type: "input",
      block_id: "target_repo",
      optional: true,
      label: { type: "plain_text", text: "Target Repository" },
      element: {
        type: "plain_text_input",
        action_id: "value",
        initial_value: defaultRepo,
        placeholder: { type: "plain_text", text: "owner/repo" },
      },
    },
    {
      type: "input",
      block_id: "options",
      optional: true,
      label: { type: "plain_text", text: "Options" },
      element: {
        type: "checkboxes",
        action_id: "value",
        options: [
          {
            text: { type: "plain_text", text: "Verbose mode" },
            description: { type: "plain_text", text: "Stream agent events to Slack thread" },
            value: "verbose",
          },
        ],
      },
    },
    {
      type: "input",
      block_id: "execution_mode",
      dispatch_action: true,
      optional: true,
      label: { type: "plain_text", text: "Execution Mode" },
      element: {
        type: "static_select",
        action_id: "execution_mode_select",
        initial_option: selectedMode,
        options: EXECUTION_MODE_OPTIONS,
      },
    },
  ];

  // GitHub Agent options: only shown when GitHub Agent mode is selected
  if (mode === "github-agent") {
    blocks.push(
      {
        type: "input",
        block_id: "code_agent",
        optional: true,
        label: { type: "plain_text", text: "Code Agent" },
        element: {
          type: "static_select",
          action_id: "value",
          initial_option: CODE_AGENT_OPTIONS[0],
          options: CODE_AGENT_OPTIONS,
        },
      },
      {
        type: "input",
        block_id: "auto_execute",
        optional: true,
        label: { type: "plain_text", text: "Auto-Execute" },
        element: {
          type: "checkboxes",
          action_id: "value",
          options: [
            {
              text: { type: "plain_text", text: "Auto-execute issue" },
              description: { type: "plain_text", text: "Skip review — trigger code generation immediately after issue creation" },
              value: "auto_execute",
            },
          ],
        },
      },
    );
  }

  blocks.push({
    type: "input",
    block_id: "skip_nodes",
    optional: true,
    label: { type: "plain_text", text: "Skip Nodes" },
    element: {
      type: "checkboxes",
      action_id: "value",
      options: skipNodeNames.map((name) => ({
        text: { type: "plain_text", text: SKIP_NODE_LABELS[name] || name },
        value: name,
      })),
    },
  });

  return {
    type: "modal",
    callback_id: "bmad_run_modal",
    title: { type: "plain_text", text: "BMAD — New Run" },
    submit: { type: "plain_text", text: "Run" },
    close: { type: "plain_text", text: "Cancel" },
    blocks,
  };
}

function buildRetryModal(meta: RetryMeta): Record<string, unknown> {
  return {
    type: "modal",
    callback_id: "bmad_retry_modal",
    private_metadata: JSON.stringify(meta),
    title: { type: "plain_text", text: "BMAD — Retry Run" },
    submit: { type: "plain_text", text: "Retry" },
    close: { type: "plain_text", text: "Cancel" },
    blocks: [
      {
        type: "context",
        elements: [
          { type: "mrkdwn", text: `*Branch:* \`${meta.branch}\`` },
          { type: "mrkdwn", text: `*Team:* ${meta.team_id}` },
          ...(meta.story_key ? [{ type: "mrkdwn", text: `*Story:* ${meta.story_key}` }] : []),
        ],
      },
      {
        type: "input",
        block_id: "guidance",
        optional: true,
        label: { type: "plain_text", text: "Guidance" },
        element: {
          type: "plain_text_input",
          action_id: "value",
          multiline: true,
          placeholder: { type: "plain_text", text: "Optional: tell the agent what to fix or focus on" },
        },
      },
    ],
  };
}

function buildRefineModal(meta: RetryMeta): Record<string, unknown> {
  return {
    type: "modal",
    callback_id: "bmad_refine_modal",
    private_metadata: JSON.stringify(meta),
    title: { type: "plain_text", text: "BMAD — Refine PR" },
    submit: { type: "plain_text", text: "Refine" },
    close: { type: "plain_text", text: "Cancel" },
    blocks: [
      {
        type: "context",
        elements: [
          { type: "mrkdwn", text: `*Branch:* \`${meta.branch}\`` },
          { type: "mrkdwn", text: `*Team:* ${meta.team_id}` },
          ...(meta.story_key ? [{ type: "mrkdwn", text: `*Story:* ${meta.story_key}` }] : []),
        ],
      },
      {
        type: "input",
        block_id: "guidance",
        label: { type: "plain_text", text: "Refinement guidance" },
        element: {
          type: "plain_text_input",
          action_id: "value",
          multiline: true,
          placeholder: { type: "plain_text", text: "What should the agent change or improve?" },
        },
      },
    ],
  };
}

// ── Payload handlers ─────────────────────────────────────────────────────────

async function handleSlashCommand(params: URLSearchParams, res: any): Promise<void> {
  const text = params.get("text") || "";
  const triggerId = params.get("trigger_id") || "";

  // Empty text → open wizard modal
  if (!text.trim()) {
    if (!triggerId) {
      res.status(200).json({ response_type: "ephemeral", text: "Missing trigger_id — cannot open modal." });
      return;
    }
    const result = await slackApi("views.open", {
      trigger_id: triggerId,
      view: buildRunModal(),
    });
    if (!result.ok) {
      res.status(200).json({ response_type: "ephemeral", text: `Failed to open modal: ${result.error}` });
      return;
    }
    // Acknowledge — modal is open, nothing to show in chat
    res.status(200).send("");
    return;
  }

  // Text provided → parse and dispatch (existing behavior)
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

async function handleBlockActions(payload: any, res: any): Promise<void> {
  const action = payload.actions?.[0];
  if (!action) {
    res.status(200).send("");
    return;
  }

  // Execution mode changed → rebuild modal with correct skip nodes
  if (action.action_id === "execution_mode_select") {
    const selectedMode = action.selected_option?.value || "inline";
    const viewId = payload.view?.id;
    const viewHash = payload.view?.hash;
    if (viewId) {
      // Preserve user's current input values across the rebuild
      const vals = payload.view?.state?.values || {};
      const prefill: RunModalState = {
        teamId: vals.team_id?.value?.value || undefined,
        prompt: vals.prompt?.value?.value || undefined,
        targetRepo: vals.target_repo?.value?.value || undefined,
      };
      await slackApi("views.update", {
        view_id: viewId,
        hash: viewHash,
        view: buildRunModal(selectedMode, prefill),
      });
    }
    res.status(200).send("");
    return;
  }

  // Both retry and refine follow the same pattern: parse meta → open modal
  let modalView: Record<string, unknown> | null = null;
  if (action.action_id === "bmad_retry") {
    let meta: RetryMeta;
    try { meta = JSON.parse(action.value); } catch { res.status(200).send(""); return; }
    modalView = buildRetryModal(meta);
  } else if (action.action_id === "bmad_refine") {
    let meta: RetryMeta;
    try { meta = JSON.parse(action.value); } catch { res.status(200).send(""); return; }
    modalView = buildRefineModal(meta);
  }

  if (!modalView) {
    console.error("handleBlockActions: unknown action_id", action.action_id);
    res.status(200).send("");
    return;
  }

  console.log("handleBlockActions: opening modal for", action.action_id);

  const result = await slackApi("views.open", {
    trigger_id: payload.trigger_id,
    view: modalView,
  });

  if (!result.ok) {
    console.error("views.open failed:", JSON.stringify(result));
    const responseUrl = payload.response_url;
    if (responseUrl) {
      await fetch(responseUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ response_type: "ephemeral", text: `Failed to open modal: ${result.error}` }),
      });
    }
  }

  res.status(200).send("");
}

async function handleViewSubmission(payload: any, res: any): Promise<void> {
  const callbackId = payload.view?.callback_id;
  const values = payload.view?.state?.values || {};

  if (callbackId === "bmad_run_modal") {
    // Slack values structure: values[block_id][action_id].value
    const teamId = values.team_id?.value?.value || process.env.DEFAULT_TEAM_ID || "";
    const prompt = values.prompt?.value?.value || "";
    const targetRepo = values.target_repo?.value?.value || "";
    const selectedOptions = values.options?.value?.selected_options || [];
    const verbose = selectedOptions.some((o: any) => o.value === "verbose");
    const skipNodes = (values.skip_nodes?.value?.selected_options || []).map((o: any) => o.value);
    const executionMode = values.execution_mode?.execution_mode_select?.selected_option?.value || "inline";
    const autoExecuteOptions = values.auto_execute?.value?.selected_options || [];
    const autoExecuteIssue = autoExecuteOptions.some((o: any) => o.value === "auto_execute");
    const codeAgent = values.code_agent?.value?.selected_option?.value || undefined;

    const cmd: ParsedCommand = {
      action: "run",
      teamId,
      prompt,
      verbose,
      skipNodes,
      branch: "",
      targetRepo,
      executionMode,
      autoExecuteIssue,
      codeAgent,
    };

    // Dispatch BEFORE responding — Vercel kills the function after res is sent
    let ok = false;
    try {
      ok = await dispatchWorkflow(cmd);
    } catch {
      // fall through with ok=false
    }

    // Send DM confirmation to user
    const userId = payload.user?.id;
    const ghRepo = process.env.GITHUB_REPO || "unknown/repo";
    const actionsUrl = `https://github.com/${ghRepo}/actions/workflows/bmad-start-run.yml`;
    const statusText = ok
      ? `*Run dispatched!*\nTeam: \`${teamId}\`\nPrompt: "${prompt}"\n<${actionsUrl}|View workflow runs>`
      : "Failed to dispatch workflow. Check GitHub token permissions.";

    if (userId) {
      try {
        await slackApi("chat.postMessage", { channel: userId, text: statusText });
      } catch {
        // best-effort
      }
    }

    // Close modal
    res.status(200).json({ response_action: "clear" });
    return;
  }

  if (callbackId === "bmad_retry_modal") {
    let meta: RetryMeta;
    try {
      meta = JSON.parse(payload.view?.private_metadata || "{}");
    } catch {
      res.status(200).json({ response_action: "clear" });
      return;
    }

    const guidance = values.guidance?.value?.value || "";

    // Guard: retry requires a branch — if missing, the failure happened before
    // code was committed so there's nothing to retry from.
    if (!meta.branch) {
      const userId = payload.user?.id;
      if (userId) {
        try {
          await slackApi("chat.postMessage", {
            channel: userId,
            text: "Cannot retry: no branch exists. The failure happened before code was committed — please start a new run instead.",
          });
        } catch { /* best-effort */ }
      }
      res.status(200).json({ response_action: "clear" });
      return;
    }

    const cmd: ParsedCommand = {
      action: "retry",
      teamId: meta.team_id,
      prompt: guidance,
      verbose: false,
      skipNodes: [],
      branch: meta.branch,
      targetRepo: meta.target_repo,
      slackThreadTs: meta.thread_ts,
    };

    // Dispatch BEFORE responding — Vercel kills the function after res is sent
    let ok = false;
    try {
      ok = await dispatchWorkflow(cmd);
    } catch {
      // fall through with ok=false
    }

    const userId = payload.user?.id;
    const ghRepo = process.env.GITHUB_REPO || "unknown/repo";
    const actionsUrl = `https://github.com/${ghRepo}/actions/workflows/bmad-start-run.yml`;
    const statusText = ok
      ? `*Retry dispatched!*\nBranch: \`${meta.branch}\`${guidance ? `\nGuidance: "${guidance}"` : ""}\n<${actionsUrl}|View workflow runs>`
      : "Failed to dispatch retry. Check GitHub token permissions.";

    if (userId) {
      try {
        await slackApi("chat.postMessage", { channel: userId, text: statusText });
      } catch {
        // best-effort
      }
    }

    // Close modal
    res.status(200).json({ response_action: "clear" });
    return;
  }

  if (callbackId === "bmad_refine_modal") {
    let meta: RetryMeta;
    try {
      meta = JSON.parse(payload.view?.private_metadata || "{}");
    } catch {
      res.status(200).json({ response_action: "clear" });
      return;
    }

    const guidance = values.guidance?.value?.value || "";

    if (!meta.branch) {
      const userId = payload.user?.id;
      if (userId) {
        try {
          await slackApi("chat.postMessage", {
            channel: userId,
            text: "Cannot refine: no branch found in metadata.",
          });
        } catch { /* best-effort */ }
      }
      res.status(200).json({ response_action: "clear" });
      return;
    }

    const cmd: ParsedCommand = {
      action: "retry",
      teamId: meta.team_id,
      prompt: guidance,
      verbose: false,
      skipNodes: [],
      branch: meta.branch,
      targetRepo: meta.target_repo,
      slackThreadTs: meta.thread_ts,
    };

    let ok = false;
    try {
      ok = await dispatchWorkflow(cmd);
    } catch {
      // fall through with ok=false
    }

    const userId = payload.user?.id;
    const ghRepo = process.env.GITHUB_REPO || "unknown/repo";
    const actionsUrl = `https://github.com/${ghRepo}/actions/workflows/bmad-start-run.yml`;
    const statusText = ok
      ? `*Refine dispatched!*\nBranch: \`${meta.branch}\`\nGuidance: "${guidance}"\n<${actionsUrl}|View workflow runs>`
      : "Failed to dispatch refine. Check GitHub token permissions.";

    if (userId) {
      try {
        await slackApi("chat.postMessage", { channel: userId, text: statusText });
      } catch {
        // best-effort
      }
    }

    res.status(200).json({ response_action: "clear" });
    return;
  }

  // Unknown callback
  res.status(200).send("");
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

  const rawBody = await readRawBody(req);
  const timestamp = req.headers["x-slack-request-timestamp"] as string;
  const signature = req.headers["x-slack-signature"] as string;

  if (!timestamp || !signature || !verifySlackSignature(rawBody, timestamp, signature, secret)) {
    res.status(401).json({ error: "Invalid signature" });
    return;
  }

  const params = new URLSearchParams(rawBody);

  // ── Route by payload type ────────────────────────────────────────────────
  // Interactive payloads (button clicks, modal submissions) come as a JSON
  // string in a "payload" form field.
  const payloadStr = params.get("payload");
  if (payloadStr) {
    let payload: any;
    try {
      payload = JSON.parse(payloadStr);
    } catch {
      res.status(400).json({ error: "Invalid payload" });
      return;
    }

    const type = payload.type;
    if (type === "block_actions") {
      await handleBlockActions(payload, res);
      return;
    }
    if (type === "view_submission") {
      await handleViewSubmission(payload, res);
      return;
    }

    // Unknown interactive payload type
    res.status(200).send("");
    return;
  }

  // ── Slash command (no payload field) ─────────────────────────────────────
  await handleSlashCommand(params, res);
}
