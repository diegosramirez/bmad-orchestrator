# Jira comment trigger — Retry / Refine from Comments

Trigger BMAD retry or refine runs from Jira by posting a comment that starts with `/bmad`. The **slack-worker** handler (`slack-worker/`, deployed on Vercel) reads the branch from the story's **BMAD Branch** custom field (default `customfield_10145`; override with `BMAD_JIRA_BRANCH_CUSTOM_FIELD_ID`) and dispatches the same GitHub Actions workflow used by Slack.

## Endpoint

- **URL:** `POST /bmad/jira-comment-webhook` (Vercel rewrite → `/api/jira-comment`)
- **Body:** JSON from Jira Automation (see below).

## Supported commands

| Command | Description |
|--------|-------------|
| `/bmad retry "guidance"` | Re-run the pipeline on the existing branch (skips planning nodes). Use after a failed run. |
| `/bmad refine "guidance"` | Re-run dev/QA/review on the existing branch with extra guidance. Use after a successful run when you want changes. |

The **guidance** text is optional but must be in quotes when present, e.g. `"fix the auth middleware"` or `"add loading states"`.

## Requirements

1. **BMAD Branch field** (`BMAD_JIRA_BRANCH_CUSTOM_FIELD_ID`, default `customfield_10145`)  
   The issue must have this field set to the git branch name (e.g. `bmad/sam1/SAM1-61-as-a-new-user-i-want-to-re-enter-my-pass`). BMAD fills it automatically after the **commit and push** step when you run the pipeline (via the manual automation button or the Jira issue webhook). If the field is empty, the handler returns 400 and does not start a run.

2. **Target repo field** (`BMAD_JIRA_TARGET_REPO_CUSTOM_FIELD_ID`, default `customfield_10112`)  
   Optional. If present (e.g. `value: "my-test-app"`), the worker builds `target_repo` as `{BMAD_GITHUB_OWNER}/{value}`. Otherwise it uses `DEFAULT_TARGET_REPO` from the deployment environment.

3. **Jira Automation payload**  
   The handler expects the comment trigger to send a JSON body that includes:
   - `issue.key`, `issue.id`
   - Target repo field (default `customfield_10112`) — slug
   - Branch field (default `customfield_10145`) — BMAD Branch
   - `comment.body`, `comment.id`, `comment.author.displayName`

   Example minimal structure:

   ```json
   {
     "issue": {
       "key": "{{issue.key}}",
       "id": "{{issue.id}}",
       "fields": {
         "customfield_10112": { "value": "{{issue.fields.customfield_10112.value}}" },
         "customfield_10145": "{{issue.fields.customfield_10145}}"
       }
     },
     "comment": {
       "body": "{{comment.body}}",
       "id": "{{comment.id}}",
       "author": "{{comment.author.displayName}}"
     }
   }
   ```

   Replace `customfield_*` keys in `fields` with your `BMAD_JIRA_*_CUSTOM_FIELD_ID` values when not using defaults.

## Examples

- Retry without extra guidance:  
  `/bmad retry`

- Retry with guidance:  
  `/bmad retry "fix the auth middleware and add logging"`

- Refine with guidance:  
  `/bmad refine "add loading states and error boundaries"`

Comments that do **not** start with `/bmad` are ignored (no workflow dispatched).

## Response

- **200** — Comment saved; no `/bmad` command or invalid syntax; `run_started: false`.
- **400** — Invalid command or missing branch field; `run_started: false`, `message` explains the error.
- **202** — Workflow dispatched; `run_started: true`, `actions_url` points to the GitHub Actions workflow.
- **500** — Dispatch to GitHub failed; `run_started: false`, `dispatch_status` and `dispatch_error` included.
