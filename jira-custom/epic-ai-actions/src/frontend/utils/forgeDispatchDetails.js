/**
 * Build a readable banner body from Vercel/slack-worker dispatch responses.
 * Includes GitHub API details when present (dispatch_status, dispatch_error).
 */
export function formatForgeDispatchErrorBody(result) {
  const parts = [
    result?.message,
    result?.dispatch_status != null && result.dispatch_status !== ''
      ? `dispatch_status: ${result.dispatch_status}`
      : null,
    result?.dispatch_error ? `dispatch_error: ${result.dispatch_error}` : null,
  ].filter(Boolean);
  return parts.join('\n\n') || 'Unknown error';
}

/**
 * Log full resolver payload for debugging (browser devtools console).
 */
export function logForgeDispatchFailure(label, issueKey, result) {
  console.error(`[${label}]`, { issueKey, result });
}
