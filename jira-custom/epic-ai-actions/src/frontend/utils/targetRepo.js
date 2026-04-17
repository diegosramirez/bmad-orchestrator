import { requestJira } from '@forge/bridge';
import { BMAD_TARGET_REPO_CUSTOM_FIELD } from '../constants';

/**
 * Normalize Jira REST value for the target-repo field (string or select-style object).
 * Mirrors resolvers/jiraTargetRepo.js for a single raw field.
 */
export function parseTargetRepoRaw(cf) {
  if (typeof cf === 'string' && cf.trim()) {
    return cf.trim();
  }
  if (cf && typeof cf === 'object') {
    if (typeof cf.value === 'string' && cf.value.trim()) {
      return cf.value.trim();
    }
    if (typeof cf.name === 'string' && cf.name.trim()) {
      return cf.name.trim();
    }
  }
  return '';
}

/**
 * Loads the BMAD target repository slug for an issue (Forge UI, same semantics as backend).
 */
export async function fetchTargetRepoSlugForIssue(issueKey) {
  if (!issueKey || typeof issueKey !== 'string') {
    return '';
  }
  try {
    const q = new URLSearchParams({
      fields: BMAD_TARGET_REPO_CUSTOM_FIELD,
    });
    const path = `/rest/api/3/issue/${encodeURIComponent(issueKey)}?${q.toString()}`;
    const response = await requestJira(path, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    const data = await response.json();
    if (!response.ok) {
      return '';
    }
    const raw = data?.fields?.[BMAD_TARGET_REPO_CUSTOM_FIELD];
    return parseTargetRepoRaw(raw);
  } catch (_e) {
    return '';
  }
}
