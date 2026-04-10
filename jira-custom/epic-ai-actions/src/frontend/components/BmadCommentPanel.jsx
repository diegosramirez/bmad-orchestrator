import React, { useRef, useState } from 'react';
import {
  Box,
  Button,
  Inline,
  LoadingButton,
  SectionMessage,
  Select,
  Stack,
  Text,
  TextArea,
} from '@forge/react';
import { requestJira, view } from '@forge/bridge';
import { useBmadBranch } from '../hooks/useBmadBranch';
import {
  BMAD_COMMENT_ROW_XCSS,
  BMAD_COMMENT_SELECT_CELL_XCSS,
  BMAD_COMMENT_SEND_BUTTON_XCSS,
  BMAD_COMMENT_SEND_CELL_XCSS,
  BMAD_COMMENT_TEXTAREA_CELL_XCSS,
} from '../constants';
import { adfParagraph, buildBmadCommentLine } from '../utils/bmadComment';

const MODE_OPTIONS = [
  { label: 'Refine', value: 'refine' },
  { label: 'Retry', value: 'retry' },
];

const NO_BRANCH_WARNING_TITLE = 'Workflow branch not available';
const NO_BRANCH_WARNING_BODY =
  'You cannot send a message because this issue has no workflow branch set. ' +
  'Run "Run development" from the Workflow Story panel first so the branch is saved; ' +
  'then you can use Refine or Retry.';

/**
 * Posts a Jira comment starting with /bmad (refine or retry) for Automation + webhook.
 * Guidance is plain text; buildBmadCommentLine wraps it in double quotes in the command.
 */
export function BmadCommentPanel({ issueKey }) {
  const { hasBranch, loading: branchLoading, error: branchError } = useBmadBranch(issueKey);
  const [mode, setMode] = useState('refine');
  /** Latest guidance without re-rendering on each keystroke (uncontrolled TextArea). */
  const guidanceRef = useRef('');
  /** Bump to remount TextArea and clear it after a successful post (defaultValue only applies on mount). */
  const [guidanceFieldKey, setGuidanceFieldKey] = useState(0);
  const [banner, setBanner] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const selectedModeOption = MODE_OPTIONS.find((o) => o.value === mode) ?? MODE_OPTIONS[0];

  const handleTextAreaChange = (raw) => {
    const value =
      typeof raw === 'string'
        ? raw
        : raw?.target?.value ?? raw?.currentTarget?.value ?? '';
    guidanceRef.current = value ?? '';
  };

  const sendBlocked = branchLoading || !!branchError || !hasBranch;

  const postComment = async () => {
    setBanner(null);
    if (!issueKey) {
      setBanner({
        appearance: 'error',
        title: 'No issue',
        body: 'Open an issue to post a workflow comment.',
      });
      return;
    }

    if (!hasBranch) {
      setBanner({
        appearance: 'warning',
        title: NO_BRANCH_WARNING_TITLE,
        body: NO_BRANCH_WARNING_BODY,
      });
      return;
    }

    const guidanceText =
      typeof guidanceRef.current === 'string' ? guidanceRef.current : '';
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
      guidanceRef.current = '';
      setGuidanceFieldKey((k) => k + 1);
      try {
        await view.refresh();
      } catch {
        /* Not all host contexts expose refresh; comment was still created. */
      }
      setBanner({
        appearance: 'success',
        title: 'Comment added',
        body: 'Jira Automation should pick up the comment and run your workflow.',
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

  const onModeChange = (opt) => {
    if (opt && !Array.isArray(opt) && typeof opt === 'object' && opt.value != null) {
      setMode(opt.value);
    }
  };

  return (
    <Stack space="space.150">
      <Text>Action</Text>

      {branchError && (
        <SectionMessage appearance="error" title="Could not load workflow branch">
          <Text>{branchError}</Text>
        </SectionMessage>
      )}

      {!branchLoading && !branchError && !hasBranch && (
        <SectionMessage appearance="warning" title={NO_BRANCH_WARNING_TITLE}>
          <Text>{NO_BRANCH_WARNING_BODY}</Text>
        </SectionMessage>
      )}

      <Box xcss={BMAD_COMMENT_ROW_XCSS}>
        <Inline space="space.100" alignBlock="stretch" grow="fill">
          <Box xcss={BMAD_COMMENT_SELECT_CELL_XCSS}>
            <Select
              name="bmad-mode"
              appearance="default"
              spacing="default"
              options={MODE_OPTIONS}
              value={selectedModeOption}
              onChange={onModeChange}
              placeholder="Action"
            />
          </Box>

          <Box xcss={BMAD_COMMENT_TEXTAREA_CELL_XCSS}>
            <TextArea
              key={guidanceFieldKey}
              label="Guidance (optional)"
              name="bmad-guidance"
              placeholder="Add context for this action (optional)"
              defaultValue=""
              onChange={handleTextAreaChange}
              isCompact
              minimumRows={2}
            />
          </Box>

          <Box xcss={BMAD_COMMENT_SEND_CELL_XCSS}>
            {submitting ? (
              <LoadingButton
                appearance="primary"
                isLoading
                spacing="default"
                xcss={BMAD_COMMENT_SEND_BUTTON_XCSS}
                isDisabled={sendBlocked}
              >
                Sending…
              </LoadingButton>
            ) : (
              <Button
                appearance="primary"
                spacing="default"
                onClick={postComment}
                xcss={BMAD_COMMENT_SEND_BUTTON_XCSS}
                isDisabled={sendBlocked}
              >
                Send
              </Button>
            )}
          </Box>
        </Inline>
      </Box>

      {banner && (
        <SectionMessage appearance={banner.appearance} title={banner.title}>
          <Text>{banner.body}</Text>
        </SectionMessage>
      )}
    </Stack>
  );
}
