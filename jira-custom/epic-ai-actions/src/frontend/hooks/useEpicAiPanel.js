import { useMemo, useState } from 'react';
import { useProductContext } from '@forge/react';
import { invoke } from '@forge/bridge';
import { ACTION_LABELS, AGENT_INVOKE_CONFIG } from '../constants';

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

    const result = await invoke(config.invoke, { issueKey });
    if (result?.ok) {
      setBanner({
        appearance: 'confirmation',
        title: config.successTitle,
        body: result.message || DEFAULT_SUCCESS_BODY,
      });
    } else {
      setBanner({
        appearance: 'error',
        title: config.errorTitle,
        body: result?.message || 'Unknown error',
      });
    }
  };

  const openConfirm = (action) => {
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
