import React from 'react';
import {
  Button,
  Icon,
  Inline,
  Pressable,
  Text,
} from '@forge/react';
import { SELECTED_AGENT_XCSS } from '../constants';

/**
 * Single agent control: default Button, or Pressable + inverse text when selected.
 */
export function AgentActionButton({
  label,
  iconGlyph,
  selected,
  onPress,
}) {
  if (selected) {
    return (
      <Pressable onClick={onPress} xcss={SELECTED_AGENT_XCSS}>
        <Inline space="space.100" alignBlock="center">
          <Icon glyph={iconGlyph} label="" color="color.text.inverse" size="small" />
          <Text color="color.text.inverse">{label}</Text>
        </Inline>
      </Pressable>
    );
  }

  return (
    <Button onClick={onPress} iconBefore={iconGlyph}>
      {label}
    </Button>
  );
}
