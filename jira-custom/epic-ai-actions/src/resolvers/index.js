import Resolver from '@forge/resolver';
import { fetchTargetRepoSlugFromIssue } from './jiraTargetRepo';

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
 * JSON body for /bmad/*-run: always issue_key; target_repo from customfield_10112 when set.
 */
async function buildForgePanelPayload(issueKey) {
  const slug = await fetchTargetRepoSlugFromIssue(issueKey);
  const payload = { issue_key: issueKey };
  if (slug) {
    payload.target_repo = slug;
  }
  return payload;
}

async function postBmadEndpoint(path, issueKey, failureLabel) {
  const { baseUrl, secret } = forgeWebhookConfig();
  if (!baseUrl || !secret) {
    return {
      ok: false,
      message:
        'BMAD_FORGE_WEBHOOK_URL (or BMAD_DISCOVERY_WEBHOOK_URL) and BMAD_FORGE_WEBHOOK_SECRET (or BMAD_DISCOVERY_WEBHOOK_SECRET) must be set for this Forge app.',
    };
  }

  const trimmed = baseUrl.replace(/\/$/, '');
  const url = `${trimmed}${path}`;
  const body = await buildForgePanelPayload(issueKey);

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-BMAD-Forge-Secret': secret,
    },
    body: JSON.stringify(body),
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
      message: data.message || res.statusText || failureLabel,
      ...data,
    };
  }

  return { ok: true, ...data };
}

resolver.define('runDiscovery', async (req) => {
  const issueKey = req.payload?.issueKey;
  if (!issueKey || typeof issueKey !== 'string') {
    return { ok: false, message: 'Missing issueKey' };
  }
  return postBmadEndpoint('/bmad/discovery-run', issueKey, 'Discovery request failed');
});

resolver.define('runArchitect', async (req) => {
  const issueKey = req.payload?.issueKey;
  if (!issueKey || typeof issueKey !== 'string') {
    return { ok: false, message: 'Missing issueKey' };
  }
  return postBmadEndpoint('/bmad/architect-run', issueKey, 'Architect request failed');
});

resolver.define('runStories', async (req) => {
  const issueKey = req.payload?.issueKey;
  if (!issueKey || typeof issueKey !== 'string') {
    return { ok: false, message: 'Missing issueKey' };
  }
  return postBmadEndpoint('/bmad/stories-run', issueKey, 'Stories request failed');
});

resolver.define('runDevelopment', async (req) => {
  const issueKey = req.payload?.issueKey;
  if (!issueKey || typeof issueKey !== 'string') {
    return { ok: false, message: 'Missing issueKey' };
  }
  return postBmadEndpoint('/bmad/dev-run', issueKey, 'Run development request failed');
});

export const handler = resolver.getDefinitions();
