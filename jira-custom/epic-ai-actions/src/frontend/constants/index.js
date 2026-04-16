import { xcss } from '@forge/react';

/**
 * Jira issue field for BMAD git branch (same as slack-worker + JiraService).
 * Refine/retry need this value; it is usually set after a development run.
 */
/** Match BMAD_JIRA_BRANCH_CUSTOM_FIELD_ID / JiraService (default customfield_10145). */
export const BMAD_BRANCH_CUSTOM_FIELD =
  (typeof process !== 'undefined' && process.env?.BMAD_JIRA_BRANCH_CUSTOM_FIELD_ID) ||
  'customfield_10079';

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

/** Full-width row for BMAD comment (select + textarea + send). */
export const BMAD_COMMENT_ROW_XCSS = xcss({
  width: '100%',
  maxWidth: '100%',
});

/**
 * Textarea column: grows so the field uses remaining horizontal space in the row.
 * @see Inline width control — child needs flexGrow for fill layouts.
 */
export const BMAD_COMMENT_TEXTAREA_CELL_XCSS = xcss({
  display: 'block',
  flexGrow: 1,
  minWidth: '0',
  width: '100%',
  alignSelf: 'stretch',
});

/**
 * Select column: stretches to row height (driven by TextArea); centers the control vertically.
 */
export const BMAD_COMMENT_SELECT_CELL_XCSS = xcss({
  flexShrink: 0,
  width: 'auto',
  minWidth: '100px',
  maxWidth: '100%',
  alignSelf: 'stretch',
  display: 'flex',
  alignItems: 'center',
});

/**
 * Send column: stretches to row height; centers the button; token padding (not raw px).
 */
export const BMAD_COMMENT_SEND_CELL_XCSS = xcss({
  flexShrink: 0,
  alignSelf: 'stretch',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  padding: 'space.050',
});

/**
 * Forge Button often ignores height — use paddingBlock tokens to enlarge the control.
 */
export const BMAD_COMMENT_SEND_BUTTON_XCSS = xcss({
  alignSelf: 'stretch',
  paddingBlock: 'space.200',
  paddingInline: 'space.200',
});
