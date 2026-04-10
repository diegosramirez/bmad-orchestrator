/**
 * Read BMAD target repo slug from Jira issue custom field (same semantics as webhook_server).
 */
import api, { route } from '@forge/api';

/** Must match BMAD_JIRA_TARGET_REPO_CUSTOM_FIELD_ID / JiraService (default customfield_10112). */
export const TARGET_REPO_CUSTOM_FIELD =
  process.env.BMAD_JIRA_TARGET_REPO_CUSTOM_FIELD_ID || 'customfield_10080';

/**
 * Parse target-repo custom field from a Jira issue JSON `fields` object.
 * Supports string field, or object with .value / .name (select-style).
 */
export function parseTargetRepoFromIssueFields(fields) {
  if (!fields || typeof fields !== 'object') {
    return '';
  }
  const cf = fields[TARGET_REPO_CUSTOM_FIELD];
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
 * Fetches the issue as the current user and returns the target repo slug, or '' on failure.
 * Empty string means the webhook will fall back to DEFAULT_TARGET_REPO.
 */
export async function fetchTargetRepoSlugFromIssue(issueKey) {
  if (!issueKey || typeof issueKey !== 'string') {
    return '';
  }
  try {
    const response = await api.asUser().requestJira(
      route`/rest/api/3/issue/${issueKey}?fields=${TARGET_REPO_CUSTOM_FIELD}`,
    );
    if (!response.ok) {
      return '';
    }
    const issue = await response.json();
    return parseTargetRepoFromIssueFields(issue.fields || {});
  } catch (_err) {
    return '';
  }
}
