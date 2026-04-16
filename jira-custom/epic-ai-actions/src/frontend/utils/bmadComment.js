/**
 * Build the /bmad command line parsed by slack-worker jira-comment (shlex.split parity).
 * Replaces double quotes in guidance with apostrophes for safe parsing.
 *
 * @param {'refine' | 'retry'} mode
 * @param {string} guidanceRaw
 * @returns {string}
 */
export function buildBmadCommentLine(mode, guidanceRaw) {
  const safe = (guidanceRaw || '').trim().replace(/"/g, "'");
  if (mode === 'retry') {
    return safe ? `/bmad retry "${safe}"` : '/bmad retry';
  }
  return safe ? `/bmad refine "${safe}"` : '/bmad refine';
}

/**
 * Minimal ADF body for a plain-text Jira comment.
 *
 * @param {string} plainText
 * @returns {{ type: 'doc', version: 1, content: object[] }}
 */
export function adfParagraph(plainText) {
  return {
    type: 'doc',
    version: 1,
    content: [
      {
        type: 'paragraph',
        content: [{ type: 'text', text: plainText }],
      },
    ],
  };
}
