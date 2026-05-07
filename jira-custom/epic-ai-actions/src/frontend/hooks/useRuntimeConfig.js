import { useEffect, useState } from 'react';
import { invoke } from '@forge/bridge';

const DEFAULT_TARGET_REPO_FIELD_ID = 'customfield_10080';
const DEFAULT_BRANCH_FIELD_ID = 'customfield_10079';

/**
 * Loads runtime config from Forge resolver so frontend and backend use the same field ids.
 */
export function useRuntimeConfig() {
  const [config, setConfig] = useState({
    targetRepoFieldId: DEFAULT_TARGET_REPO_FIELD_ID,
    branchFieldId: DEFAULT_BRANCH_FIELD_ID,
  });

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const runtime = await invoke('getRuntimeConfig');
        if (!cancelled && runtime && typeof runtime === 'object') {
          setConfig({
            targetRepoFieldId:
              runtime.targetRepoFieldId || DEFAULT_TARGET_REPO_FIELD_ID,
            branchFieldId: runtime.branchFieldId || DEFAULT_BRANCH_FIELD_ID,
          });
        }
      } catch (_e) {
        // Keep defaults if resolver config is unavailable.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return config;
}
