import { xcss } from '@forge/react';

/** Human-readable labels for modals and fallbacks. */
export const ACTION_LABELS = {
  discovery: 'Run Discovery',
  architect: 'Design Architect',
  stories: 'Generate Stories',
};

/**
 * Forge resolver name (first arg to invoke) and copy for each agent action.
 * Used by useEpicAiPanel to dispatch without duplicating branches.
 */
export const AGENT_INVOKE_CONFIG = {
  discovery: {
    invoke: 'runDiscovery',
    noIssueBody: 'Open an issue (epic) to run Discovery.',
    successTitle: 'Discovery started',
    errorTitle: 'Discovery failed',
  },
  architect: {
    invoke: 'runArchitect',
    noIssueBody: 'Open an issue (epic) to run Design Architect.',
    successTitle: 'Design Architect started',
    errorTitle: 'Design Architect failed',
  },
  stories: {
    invoke: 'runStories',
    noIssueBody: 'Open an issue (epic) to generate stories.',
    successTitle: 'Generate Stories started',
    errorTitle: 'Generate Stories failed',
  },
};

/** Row of agent buttons: stable order for rendering. */
export const AGENT_ACTIONS = [
  { id: 'discovery', label: 'Run Discovery', iconGlyph: 'discover' },
  { id: 'architect', label: 'Design Architect', iconGlyph: 'canvas' },
  { id: 'stories', label: 'Generate Stories', iconGlyph: 'child-issues' },
];

/** Selected agent: custom blue (Forge Button primary does not match this hex). */
export const SELECTED_AGENT_XCSS = xcss({
  backgroundColor: '#0d6efd',
  borderRadius: 'border.radius',
  paddingBlock: 'space.050',
  paddingInline: 'space.150',
  ':hover': {
    backgroundColor: '#0069d9',
  },
});

/** Full panel width so Send matches the text field above. */
export const BMAD_SEND_ROW_XCSS = xcss({
  width: '100%',
  maxWidth: '100%',
});

/**
 * Stretch primary Button / LoadingButton to panel width (Forge theme blue via appearance).
 */
export const BMAD_SEND_BUTTON_STRETCH_XCSS = xcss({
  width: '100%',
});
