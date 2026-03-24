import React from 'react';
import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
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
  const handleContinue = async () => {
    await onConfirm();
    onClose();
  };

  return (
    <ModalTransition>
      {isOpen && (
        <Modal onClose={onClose} width="small">
          <ModalHeader>
            <ModalTitle>{title}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Text>{bodyText}</Text>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose}>
              Cancel
            </Button>
            <Button appearance="primary" onClick={handleContinue}>
              Continue
            </Button>
          </ModalFooter>
        </Modal>
      )}
    </ModalTransition>
  );
};
