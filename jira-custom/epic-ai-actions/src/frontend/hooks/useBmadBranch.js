import { useEffect, useMemo, useState } from 'react';
import { requestJira } from '@forge/bridge';
import { BMAD_BRANCH_CUSTOM_FIELD } from '../constants';

/**
 * Normalize Jira REST value for the branch field (plain string or wrapped shape).
 */
function branchFieldToString(raw) {
  if (raw == null) {
    return '';
  }
  if (typeof raw === 'string') {
    return raw.trim();
  }
  if (typeof raw === 'object' && typeof raw.value === 'string') {
    return raw.value.trim();
  }
  return '';
}

/**
 * Loads BMAD Branch (customfield_10145) for the current issue.
 */
export function useBmadBranch(issueKey) {
  const [branch, setBranch] = useState('');
  const [loading, setLoading] = useState(Boolean(issueKey));
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!issueKey) {
      setBranch('');
      setLoading(false);
      setError(null);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    (async () => {
      try {
        const q = new URLSearchParams({
          fields: BMAD_BRANCH_CUSTOM_FIELD,
        });
        const path = `/rest/api/3/issue/${encodeURIComponent(issueKey)}?${q.toString()}`;
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
          const raw = data?.fields?.[BMAD_BRANCH_CUSTOM_FIELD];
          setBranch(branchFieldToString(raw));
        }
      } catch (e) {
        if (!cancelled) {
          setBranch('');
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

  const hasBranch = useMemo(() => branch.length > 0, [branch]);

  return {
    branch,
    hasBranch,
    loading,
    error,
  };
}
