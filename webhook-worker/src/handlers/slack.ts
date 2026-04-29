import { createHmac, timingSafeEqual } from "node:crypto";

import { getGitHubAuth } from "../lib/github-auth.js";

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
  slackChannel?: string;
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

const HELP_TEXT = `*BMAD Orchestrator — Commands*

*Slash commands (any channel):*
\`/bmad\` — Open the run wizard (interactive form)
\`/bmad run <team> "<prompt>"\` — Start a new orchestrator run
\`/bmad run <team> "<prompt>" --verbose\` — Start with verbose Slack updates
\`/bmad run <team> "<prompt>" --skip dev_story,qa_automation\` — Skip specific nodes
\`/bmad run <team> "<prompt>" --target <owner/repo>\` — Override target repository
\`/bmad retry <team> <branch> "<guidance>"\` — Retry a failed run on an existing branch
\`/bmad status\` — Link to GitHub Actions runs
\`/bmad help\` — Show this message

*DM the bot (under Apps → BMAD Orchestrator):*
Just type your prompt and I'll start a run with the default team.
\`Add user dashboard with analytics\` — Starts a run
\`run SAM1 "Add SSO login"\` — Explicit team + prompt
\`retry SAM1 bmad/sam1/SAM1-54 "fix tests"\` — Retry a failed branch
\`status\` — Link to workflow runs
\`help\` — Show this message

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
  e2e_automation: "E2E tests (Playwright)",
  commit_and_push: "Commit & push",
  create_pull_request: "Create PR",
};

const RETRY_SKIP_NODES = [
  "check_epic_state", "create_or_correct_epic",
  "create_story_tasks", "party_mode_refinement",
];

async function dispatchWorkflow(cmd: ParsedCommand): Promise<boolean> {
  const ghRepo = process.env.GITHUB_REPO;
  if (!ghRepo) {
    throw new Error("GITHUB_REPO must be configured");
  }
  const authHeader = await getGitHubAuth().getAuthHeader();

  const inputs: Record<string, string> = {
    target_repo: cmd.targetRepo || process.env.DEFAULT_TARGET_REPO || "",
    team_id: cmd.teamId || process.env.DEFAULT_TEAM_ID || "",
    prompt: cmd.prompt,
    slack_verbose: cmd.verbose ? "true" : "false",
  };

  if (cmd.branch) inputs.branch = cmd.branch;
  if (cmd.slackThreadTs) inputs.slack_thread_ts = cmd.slackThreadTs;
  if (cmd.slackChannel) inputs.slack_channel = cmd.slackChannel;
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
      Authorization: authHeader,
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

function buildRunModal(mode: string = "inline", prefill?: RunModalState, autoExecute: boolean = false): Record<string, unknown> {
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
    blocks.push({
      type: "input",
      block_id: "auto_execute",
      dispatch_action: true,
      optional: true,
      label: { type: "plain_text", text: "Auto-Execute" },
      element: {
        type: "checkboxes",
        action_id: "auto_execute_toggle",
        options: [
          {
            text: { type: "plain_text", text: "Auto-execute issue" },
            description: { type: "plain_text", text: "Skip review — trigger code generation immediately after issue creation" },
            value: "auto_execute",
          },
        ],
        ...(autoExecute ? {
          initial_options: [{
            text: { type: "plain_text", text: "Auto-execute issue" },
            description: { type: "plain_text", text: "Skip review — trigger code generation immediately after issue creation" },
            value: "auto_execute",
          }],
        } : {}),
      },
    });

    // Code agent dropdown: only shown when auto-execute is checked
    if (autoExecute) {
      blocks.push({
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
      });
    }
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

  // Execution mode or auto-execute changed → rebuild modal
  if (action.action_id === "execution_mode_select" || action.action_id === "auto_execute_toggle") {
    const viewId = payload.view?.id;
    const viewHash = payload.view?.hash;
    if (viewId) {
      const vals = payload.view?.state?.values || {};
      const prefill: RunModalState = {
        teamId: vals.team_id?.value?.value || undefined,
        prompt: vals.prompt?.value?.value || undefined,
        targetRepo: vals.target_repo?.value?.value || undefined,
      };

      // Determine current mode and auto-execute state
      let selectedMode: string;
      let isAutoExecute: boolean;

      if (action.action_id === "execution_mode_select") {
        selectedMode = action.selected_option?.value || "inline";
        // Reset auto-execute when switching modes
        isAutoExecute = false;
      } else {
        // auto_execute_toggle — read current mode from state
        selectedMode = vals.execution_mode?.execution_mode_select?.selected_option?.value || "inline";
        const selected = action.selected_options || [];
        isAutoExecute = selected.some((o: any) => o.value === "auto_execute");
      }

      await slackApi("views.update", {
        view_id: viewId,
        hash: viewHash,
        view: buildRunModal(selectedMode, prefill, isAutoExecute),
      });
    }
    res.status(200).send("");
    return;
  }

  // DM button → open run wizard pre-filled with typed text
  if (action.action_id === "open_run_modal_dm") {
    let prefill: RunModalState = {};
    let dmChannel = payload.channel?.id || "";
    try {
      const parsed = JSON.parse(action.value || "{}");
      prefill = { prompt: parsed.prompt || "", teamId: parsed.teamId || process.env.DEFAULT_TEAM_ID || "SAM1" };
    } catch { /* use empty prefill */ }
    const modal = buildRunModal("inline", prefill);
    // Store DM channel so the submission can thread replies back here
    (modal as any).private_metadata = JSON.stringify({ dm_channel: dmChannel });
    const result = await slackApi("views.open", {
      trigger_id: payload.trigger_id,
      view: modal,
    });
    if (!result.ok) {
      console.error("views.open failed for open_run_modal_dm:", JSON.stringify(result));
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
    const autoExecuteOptions = values.auto_execute?.auto_execute_toggle?.selected_options || [];
    const autoExecuteIssue = autoExecuteOptions.some((o: any) => o.value === "auto_execute");
    const codeAgent = values.code_agent?.value?.selected_option?.value || undefined;

    // If the modal was opened from a DM, private_metadata contains the DM channel.
    // Post an initial thread-root message there so workflow updates land in-thread.
    let dmChannel = "";
    let slackThreadTs: string | undefined;
    try {
      const meta = JSON.parse(payload.view?.private_metadata || "{}");
      dmChannel = meta.dm_channel || "";
    } catch { /* ok */ }

    if (dmChannel) {
      try {
        const initMsg = await slackApi("chat.postMessage", {
          channel: dmChannel,
          text: `🚀 *Run starting…*\nTeam: \`${teamId}\`\nPrompt: "${prompt}"`,
        });
        if (initMsg.ok) slackThreadTs = initMsg.ts;
      } catch { /* best-effort */ }
    }

    const cmd: ParsedCommand = {
      action: "run",
      teamId,
      prompt,
      verbose: verbose,
      skipNodes,
      branch: "",
      targetRepo,
      executionMode,
      autoExecuteIssue,
      codeAgent,
      slackThreadTs,
      slackChannel: dmChannel || undefined,
    };

    // Dispatch BEFORE responding — Vercel kills the function after res is sent
    let ok = false;
    try {
      ok = await dispatchWorkflow(cmd);
    } catch {
      // fall through with ok=false
    }

    if (!ok) {
      // Post failure notice to wherever the user will see it
      const notifyChannel = dmChannel || payload.user?.id;
      if (notifyChannel) {
        try {
          await slackApi("chat.postMessage", {
            channel: notifyChannel,
            text: "❌ Failed to dispatch workflow. Check GitHub token permissions.",
            ...(slackThreadTs ? { thread_ts: slackThreadTs } : {}),
          });
        } catch { /* best-effort */ }
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

// ── DM (Events API) handler ─────────────────────────────────────────────────

async function handleDirectMessage(event: any): Promise<void> {
  // Ignore bot's own messages and message edits/deletes
  if (event.bot_id || event.subtype) return;

  const text = (event.text || "").trim();
  const channel = event.channel;  // DM channel ID
  const userTs = event.ts;        // message timestamp — used as thread parent

  if (!text || !channel) return;

  // Helper: reply in the DM thread
  const reply = async (msg: string, threadTs?: string) => {
    await slackApi("chat.postMessage", {
      channel,
      text: msg,
      ...(threadTs ? { thread_ts: threadTs } : {}),
    });
  };

  // ── Parse: try structured command first, fall back to modal prompt ──────
  const parsed = parseCommand(text);

  if ("error" in parsed) {
    // Any unrecognised text → offer the run wizard modal with the text pre-filled.
    // (Slack requires a trigger_id to open modals, which only comes from button
    // clicks — so we post a button and the modal opens on click.)
    const defaultTeam = process.env.DEFAULT_TEAM_ID || "SAM1";
    await slackApi("chat.postMessage", {
      channel,
      text: "Open the run wizard to configure and start a pipeline run:",
      blocks: [
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: `Got it! Open the wizard to review options and kick off a run.`,
          },
        },
        {
          type: "actions",
          elements: [
            {
              type: "button",
              style: "primary",
              text: { type: "plain_text", text: "Open Run Wizard" },
              action_id: "open_run_modal_dm",
              value: JSON.stringify({ prompt: text, teamId: defaultTeam }),
            },
          ],
        },
      ],
    });
    return;
  }

  // ── Structured commands ─────────────────────────────────────────────────

  if (parsed.action === "help") {
    await reply(HELP_TEXT);
    return;
  }

  if (parsed.action === "status") {
    const ghRepo = process.env.GITHUB_REPO || "unknown/repo";
    await reply(`<https://github.com/${ghRepo}/actions/workflows/bmad-start-run.yml|View BMAD Orchestrator runs>`);
    return;
  }

  // run or retry — dispatch and reply in thread
  parsed.slackThreadTs = userTs;
  if (!parsed.targetRepo) parsed.targetRepo = process.env.DEFAULT_TARGET_REPO || "";

  const actionLabel = parsed.action === "retry" ? "Retry" : "Run";
  const parts = [`🚀 *${actionLabel} starting…*`, `Team: \`${parsed.teamId}\``];
  if (parsed.prompt) parts.push(`Prompt: "${parsed.prompt}"`);
  if (parsed.branch) parts.push(`Branch: \`${parsed.branch}\``);
  if (parsed.skipNodes.length) parts.push(`Skip: ${parsed.skipNodes.join(", ")}`);

  await reply(parts.join("\n"), userTs);

  try {
    const ok = await dispatchWorkflow(parsed);
    if (!ok) {
      await reply("❌ Failed to dispatch workflow. Check GitHub token permissions.", userTs);
      return;
    }
    const ghRepo = process.env.GITHUB_REPO || "unknown/repo";
    await reply(
      `✅ Dispatched! <https://github.com/${ghRepo}/actions/workflows/bmad-start-run.yml|View workflow runs>`,
      userTs,
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    await reply(`❌ Error: ${msg}`, userTs);
  }
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

  // ── Events API (JSON body) ──────────────────────────────────────────────
  // Slack Events API sends JSON, not form-encoded. Detect by trying to parse.
  let jsonBody: any = null;
  try {
    jsonBody = JSON.parse(rawBody);
  } catch {
    // Not JSON — fall through to form-encoded handling below
  }

  if (jsonBody) {
    // URL verification challenge (one-time setup handshake)
    if (jsonBody.type === "url_verification") {
      res.status(200).json({ challenge: jsonBody.challenge });
      return;
    }

    // Slack retries — acknowledge and skip
    if (req.headers["x-slack-retry-num"]) {
      res.status(200).send("");
      return;
    }

    // Event callback (DM messages, etc.)
    if (jsonBody.type === "event_callback") {
      const event = jsonBody.event;

      // Process BEFORE responding — Vercel kills the function after res.send()
      if (event?.type === "message" && event?.channel_type === "im") {
        try {
          await handleDirectMessage(event);
        } catch (err) {
          console.error("handleDirectMessage error:", err);
        }
      }

      res.status(200).send("");
      return;
    }
  }

  // ── Form-encoded payloads (slash commands, interactive components) ──────
  const params = new URLSearchParams(rawBody);

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
