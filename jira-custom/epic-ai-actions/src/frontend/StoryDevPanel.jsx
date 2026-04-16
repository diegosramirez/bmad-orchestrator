import React, { Fragment, useMemo, useState } from 'react';
import {
  Box,
  Heading,
  Inline,
  SectionMessage,
  Spinner,
  Stack,
  Text,
  xcss,
} from '@forge/react';
import { invoke } from '@forge/bridge';
import { AgentActionButton } from './components/AgentActionButton';
import { ConfirmActionModal } from './components/ConfirmActionModal';
import { useIssueMetadata } from './hooks/useIssueMetadata';

const HEADER_BOX_STYLES = xcss({
  marginBlockStart: 'space.300',
});

const DEFAULT_SUCCESS_BODY =
  'GitHub Actions workflow was dispatched. Check the issue comment for progress.';

/**
 * Story issues only: dispatch full workflow dev pipeline (detect → implementation → QA → review → PR).
 * E2E (Playwright) is skipped in workflow inputs to keep runs lighter and more reliable.
 */
export function StoryDevPanel() {
  const { issueKey, loading, error, issueTypeName, isStory } = useIssueMetadata();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [banner, setBanner] = useState(null);

  const bodyText = useMemo(
    () =>
      issueKey
        ? `Run the full development pipeline on story ${issueKey}? This starts GitHub Actions on the configured target repository.`
        : '',
    [issueKey],
  );

  const runDevelopment = async () => {
    setBanner(null);
    if (!issueKey) {
      setBanner({
        appearance: 'error',
        title: 'No issue context',
        body: 'Open a Story issue to run development.',
      });
      return;
    }
    const result = await invoke('runDevelopment', { issueKey });
    if (result?.ok) {
      setBanner({
        appearance: 'success',
        title: 'Development run started',
        body: result.message || DEFAULT_SUCCESS_BODY,
      });
    } else if (result?.code === 'run_in_progress') {
      setBanner({
        appearance: 'warning',
        title: 'Run in progress',
        body:
          result?.message ||
          'A workflow orchestrator run is already in progress for this issue. Wait for it to finish.',
      });
    } else {
      setBanner({
        appearance: 'error',
        title: 'Run failed',
        body: result?.message || 'Unknown error',
      });
    }
  };

  if (loading) {
    return (
      <Stack space="space.100">
        <Spinner size="medium" />
        <Text>Loading issue type…</Text>
      </Stack>
    );
  }

  if (error) {
    return (
      <SectionMessage appearance="error" title="Could not load issue">
        <Text>{error}</Text>
      </SectionMessage>
    );
  }

  if (!issueKey) {
    return (
      <SectionMessage appearance="warning" title="No issue context">
        <Text>Open an issue to use this panel.</Text>
      </SectionMessage>
    );
  }

  if (!isStory) {
    return (
      <Stack space="space.150">
        <SectionMessage appearance="info" title="Story-only panel">
          <Text>
            This panel runs the workflow development pipeline on <Text as="strong">Story</Text>{' '}
            issues. This issue&apos;s type is{' '}
            <Text as="strong">{issueTypeName || 'unknown'}</Text>.
          </Text>
          <Text>
            For <Text as="strong">Epic</Text> issues, use the <Text as="strong">Workflow Epic</Text>{' '}
            panel (Discovery, Design Architect, Generate Stories).
          </Text>
        </SectionMessage>
      </Stack>
    );
  }

  return (
    <Fragment>
      <Stack space="space.200">
        {/* <Box
          xcss={HEADER_BOX_STYLES}
          borderBlockEndWidth="border.width"
          borderBlockEndColor="color.border"
          paddingBlockEnd="space.100"
        >
          <Heading as="h2">🚀 AI Actions Panel</Heading>
        </Box> */}

      <Box xcss={xcss({ marginBlockStart: 'space.200' })}>
        <Text>
          <Text as="strong">Story:</Text> {issueKey}
        </Text>
      </Box>

        {banner && (
          <SectionMessage appearance={banner.appearance} title={banner.title}>
            <Text>{banner.body}</Text>
          </SectionMessage>
        )}

        <Text>
          Implement code and open a GitHub pull request. End-to-end (Playwright) tests are not run in
          this pipeline.
        </Text>

        <Inline space="space.150" alignBlock="center">
          <AgentActionButton
            label="Run development"
            iconGlyph="branch"
            selected={confirmOpen}
            onPress={() => setConfirmOpen(true)}
          />
        </Inline>



      </Stack>

      <ConfirmActionModal
        isOpen={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Confirm development run"
        bodyText={bodyText}
        onConfirm={runDevelopment}
      />
    </Fragment>
  );
}
