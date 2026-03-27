import Resolver from '@forge/resolver';

const resolver = new Resolver();

/**
 * Base URL and secret for BMAD FastAPI webhooks (Discovery + Epic Architect).
 * Prefer BMAD_FORGE_*; BMAD_DISCOVERY_* kept for compatibility.
 */
function forgeWebhookConfig() {
  const baseUrl =
    process.env.BMAD_FORGE_WEBHOOK_URL || process.env.BMAD_DISCOVERY_WEBHOOK_URL;
  const secret =
    process.env.BMAD_FORGE_WEBHOOK_SECRET || process.env.BMAD_DISCOVERY_WEBHOOK_SECRET;
  return { baseUrl, secret };
}

/**
 * Dispatches BMAD Discovery (epic-only) via the FastAPI webhook.
 */
resolver.define('runDiscovery', async (req) => {
  const issueKey = req.payload?.issueKey;
  if (!issueKey || typeof issueKey !== 'string') {
    return { ok: false, message: 'Missing issueKey' };
  }

  const { baseUrl, secret } = forgeWebhookConfig();
  if (!baseUrl || !secret) {
    return {
      ok: false,
      message:
        'BMAD_FORGE_WEBHOOK_URL (or BMAD_DISCOVERY_WEBHOOK_URL) and BMAD_FORGE_WEBHOOK_SECRET (or BMAD_DISCOVERY_WEBHOOK_SECRET) must be set for this Forge app.',
    };
  }

  const trimmed = baseUrl.replace(/\/$/, '');
  const url = `${trimmed}/bmad/discovery-run`;

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-BMAD-Forge-Secret': secret,
    },
    body: JSON.stringify({ issue_key: issueKey }),
  });

  let data = {};
  try {
    data = await res.json();
  } catch (_e) {
    data = {};
  }

  if (!res.ok) {
    return {
      ok: false,
      status: res.status,
      message: data.message || res.statusText || 'Discovery request failed',
      ...data,
    };
  }

  return { ok: true, ...data };
});

/**
 * Dispatches Epic Architect (Design Architect) via POST /bmad/architect-run.
 */
resolver.define('runArchitect', async (req) => {
  const issueKey = req.payload?.issueKey;
  if (!issueKey || typeof issueKey !== 'string') {
    return { ok: false, message: 'Missing issueKey' };
  }

  const { baseUrl, secret } = forgeWebhookConfig();
  if (!baseUrl || !secret) {
    return {
      ok: false,
      message:
        'BMAD_FORGE_WEBHOOK_URL (or BMAD_DISCOVERY_WEBHOOK_URL) and BMAD_FORGE_WEBHOOK_SECRET (or BMAD_DISCOVERY_WEBHOOK_SECRET) must be set for this Forge app.',
    };
  }

  const trimmed = baseUrl.replace(/\/$/, '');
  const url = `${trimmed}/bmad/architect-run`;

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-BMAD-Forge-Secret': secret,
    },
    body: JSON.stringify({ issue_key: issueKey }),
  });

  let data = {};
  try {
    data = await res.json();
  } catch (_e) {
    data = {};
  }

  if (!res.ok) {
    return {
      ok: false,
      status: res.status,
      message: data.message || res.statusText || 'Architect request failed',
      ...data,
    };
  }

  return { ok: true, ...data };
});

/**
 * Dispatches epic story breakdown (N stories + party mode) via POST /bmad/stories-run.
 */
resolver.define('runStories', async (req) => {
  const issueKey = req.payload?.issueKey;
  if (!issueKey || typeof issueKey !== 'string') {
    return { ok: false, message: 'Missing issueKey' };
  }

  const { baseUrl, secret } = forgeWebhookConfig();
  if (!baseUrl || !secret) {
    return {
      ok: false,
      message:
        'BMAD_FORGE_WEBHOOK_URL (or BMAD_DISCOVERY_WEBHOOK_URL) and BMAD_FORGE_WEBHOOK_SECRET (or BMAD_DISCOVERY_WEBHOOK_SECRET) must be set for this Forge app.',
    };
  }

  const trimmed = baseUrl.replace(/\/$/, '');
  const url = `${trimmed}/bmad/stories-run`;

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-BMAD-Forge-Secret': secret,
    },
    body: JSON.stringify({ issue_key: issueKey }),
  });

  let data = {};
  try {
    data = await res.json();
  } catch (_e) {
    data = {};
  }

  if (!res.ok) {
    return {
      ok: false,
      status: res.status,
      message: data.message || res.statusText || 'Stories request failed',
      ...data,
    };
  }

  return { ok: true, ...data };
});

export const handler = resolver.getDefinitions();
