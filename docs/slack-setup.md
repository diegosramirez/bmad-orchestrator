# Slack Integration Setup

This guide walks you through creating a Slack app and configuring it for BMAD Orchestrator notifications. Each pipeline run posts a threaded message to your Slack channel with real-time step updates.

## 1. Create a Slack App

1. Open https://api.slack.com/apps
2. Click **Create New App**
3. Select **From scratch**
4. Enter a name (e.g. `BMAD Orchestrator`) and select your workspace
5. Click **Create App**

## 2. Add Bot Permissions

1. In the left sidebar, click **OAuth & Permissions**
2. Scroll down to **Scopes** > **Bot Token Scopes**
3. Click **Add an OAuth Scope**
4. Add the `chat:write` scope

This is the only scope needed — it allows the bot to post and update messages.

## 3. Install to Workspace

1. Scroll back up to the top of the **OAuth & Permissions** page
2. Click **Install to Workspace**
3. Review the permissions and click **Allow**
4. Copy the **Bot User OAuth Token** that appears — it starts with `xoxb-`

> Keep this token secret. Anyone with it can post messages as your bot.

## 4. Invite the Bot to Your Channel

In Slack, go to the channel where you want notifications and type:

```
/invite @BMAD Orchestrator
```

(Use whatever name you gave your app in step 1.)

If the bot doesn't appear in the invite list, try `/apps` and add it from there.

## 5. Configure GitHub Actions

Go to your `bmad-orchestrator` repository on GitHub:

**Settings** > **Secrets and variables** > **Actions**

### Secrets tab

| Name | Value |
|------|-------|
| `BMAD_SLACK_BOT_TOKEN` | The `xoxb-...` token from step 3 |

### Variables tab

| Name | Value |
|------|-------|
| `BMAD_SLACK_NOTIFY` | `true` |
| `BMAD_SLACK_CHANNEL` | `#your-channel-name` (e.g. `#bmad-notifications`) |

## 6. Test It

Trigger a workflow run from the GitHub Actions UI. You should see:

1. A root message in your Slack channel: `:rocket: BMAD Run — [TEAM] STORY-ID`
2. Each pipeline step appears as a **threaded reply** under that message
3. On failure: the thread includes the failure reason
4. On success: the thread includes the PR link

## 7. Local Development

Add to your `.env` file:

```bash
BMAD_SLACK_NOTIFY=true
BMAD_SLACK_BOT_TOKEN=xoxb-your-token-here
BMAD_SLACK_CHANNEL=#bmad-notifications
```

When running with `--dummy-jira --dummy-github`, Slack notifications still fire (they use the real Slack API regardless of dummy mode). To suppress them locally, set `BMAD_SLACK_NOTIFY=false` or omit the variables.

## Troubleshooting

**"channel_not_found" error in logs**
- The bot hasn't been invited to the channel. Run `/invite @BMAD Orchestrator` in the channel.
- Check that `BMAD_SLACK_CHANNEL` matches the exact channel name (including `#`).

**"invalid_auth" error in logs**
- The bot token is wrong or expired. Re-copy it from **OAuth & Permissions** in your Slack app settings.

**No messages appearing**
- Verify `BMAD_SLACK_NOTIFY` is set to `true` (not `false` or empty).
- Check the GitHub Actions run logs for `slack_api_error` or `slack_api_failed` warnings.

**Messages appear but not threaded**
- This is expected if the first API call fails (no `ts` to thread on). Check the first step's Slack API response in the logs.
