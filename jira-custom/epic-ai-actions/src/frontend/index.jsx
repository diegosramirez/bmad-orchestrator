import React, { Fragment, useState } from 'react';
import ForgeReconciler, {
  Button,
  Text,
  Inline,
  Box,
  Heading,
  Icon,
  Stack,
} from '@forge/react';
import { ConfirmActionModal } from './ConfirmActionModal';

const ACTION_LABELS = {
  discovery: 'Run Discovery',
  architect: 'Design Architect',
  stories: 'Generate Stories',
};

const App = () => {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);

  const handleClick = async (action) => {
    console.log(`Clicked: ${action}`);
    // Aquí irá tu invoke('mi-funcion-backend')
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
