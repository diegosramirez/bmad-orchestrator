/**
 * webhook-worker HTTP server.
 *
 * Runs on Cloud Run (or anything that speaks HTTP on $PORT). Routes incoming
 * requests to handler modules whose signatures match the Vercel Functions shape
 * `(req, res) => Promise<void>` so the same handler code runs unchanged.
 */
import { createServer, IncomingMessage, ServerResponse } from "node:http";

import jiraCommentHandler from "./handlers/jira-comment.js";
import jiraIssueHandler from "./handlers/jira-issue.js";
import slackHandler from "./handlers/slack.js";
import workflowArchitectRunHandler from "./handlers/workflow-architect-run.js";
import workflowDevRunHandler from "./handlers/workflow-dev-run.js";
import workflowDiscoveryRunHandler from "./handlers/workflow-discovery-run.js";
import workflowStoriesRunHandler from "./handlers/workflow-stories-run.js";

// ── Vercel-compatible response shim ────────────────────────────────────────
// Handler code written for Vercel expects res.status(n).json(obj) and res.send(str)
// chaining. Node's ServerResponse does not provide these — we attach them here.

interface VercelLikeResponse extends ServerResponse {
  status(code: number): VercelLikeResponse;
  json(body: unknown): void;
  send(body: unknown): void;
}

function wrapResponse(res: ServerResponse): VercelLikeResponse {
  const r = res as VercelLikeResponse;
  r.status = (code: number) => {
    r.statusCode = code;
    return r;
  };
  r.json = (body: unknown) => {
    if (!r.getHeader("Content-Type")) {
      r.setHeader("Content-Type", "application/json; charset=utf-8");
    }
    r.end(JSON.stringify(body));
  };
  r.send = (body: unknown) => {
    if (body === undefined || body === null) {
      r.end();
      return;
    }
    if (typeof body === "string" || Buffer.isBuffer(body)) {
      r.end(body);
      return;
    }
    if (!r.getHeader("Content-Type")) {
      r.setHeader("Content-Type", "application/json; charset=utf-8");
    }
    r.end(JSON.stringify(body));
  };
  return r;
}

// ── Routing table ──────────────────────────────────────────────────────────
// Mirrors the 10 rewrites in the original slack-worker/vercel.json exactly.

type Handler = (req: IncomingMessage, res: VercelLikeResponse) => Promise<void>;

const routes: Record<string, Handler> = {
  // Slack slash commands + interactivity + Events API
  "/api/slack": slackHandler,

  // Jira native webhooks
  "/bmad/jira-webhook": jiraIssueHandler,
  "/bmad/jira-comment-webhook": jiraCommentHandler,

  // Forge panel routes (current and legacy paths)
  "/workflow/discovery-run": workflowDiscoveryRunHandler,
  "/workflow/architect-run": workflowArchitectRunHandler,
  "/workflow/stories-run": workflowStoriesRunHandler,
  "/workflow/dev-run": workflowDevRunHandler,
  "/bmad/discovery-run": workflowDiscoveryRunHandler,
  "/bmad/architect-run": workflowArchitectRunHandler,
  "/bmad/stories-run": workflowStoriesRunHandler,
  "/bmad/dev-run": workflowDevRunHandler,
};

// ── Server ─────────────────────────────────────────────────────────────────

const port = Number(process.env.PORT || 8080);
const host = "0.0.0.0";

const server = createServer(async (req, rawRes) => {
  const res = wrapResponse(rawRes);
  const url = req.url || "/";
  const path = url.split("?", 1)[0];

  // Cloud Run / uptime probes
  if (path === "/healthz" || path === "/") {
    res.status(200).json({ ok: true });
    return;
  }

  const handler = routes[path];
  if (!handler) {
    res.status(404).json({ error: "Not found", path });
    return;
  }

  try {
    await handler(req, res);
  } catch (err) {
    console.error(`handler error on ${path}:`, err);
    if (!res.headersSent) {
      res.status(500).json({ error: "Internal server error" });
    } else if (!res.writableEnded) {
      res.end();
    }
  }
});

server.listen(port, host, () => {
  console.log(`webhook-worker listening on http://${host}:${port}`);
});

// Graceful shutdown — Cloud Run sends SIGTERM 10s before hard kill.
function shutdown(signal: string): void {
  console.log(`received ${signal}, closing server…`);
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 8000).unref();
}
process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
