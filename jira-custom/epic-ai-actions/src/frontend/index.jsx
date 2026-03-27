import React, { Fragment, useState } from 'react';
import ForgeReconciler, {
  Box,
  Button,
  Heading,
  Icon,
  Inline,
  SectionMessage,
  Stack,
  Text,
  useProductContext,
} from '@forge/react';
import { invoke } from '@forge/bridge';
import { ConfirmActionModal } from './ConfirmActionModal';

const ACTION_LABELS = {
  discovery: 'Run Discovery',
  architect: 'Design Architect',
  stories: 'Generate Stories',
};

const App = () => {
  const context = useProductContext();
  const issueKey =
    context?.extension?.issue?.key ?? context?.extension?.issueKey ?? null;

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const [banner, setBanner] = useState(null);

  const handleClick = async (action) => {
    setBanner(null);
    if (action === 'discovery') {
      if (!issueKey) {
        setBanner({
          appearance: 'error',
          title: 'No issue context',
          body: 'Open an issue (epic) to run Discovery.',
        });
        return;
      }
      const result = await invoke('runDiscovery', { issueKey });
      if (result?.ok) {
        setBanner({
          appearance: 'success',
          title: 'Discovery started',
          body:
            result.message ||
            'GitHub Actions workflow was dispatched. Check the issue comment for progress.',
        });
      } else {
        setBanner({
          appearance: 'error',
          title: 'Discovery failed',
          body: result?.message || 'Unknown error',
        });
      }
      return;
    }
    if (action === 'architect') {
      if (!issueKey) {
        setBanner({
          appearance: 'error',
          title: 'No issue context',
          body: 'Open an issue (epic) to run Design Architect.',
        });
        return;
      }
      const result = await invoke('runArchitect', { issueKey });
      if (result?.ok) {
        setBanner({
          appearance: 'success',
          title: 'Design Architect started',
          body:
            result.message ||
            'GitHub Actions workflow was dispatched. Check the issue comment for progress.',
        });
      } else {
        setBanner({
          appearance: 'error',
          title: 'Design Architect failed',
          body: result?.message || 'Unknown error',
        });
      }
      return;
    }
    if (action === 'stories') {
      if (!issueKey) {
        setBanner({
          appearance: 'error',
          title: 'No issue context',
          body: 'Open an issue (epic) to generate stories.',
        });
        return;
      }
      const result = await invoke('runStories', { issueKey });
      if (result?.ok) {
        setBanner({
          appearance: 'success',
          title: 'Generate Stories started',
          body:
            result.message ||
            'GitHub Actions workflow was dispatched. Check the issue comment for progress.',
        });
      } else {
        setBanner({
          appearance: 'error',
          title: 'Generate Stories failed',
          body: result?.message || 'Unknown error',
        });
      }
      return;
    }
    setBanner({
      appearance: 'information',
      title: 'Not available yet',
      body: `${ACTION_LABELS[action]} is not wired in this version.`,
    });
  };

  const openConfirm = (action) => {
    setPendingAction(action);
    setConfirmOpen(true);
  };

  const closeConfirm = () => {
    setConfirmOpen(false);
    setPendingAction(null);
  };

  const bodyText =
    pendingAction != null
      ? `Are you sure you want to run ${ACTION_LABELS[pendingAction]} on this issue?`
      : '';

  return (
    <Fragment>
      <Stack space="space.200">
        <Box
          borderBlockEndWidth="border.width"
          borderBlockEndColor="color.border"
          paddingBlockEnd="space.100"
        >
          <Heading as="h2">🚀 AI Actions Panel</Heading>
        </Box>

        {issueKey && (
          <Text>
            <Text as="strong">Issue:</Text> {issueKey}
          </Text>
        )}

        {banner && (
          <SectionMessage appearance={banner.appearance} title={banner.title}>
            <Text>{banner.body}</Text>
          </SectionMessage>
        )}

        <Text>Select an agent to process this epic:</Text>

        <Inline space="space.150" alignBlock="center">
          <Button
            appearance="primary"
            onClick={() => openConfirm('discovery')}
            iconBefore={<Icon glyph="search" label="Discovery" />}
          >
            Run Discovery
          </Button>

          <Button
            onClick={() => openConfirm('architect')}
            iconBefore={<Icon glyph="component" label="Architect" />}
          >
            Design Architect
          </Button>

          <Button
            onClick={() => openConfirm('stories')}
            iconBefore={<Icon glyph="page" label="Stories" />}
          >
            Generate Stories
          </Button>
        </Inline>
      </Stack>

      <ConfirmActionModal
        isOpen={confirmOpen}
        onClose={closeConfirm}
        title="Confirm action"
        bodyText={bodyText}
        onConfirm={() =>
          pendingAction != null ? handleClick(pendingAction) : Promise.resolve()
        }
      />
    </Fragment>
  );
};

ForgeReconciler.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
