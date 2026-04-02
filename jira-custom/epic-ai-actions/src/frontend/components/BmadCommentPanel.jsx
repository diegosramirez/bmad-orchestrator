import React, { useState } from 'react';
import {
  Box,
  Button,
  Inline,
  LoadingButton,
  SectionMessage,
  Stack,
  Text,
  TextArea,
} from '@forge/react';
import { requestJira } from '@forge/bridge';
import { BMAD_SEND_BUTTON_STRETCH_XCSS, BMAD_SEND_ROW_XCSS } from '../constants';
import { adfParagraph, buildBmadCommentLine } from '../utils/bmadComment';

/**
 * Normalize TextArea onChange: UI Kit may pass a string or an event-like object.
 */
function guidanceFromChange(raw) {
  if (typeof raw === 'string') {
    return raw;
  }
  if (raw && typeof raw === 'object') {
    const t = raw.target;
    if (t != null && typeof t === 'object' && typeof t.value === 'string') {
      return t.value;
    }
    if (typeof raw.value === 'string') {
      return raw.value;
    }
  }
  return '';
}

/**
 * Posts a Jira comment starting with /bmad (refine or retry) for Automation + webhook.
 * Guidance is plain text; buildBmadCommentLine wraps it in double quotes in the command.
 */
export function BmadCommentPanel({ issueKey }) {
  const [mode, setMode] = useState('refine');
  const [guidance, setGuidance] = useState('');
  const [banner, setBanner] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const guidanceText = typeof guidance === 'string' ? guidance : '';

  const postComment = async () => {
    setBanner(null);
    if (!issueKey) {
      setBanner({
        appearance: 'error',
        title: 'No issue',
        body: 'Open an issue to post a BMAD comment.',
      });
      return;
    }

    const line = buildBmadCommentLine(mode, guidanceText);
    setSubmitting(true);
    try {
      const response = await requestJira(
        `/rest/api/3/issue/${encodeURIComponent(issueKey)}/comment`,
        {
          method: 'POST',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ body: adfParagraph(line) }),
        },
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const msg =
          data?.errorMessages?.join(' ') ||
          data?.errors ||
          response.statusText ||
          'Failed to add comment';
        throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      }
      setGuidance('');
      setBanner({
        appearance: 'confirmation',
        title: 'Comment added',
        body: 'Jira Automation should pick up the /bmad command and run your workflow.',
      });
    } catch (e) {
      setBanner({
        appearance: 'error',
        title: 'Could not add comment',
        body: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Stack space="space.150">
      <Text>Action</Text>
      <Inline space="space.100">
        <Button
          appearance={mode === 'refine' ? 'primary' : 'subtle'}
          onClick={() => setMode('refine')}
        >
          Refine
        </Button>
        <Button
          appearance={mode === 'retry' ? 'primary' : 'subtle'}
          onClick={() => setMode('retry')}
        >
          Retry
        </Button>
      </Inline>

      <TextArea
        label="Guidance (optional)"
        name="bmad-guidance"
        placeholder="Add context for this action (optional)"
        value={guidanceText}
        onChange={(raw) => setGuidance(guidanceFromChange(raw))}
      />

      <Box xcss={BMAD_SEND_ROW_XCSS}>
        {submitting ? (
          <LoadingButton
            appearance="primary"
            isLoading
            xcss={BMAD_SEND_BUTTON_STRETCH_XCSS}
          >
            Sending…
          </LoadingButton>
        ) : (
          <Button
            appearance="primary"
            onClick={postComment}
            xcss={BMAD_SEND_BUTTON_STRETCH_XCSS}
          >
            Send
          </Button>
        )}
      </Box>

      {banner && (
        <SectionMessage appearance={banner.appearance} title={banner.title}>
          <Text>{banner.body}</Text>
        </SectionMessage>
      )}
    </Stack>
  );
}
