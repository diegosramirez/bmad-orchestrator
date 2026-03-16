# BMAD Orchestrator — Demo Recording Script

## Pre-recording checklist

1. Make sure your API rate limit has reset (or switch to API key billing)
2. Clean the target project: `cd ~/source/repos/mine/my-test-app && git checkout main && git clean -fd`
3. Have VS Code or terminal full-screen, font size ~16pt for readability

---

## Script

**[Screen: terminal in `my-test-app` directory]**

> "I'm going to demonstrate the BMAD Autonomous Engineering Orchestrator — it takes a Jira user story and autonomously generates a full feature: code, tests, QA validation, and code review — all driven by Claude AI with role-based personas."

**[Type the command, don't hit enter yet]**

```bash
bmad-orchestrator run --story-key SAM1-54 --clean
```

> "I'm passing a Jira story key. The `--clean` flag wipes any cached state so we get a completely fresh run. The orchestrator will fetch the story from Jira and auto-detect the team, epic, and acceptance criteria."

**[Hit enter]**

> "It first asks which pipeline steps to skip. Since we already have the story in Jira, I'm skipping epic creation and story creation — jumping straight to development."

**[Select the 6 nodes to skip, hit enter]**

> "You can see it cleaned the previous checkpoints. Now it shows the run configuration — team, epic, prompt from the Jira story, and which nodes we're skipping."

**[Wait for detect_commands to complete]**

> "The Build Expert agent just analyzed the project and detected the build, test, and lint commands — `ng build` and `ng test`."

**[Wait for dev_story agent to start]**

> "Now Amelia, the Developer persona, starts implementing the feature. She's using Claude Opus with access to Read, Write, Edit, Bash, Glob, and Grep tools — she can explore the codebase, write files, and run commands autonomously."

**[As tool_use logs appear]**

> "You can see each file she creates in real-time — the data model, the service layer, components, routing. She's following Angular conventions and the acceptance criteria from the Jira story."

**[When dev_story completes]**

> "Development is done. Now the QA agent runs the test suite to validate the implementation."

**[When qa_automation completes]**

> "QA passed. Now the Code Reviewer — a senior architect persona — does a thorough review looking for issues across severity levels."

**[When code_review completes, if issues found]**

> "The reviewer found some issues. If they're medium severity or above, the orchestrator automatically sends the developer back to fix them — up to two review loops."

**[When pipeline completes]**

> "The full pipeline completed autonomously — from Jira story to working, reviewed code. Let me show you the result."

**[Show the generated app]**

```bash
ng serve
```

> "Here's the app running with the new feature fully implemented."

**[Optional: show the log file]**

```bash
ls ~/.bmad/logs/
```

> "Every run produces a detailed log file with console output and, in verbose mode, full agent interaction traces."

---

## Tips for recording

- Use `--verbose` if you want the video to show detailed agent logs (more interesting visually), or omit it for a cleaner output
- The run takes ~10-15 minutes — consider speeding up the video 4-8x during the agent execution portions, with normal speed for your narration
- If you want to show the Jira comment updates, have Jira open in a split screen on SAM1-54
