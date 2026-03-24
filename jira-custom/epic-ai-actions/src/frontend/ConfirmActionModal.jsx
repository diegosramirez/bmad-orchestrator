import React, { useState } from 'react';
import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
  Spinner,
  Stack,
  Text,
} from '@forge/react';

/**
 * Confirmation dialog shown before running an agent action.
 * Cancel closes the modal; Continue runs onConfirm then closes.
 */
export const ConfirmActionModal = ({
  isOpen,
  onClose,
  title,
  bodyText,
  onConfirm,
}) => {
  const [working, setWorking] = useState(false);

  const handleContinue = async () => {
    setWorking(true);
    try {
      await onConfirm();
      onClose();
    } finally {
      setWorking(false);
    }
  };

  return (
    <ModalTransition>
      {isOpen && (
        <Modal onClose={working ? () => {} : onClose} width="small">
          <ModalHeader>
            <ModalTitle>{title}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.100">
              <Text>{bodyText}</Text>
              {working && (
                <Stack space="space.050" alignInline="start">
                  <Spinner size="medium" />
                  <Text>Starting run…</Text>
                </Stack>
              )}
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} isDisabled={working}>
              Cancel
            </Button>
            <Button appearance="primary" onClick={handleContinue} isDisabled={working}>
              Continue
            </Button>
          </ModalFooter>
        </Modal>
      )}
    </ModalTransition>
  );
};
