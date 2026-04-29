import { useMemo, useState } from 'react';
import { useProductContext } from '@forge/react';
import { invoke } from '@forge/bridge';
import { TARGET_REPO_REQUIRED_MESSAGE_EPIC } from '../../bmadTargetRepoMessages';
import { ACTION_LABELS, AGENT_INVOKE_CONFIG } from '../constants';
import { fetchTargetRepoSlugForIssue } from '../utils/targetRepo';
import {
  formatForgeDispatchErrorBody,
  logForgeDispatchFailure,
} from '../utils/forgeDispatchDetails';

const DEFAULT_SUCCESS_BODY =
  'GitHub Actions workflow was dispatched. Check the issue comment for progress.';

/**
 * Issue panel state: epic key, confirmation modal, banners, and invoke handlers
 * for Discovery / Architect / Stories.
 */
export function useEpicAiPanel() {
  const context = useProductContext();
  const issueKey =
    context?.extension?.issue?.key ?? context?.extension?.issueKey ?? null;

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [banner, setBanner] = useState(null);

  const handleClick = async (action) => {
    setBanner(null);
    const config = AGENT_INVOKE_CONFIG[action];
    if (!config) {
      setBanner({
        appearance: 'info',
        title: 'Not available yet',
        body: `${ACTION_LABELS[action] ?? action} is not wired in this version.`,
      });
      return;
    }

    if (!issueKey) {
      setBanner({
        appearance: 'error',
        title: 'No issue context',
        body: config.noIssueBody,
      });
      return;
    }

    const slug = await fetchTargetRepoSlugForIssue(issueKey);
    if (!slug) {
      setBanner({
        appearance: 'warning',
        title: 'Repository required',
        body: TARGET_REPO_REQUIRED_MESSAGE_EPIC,
      });
      return;
    }

    const result = await invoke(config.invoke, { issueKey });
    if (result?.ok) {
      setBanner({
        appearance: 'success',
        title: config.successTitle,
        body: result.message || DEFAULT_SUCCESS_BODY,
      });
    } else if (result?.code === 'run_in_progress') {
      setBanner({
        appearance: 'info',
        title: 'Run in progress',
        body:
          result?.message ||
          'A workflow orchestrator run is already in progress for this issue. Wait for it to finish.',
      });
    } else if (result?.code === 'missing_target_repo') {
      setBanner({
        appearance: 'warning',
        title: 'Repository required',
        body: result?.message || TARGET_REPO_REQUIRED_MESSAGE_EPIC,
      });
    } else {
      logForgeDispatchFailure(`Forge ${config.invoke}`, issueKey, result);
      setBanner({
        appearance: 'error',
        title: config.errorTitle,
        body: formatForgeDispatchErrorBody(result),
      });
    }
  };

  const openConfirm = async (action) => {
    setBanner(null);
    const config = AGENT_INVOKE_CONFIG[action];
    if (!config) {
      setBanner({
        appearance: 'info',
        title: 'Not available yet',
        body: `${ACTION_LABELS[action] ?? action} is not wired in this version.`,
      });
      return;
    }
    if (!issueKey) {
      setBanner({
        appearance: 'error',
        title: 'No issue context',
        body: config.noIssueBody,
      });
      return;
    }
    const slug = await fetchTargetRepoSlugForIssue(issueKey);
    if (!slug) {
      setBanner({
        appearance: 'warning',
        title: 'Repository required',
        body: TARGET_REPO_REQUIRED_MESSAGE_EPIC,
      });
      return;
    }
    setSelectedAgent(action);
    setPendingAction(action);
    setConfirmOpen(true);
  };

  const closeConfirm = () => {
    setConfirmOpen(false);
    setPendingAction(null);
    setSelectedAgent(null);
  };

  const bodyText = useMemo(
    () =>
      pendingAction != null
        ? `Are you sure you want to run ${ACTION_LABELS[pendingAction]} on this issue?`
        : '',
    [pendingAction],
  );

  const confirmPendingAction = async () => {
    if (pendingAction != null) {
      await handleClick(pendingAction);
    }
  };

  return {
    issueKey,
    banner,
    confirmOpen,
    bodyText,
    selectedAgent,
    openConfirm,
    closeConfirm,
    handleClick,
    confirmPendingAction,
  };
}
