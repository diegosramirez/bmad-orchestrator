import React, { Fragment } from 'react';
import {
  Box,
  Heading,
  Inline,
  SectionMessage,
  Stack,
  Text,
  xcss,
} from '@forge/react';

/** Top spacing for panel header (~24px; closest ADS token to 25px). */
const HEADER_BOX_STYLES = xcss({
  marginBlockStart: 'space.300',
});
import { AgentActionButton } from './components/AgentActionButton';
import { ConfirmActionModal } from './components/ConfirmActionModal';
import { AGENT_ACTIONS } from './constants';
import { useEpicAiPanel } from './hooks/useEpicAiPanel';

export function App() {
  const {
    issueKey,
    banner,
    confirmOpen,
    bodyText,
    selectedAgent,
    openConfirm,
    closeConfirm,
    confirmPendingAction,
  } = useEpicAiPanel();

  return (
    <Fragment>
      <Stack space="space.200">
        <Box
          xcss={HEADER_BOX_STYLES}
          borderBlockEndWidth="border.width"
          borderBlockEndColor="color.border"
          paddingBlockEnd="space.100"
        >
          <Heading as="h2">🚀 AI Actions Panel</Heading>
        </Box>

        {issueKey && (
          <Text>
            <Text as="strong">Epic:</Text> {issueKey}
          </Text>
        )}

        {banner && (
          <SectionMessage appearance={banner.appearance} title={banner.title}>
            <Text>{banner.body}</Text>
          </SectionMessage>
        )}

        <Text>Select an agent to process this epic:</Text>

        <Inline space="space.150" alignBlock="center">
          {AGENT_ACTIONS.map(({ id, label, iconGlyph }) => (
            <AgentActionButton
              key={id}
              label={label}
              iconGlyph={iconGlyph}
              selected={selectedAgent === id}
              onPress={() => openConfirm(id)}
            />
          ))}
        </Inline>
      </Stack>

      <ConfirmActionModal
        isOpen={confirmOpen}
        onClose={closeConfirm}
        title="Confirm action"
        bodyText={bodyText}
        onConfirm={confirmPendingAction}
      />
    </Fragment>
  );
}
