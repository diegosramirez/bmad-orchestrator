import Resolver from '@forge/resolver';

const resolver = new Resolver();

/**
 * Dispatches BMAD Discovery (epic-only) via the FastAPI webhook.
 * Configure Forge environment variables:
 * - BMAD_DISCOVERY_WEBHOOK_URL — base URL, e.g. https://host:port (no trailing path)
 * - BMAD_DISCOVERY_WEBHOOK_SECRET — same value as BMAD_DISCOVERY_WEBHOOK_SECRET on the server
 */
resolver.define('runDiscovery', async (req) => {
  const issueKey = req.payload?.issueKey;
  if (!issueKey || typeof issueKey !== 'string') {
    return { ok: false, message: 'Missing issueKey' };
  }

  const baseUrl = process.env.BMAD_DISCOVERY_WEBHOOK_URL;
  console.log('baseUrl', baseUrl);
  const secret = process.env.BMAD_DISCOVERY_WEBHOOK_SECRET;
  console.log('secret', secret);
  if (!baseUrl || !secret) {
    return {
      ok: false,
      message:
        'BMAD_DISCOVERY_WEBHOOK_URL or BMAD_DISCOVERY_WEBHOOK_SECRET is not set for this Forge app.',
    };
  }

  const trimmed = baseUrl.replace(/\/$/, '');
  const url = `${trimmed}/bmad/discovery-run`;

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-BMAD-Discovery-Secret': secret,
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

export const handler = resolver.getDefinitions();
