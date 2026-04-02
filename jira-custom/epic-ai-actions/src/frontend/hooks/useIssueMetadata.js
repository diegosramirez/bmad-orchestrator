import { useEffect, useState } from 'react';
import { useProductContext } from '@forge/react';
import { requestJira } from '@forge/bridge';
import { EPIC_TYPE_NAMES, STORY_TYPE_NAMES } from '../constants/issueTypes';

/**
 * Current issue key from Forge context and issuetype.name from Jira REST.
 */
export function useIssueMetadata() {
  const context = useProductContext();
  const issueKey =
    context?.extension?.issue?.key ?? context?.extension?.issueKey ?? null;

  const [loading, setLoading] = useState(Boolean(issueKey));
  const [issueTypeName, setIssueTypeName] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!issueKey) {
      setLoading(false);
      setIssueTypeName(null);
      setError(null);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    (async () => {
      try {
        const path = `/rest/api/3/issue/${encodeURIComponent(issueKey)}?fields=issuetype`;
        const response = await requestJira(path, {
          method: 'GET',
          headers: { Accept: 'application/json' },
        });
        const data = await response.json();
        if (!response.ok) {
          const msg =
            data?.errorMessages?.join(' ') ||
            data?.errors ||
            `HTTP ${response.status}`;
          throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
        }
        if (!cancelled) {
          setIssueTypeName(data?.fields?.issuetype?.name ?? '');
        }
      } catch (e) {
        if (!cancelled) {
          setIssueTypeName(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [issueKey]);

  const normalized = (issueTypeName || '').trim().toLowerCase();
  const isEpic = EPIC_TYPE_NAMES.has(normalized);
  const isStory = STORY_TYPE_NAMES.has(normalized);

  return {
    issueKey,
    loading,
    error,
    issueTypeName,
    isEpic,
    isStory,
  };
}
