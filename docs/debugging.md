# Debugging with VS Code

## Prerequisites

`debugpy` must be installed in the project venv:

```bash
uv add --dev debugpy
```

This only needs to be done once.

> **No reinstall needed after code changes.** The package is installed in editable mode (`uv tool install --editable .`), so any change to `src/` is reflected immediately — just restart the debug session.

---

## Option A — Attach to a terminal process (recommended)

This lets you control the exact CLI arguments each run.

### 1. Start the process in your terminal

```bash
.venv/bin/python -Xfrozen_modules=off -m debugpy --listen 5678 --wait-for-client \
  -m bmad_orchestrator.cli \
  --team-id your-team-id \
  --prompt "your prompt here" \
  --dummy-jira \
  --dummy-github \
  --dry-run
```

> **Tip — jump straight to a specific node:** use `--skip-nodes` to bypass earlier nodes, and `--epic-key` to skip interactive epic selection. For example, to land directly in `dev_story` with real Jira story content:
>
> ```bash
> .venv/bin/python -Xfrozen_modules=off -m debugpy --listen 5678 --wait-for-client \
>   -m bmad_orchestrator.cli \
>   --team-id your-team-id \
>   --epic-key PUG-437 \
>   --prompt "your prompt here" \
>   --skip-nodes check_epic_state,create_or_correct_epic
> ```

The process will pause and print the frozen-modules warning — that is expected. It is waiting for VS Code to connect.

### 2. Set breakpoints in VS Code

Click the gutter next to any line in `src/` to set a breakpoint before attaching.

### 3. Attach VS Code

Open the **Run & Debug** panel (`Cmd+Shift+D`), select **"bmad-orchestrator attach (terminal)"** from the dropdown, and press **F5**.

VS Code connects and execution resumes, stopping at your breakpoints.

---

## Option B — Launch directly from VS Code

Use this when you want a fixed set of arguments and don't need the terminal.

1. Edit the args in [`.vscode/launch.json`](../.vscode/launch.json) under the **"bmad-orchestrator run"** configuration.
2. Set breakpoints.
3. Select **"bmad-orchestrator run"** in the Run & Debug dropdown and press **F5**.

---

## Debugging tests

Two pytest configurations are available in `.vscode/launch.json`:

| Config                      | What it runs                                         |
| --------------------------- | ---------------------------------------------------- |
| **pytest (current file)**   | Debugs whichever test file is open in the editor     |
| **pytest (all unit tests)** | Runs the full `tests/unit/` suite under the debugger |

Set a breakpoint inside a test or the node under test, select the config, and hit **F5**. The `-s` flag is passed so `print()` output is visible in the Debug Console.

---

## Troubleshooting

**Breakpoints not hit / greyed out**

Pass `-Xfrozen_modules=off` to the Python interpreter (already included in the attach command above). For the launch config add it to `"python"`:

```json
"python": "${workspaceFolder}/.venv/bin/python3 -Xfrozen_modules=off"
```

Or set the env var instead:

```bash
PYDEVD_DISABLE_FILE_VALIDATION=1 .venv/bin/python -m debugpy ...
```

**`pyenv: version '3.11' is not installed`**

Always use the venv Python directly — never the bare `python` command, which pyenv intercepts:

```bash
# correct
.venv/bin/python -m debugpy ...

# wrong — pyenv picks this up
python -m debugpy ...
```

**`No module named debugpy`**

```bash
uv add --dev debugpy
```

**Port 5678 already in use**

A previous debug session may still be running. Kill it:

```bash
lsof -ti :5678 | xargs kill -9
```

Or change the port in both the terminal command and `.vscode/launch.json`.
