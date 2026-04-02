import React from 'react';
import { Button } from '@forge/react';

/**
 * Agent action: default outline when idle, Jira primary blue when selected (after press).
 */
export function AgentActionButton({
  label,
  iconGlyph,
  selected,
  onPress,
}) {
  return (
    <Button
      onClick={onPress}
      iconBefore={iconGlyph}
      appearance={selected ? 'primary' : 'default'}
    >
      {label}
    </Button>
  );
}
