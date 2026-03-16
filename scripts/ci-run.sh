#!/usr/bin/env bash
# ci-run.sh — Wrapper for running bmad-orchestrator in GitHub Actions.
# Provides structured log grouping and masked environment output.
#
# Usage:
#   ORCHESTRATOR_DIR=../apps/autonomous-engineering-orchestrator \
#   TEAM_ID=alpha PROMPT="Add auth" \
#   ./ci-run.sh [extra_flags...]
set -euo pipefail

ORCHESTRATOR_DIR="${ORCHESTRATOR_DIR:?Must set ORCHESTRATOR_DIR}"
TEAM_ID="${TEAM_ID:?Must set TEAM_ID}"
PROMPT="${PROMPT:?Must set PROMPT}"

echo "::group::Orchestrator Configuration"
env | grep '^BMAD_' | sed \
  -e 's/\(API_KEY=\).*/\1***/' \
  -e 's/\(API_TOKEN=\).*/\1***/' \
  -e 's/\(TOKEN=\).*/\1***/' \
  | sort
echo "::endgroup::"

echo "::group::Running bmad-orchestrator"
uv run --project "${ORCHESTRATOR_DIR}" \
  bmad-orchestrator run \
  --team-id "${TEAM_ID}" \
  --prompt "${PROMPT}" \
  --non-interactive \
  "$@"
EXIT_CODE=$?
echo "::endgroup::"

exit "${EXIT_CODE}"
