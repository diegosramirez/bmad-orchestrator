/**
 * GitHub workflow_dispatch input maps for Forge panel flows (parity with Python webhook).
 */
export function teamIdFromIssueKey(issueKey: string, defaultTeamId: string): string {
  if (issueKey.includes("-")) return issueKey.split("-", 1)[0];
  return defaultTeamId;
}

export function buildDiscoveryWorkflowInputs(
  issueKey: string,
  targetRepo: string,
  teamId: string
): Record<string, string> {
  const extraFlags = `--epic-key ${issueKey} --story-key ${issueKey}`;
  return {
    target_repo: targetRepo,
    base_branch: "main",
    prompt: issueKey,
    team_id: teamId,
    run_id: "",
    skip_check_epic_state: "false",
    skip_create_or_correct_epic: "false",
    skip_create_story_tasks: "true",
    skip_party_mode_refinement: "true",
    skip_detect_commands: "true",
    skip_dev_story: "true",
    skip_qa_automation: "true",
    skip_code_review: "true",
    skip_e2e_automation: "true",
    skip_commit_and_push: "true",
    skip_create_pull_request: "true",
    skip_epic_architect: "true",
    slack_verbose: "false",
    slack_thread_ts: "",
    branch: "",
    extra_flags: extraFlags,
    guidance: "",
    execution_mode: "discovery",
    auto_execute_issue: "false",
    code_agent: "",
  };
}

export function buildEpicArchitectWorkflowInputs(
  issueKey: string,
  targetRepo: string,
  teamId: string
): Record<string, string> {
  const extraFlags = `--epic-key ${issueKey} --story-key ${issueKey}`;
  return {
    target_repo: targetRepo,
    base_branch: "main",
    prompt: issueKey,
    team_id: teamId,
    run_id: "",
    skip_check_epic_state: "true",
    skip_create_or_correct_epic: "true",
    skip_create_story_tasks: "true",
    skip_party_mode_refinement: "true",
    skip_detect_commands: "true",
    skip_dev_story: "true",
    skip_qa_automation: "true",
    skip_code_review: "true",
    skip_e2e_automation: "true",
    skip_commit_and_push: "true",
    skip_create_pull_request: "true",
    skip_epic_architect: "false",
    slack_verbose: "false",
    slack_thread_ts: "",
    branch: "",
    extra_flags: extraFlags,
    guidance: "",
    execution_mode: "epic_architect",
    auto_execute_issue: "false",
    code_agent: "",
  };
}

export function buildStoriesWorkflowInputs(
  issueKey: string,
  targetRepo: string,
  teamId: string
): Record<string, string> {
  const extraFlags = `--epic-key ${issueKey}`;
  return {
    target_repo: targetRepo,
    base_branch: "main",
    prompt: issueKey,
    team_id: teamId,
    run_id: "",
    skip_check_epic_state: "true",
    skip_create_or_correct_epic: "true",
    skip_create_story_tasks: "false",
    skip_party_mode_refinement: "false",
    skip_detect_commands: "true",
    skip_dev_story: "true",
    skip_qa_automation: "true",
    skip_code_review: "true",
    skip_e2e_automation: "true",
    skip_commit_and_push: "true",
    skip_create_pull_request: "true",
    skip_epic_architect: "true",
    slack_verbose: "false",
    slack_thread_ts: "",
    branch: "",
    extra_flags: extraFlags,
    guidance: "",
    execution_mode: "stories_breakdown",
    auto_execute_issue: "false",
    code_agent: "",
  };
}

export function buildDevStoryWorkflowInputs(
  issueKey: string,
  targetRepo: string,
  teamId: string
): Record<string, string> {
  return {
    target_repo: targetRepo,
    base_branch: "main",
    prompt: issueKey,
    team_id: teamId,
    run_id: "",
    skip_check_epic_state: "true",
    skip_create_or_correct_epic: "true",
    skip_create_story_tasks: "true",
    skip_party_mode_refinement: "true",
    skip_detect_commands: "false",
    skip_dev_story: "false",
    skip_qa_automation: "false",
    skip_code_review: "false",
    skip_commit_and_push: "false",
    skip_create_pull_request: "false",
    skip_epic_architect: "true",
    slack_verbose: "false",
    slack_thread_ts: "",
    branch: "",
    extra_flags: "",
    guidance: "",
    execution_mode: "inline",
    auto_execute_issue: "false",
    code_agent: "",
  };
}
