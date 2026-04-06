import React, { Fragment } from 'react';
import { SectionMessage, Spinner, Stack, Text } from '@forge/react';
import { App } from './App';
import { useIssueMetadata } from './hooks/useIssueMetadata';

/**
 * Epic issues only: original AI Actions panel (Discovery, Architect, Stories).
 * BMAD comments (/bmad refine|retry) live on the AI Comments panel for Story issues.
 */
export function EpicPanelApp() {
  const { issueKey, loading, error, issueTypeName, isEpic } = useIssueMetadata();

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

  if (!isEpic) {
    return (
      <Stack space="space.150">
        <SectionMessage appearance="info" title="Epic-only panel">
          <Text>
            This panel runs Discovery, Design Architect, and Generate Stories on{' '}
            <Text as="strong">Epic</Text> issues. This issue&apos;s type is{' '}
            <Text as="strong">{issueTypeName || 'unknown'}</Text>.
          </Text>
          <Text>
            For <Text as="strong">Story</Text> issues, use the <Text as="strong">BMAD Story</Text>{' '}
            panel to run the full dev pipeline, or <Text as="strong">AI Comments</Text> for /bmad
            refine or retry.
          </Text>
        </SectionMessage>
      </Stack>
    );
  }

  return (
    <Fragment>
      <Stack space="space.200">
        <App />
      </Stack>
    </Fragment>
  );
}
