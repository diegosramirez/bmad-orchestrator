import React, { Fragment } from 'react';
import {
  SectionMessage,
  Spinner,
  Stack,
  Text,
} from '@forge/react';
import { BmadCommentPanel } from './components/BmadCommentPanel';
import { useIssueMetadata } from './hooks/useIssueMetadata';

/**
 * Story issues only: workflow comment helper (no epic actions).
 */
export function CommentApps() {
  const { issueKey, loading, error, issueTypeName, isStory } = useIssueMetadata();

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
            This panel posts <Text as="strong">refine</Text> or <Text as="strong">retry</Text>{' '}
            workflow comments on <Text as="strong">Story</Text> issues. This issue&apos;s type is{' '}
            <Text as="strong">{issueTypeName || 'unknown'}</Text>.
          </Text>
          <Text>
            For <Text as="strong">Epic</Text> issues, use the <Text as="strong">Workflow Epic</Text>{' '}
            panel (Discovery, Design Architect, Generate Stories). For a full automated dev run on a
            Story, use <Text as="strong">Workflow Story</Text>.
          </Text>
        </SectionMessage>
      </Stack>
    );
  }

  return (
    <Fragment>
      <Stack space="space.200">
        <BmadCommentPanel issueKey={issueKey} />
      </Stack>
    </Fragment>
  );
}
