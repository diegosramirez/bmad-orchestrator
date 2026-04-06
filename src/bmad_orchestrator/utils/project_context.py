from __future__ import annotations

import json
import subprocess
from pathlib import Path

_COMPILE_TIMEOUT_S = 90  # seconds — tsc can be slow on first run

_MAX_OUTPUT_CHARS = 4000

# Ordered: most specific first so we detect Angular before generic TypeScript, etc.
_FRAMEWORK_DEPS: list[tuple[str, str]] = [
    ("@angular/core", "Angular"),
    ("@angular/common", "Angular"),
    ("next", "Next.js (React)"),
    ("nuxt", "Nuxt.js (Vue)"),
    ("react", "React"),
    ("vue", "Vue"),
    ("svelte", "Svelte"),
    ("solid-js", "SolidJS"),
    ("astro", "Astro"),
    ("express", "Express (Node.js)"),
    ("fastify", "Fastify (Node.js)"),
    ("nestjs/core", "NestJS"),
    ("@nestjs/core", "NestJS"),
]

_TEST_RUNNER_DEPS: list[tuple[str, str]] = [
    ("@angular/core", "Jasmine / Karma"),  # Angular default
    ("jest", "Jest"),
    ("vitest", "Vitest"),
    ("mocha", "Mocha"),
    ("jasmine", "Jasmine"),
    ("cypress", "Cypress"),
    ("playwright", "Playwright"),
]

_PYTHON_FRAMEWORK_DEPS: list[tuple[str, str]] = [
    ("django", "Django"),
    ("flask", "Flask"),
    ("fastapi", "FastAPI"),
    ("starlette", "Starlette"),
    ("tornado", "Tornado"),
]


def _detect_angular_architecture(cwd: Path) -> str:
    """Return 'standalone' or 'ngmodule' by inspecting the project structure.

    Standalone is the default from Angular 17+. Key signals:
    - No src/app/app.module.ts  → standalone
    - src/main.ts uses bootstrapApplication → standalone
    """
    if not (cwd / "src" / "app" / "app.module.ts").exists():
        return "standalone"
    main_ts = cwd / "src" / "main.ts"
    if main_ts.exists():
        try:
            if "bootstrapApplication" in main_ts.read_text(encoding="utf-8", errors="ignore"):
                return "standalone"
        except Exception:
            pass
    return "ngmodule"


def _read_file_head(path: Path, max_chars: int = 500) -> str:
    """Read up to max_chars from a file; empty string if missing or unreadable."""
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def _detect_js_framework(all_deps: dict[str, str]) -> str:
    for key, label in _FRAMEWORK_DEPS:
        if key in all_deps:
            return label
    return "Node.js"


def _detect_js_test_runner(all_deps: dict[str, str]) -> str:
    # Angular is special: its presence implies Jasmine/Karma by default
    if "@angular/core" in all_deps:
        for key, label in _TEST_RUNNER_DEPS:
            if key == "@angular/core":
                continue
            if key in all_deps:
                return label
        return "Jasmine / Karma"
    for key, label in _TEST_RUNNER_DEPS:
        if key in all_deps:
            return label
    return ""


def _read_package_json(cwd: Path) -> dict[str, str]:
    """Return a flat dict of all dependency names → version strings."""
    pkg_path = cwd / "package.json"
    if not pkg_path.exists():
        return {}
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        combined: dict[str, str] = {}
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            combined.update(data.get(section, {}))
        return combined
    except Exception:
        return {}


def _read_pyproject(cwd: Path) -> dict[str, str]:
    """Return {name, requires-python, frameworks} from pyproject.toml."""
    path = cwd / "pyproject.toml"
    if not path.exists():
        return {}
    try:
        # Avoid adding tomllib dependency — parse just what we need with basic string scan
        text = path.read_text(encoding="utf-8")
        result: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("name") and "=" in line:
                result["name"] = line.split("=", 1)[1].strip().strip('"\'')
            elif line.startswith("requires-python") and "=" in line:
                result["python"] = line.split("=", 1)[1].strip().strip('"\'')
        deps_text = text.lower()
        for key, label in _PYTHON_FRAMEWORK_DEPS:
            if key in deps_text:
                result["framework"] = label
                break
        return result
    except Exception:
        return {}


def _read_requirements(cwd: Path) -> str:
    """Return top lines from requirements.txt as a framework hint."""
    for name in ("requirements.txt", "requirements/base.txt", "requirements/prod.txt"):
        path = cwd / name
        if path.exists():
            try:
                lines = [
                    ln.strip()
                    for ln in path.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.startswith("#")
                ][:10]
                text = "\n".join(lines).lower()
                for key, label in _PYTHON_FRAMEWORK_DEPS:
                    if key in text:
                        return label
            except Exception:
                pass
    return ""


def _read_go_mod(cwd: Path) -> dict[str, str]:
    path = cwd / "go.mod"
    if not path.exists():
        return {}
    try:
        result: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("module "):
                result["module"] = line[len("module "):].strip()
            elif line.startswith("go "):
                result["go"] = line[3:].strip()
        return result
    except Exception:
        return {}


def _read_cargo_toml(cwd: Path) -> dict[str, str]:
    path = cwd / "Cargo.toml"
    if not path.exists():
        return {}
    try:
        result: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("name") and "=" in line:
                result["name"] = line.split("=", 1)[1].strip().strip('"\'')
            elif line.startswith("edition") and "=" in line:
                result["edition"] = line.split("=", 1)[1].strip().strip('"\'')
        return result
    except Exception:
        return {}


def gather_project_context(cwd: Path) -> str:
    """
    Scan cwd for well-known project manifest files and return a concise
    human-readable summary suitable for injection into LLM prompts.
    Returns an empty string if nothing recognisable is found.
    """
    lines: list[str] = []

    # ── JavaScript / TypeScript projects ─────────────────────────────────────
    js_deps = _read_package_json(cwd)
    if js_deps:
        try:
            pkg_name = json.loads(
                (cwd / "package.json").read_text(encoding="utf-8")
            ).get("name", "")
        except Exception:
            pkg_name = ""

        framework = _detect_js_framework(js_deps)
        is_typescript = (cwd / "tsconfig.json").exists() or "typescript" in js_deps

        lines.append("=== Project Context ===")
        if pkg_name:
            lines.append(f"Project: {pkg_name}")

        lang = "TypeScript" if is_typescript else "JavaScript"
        lines.append(f"Framework: {framework} ({lang})")

        # Angular-specific: detect standalone vs NgModule architecture
        if "@angular/core" in js_deps:
            angular_version = js_deps.get("@angular/core", "").lstrip("^~>=< ")
            if angular_version:
                lines.append(f"Angular version: {angular_version}")
            arch = _detect_angular_architecture(cwd)
            if arch == "standalone":
                lines.append("Architecture: Standalone Components (Angular 14+)")
                lines.append(
                    "CRITICAL: Do NOT create app.module.ts or use NgModule declarations. "
                    "All components must have `standalone: true`. "
                    "Register routes in app.routes.ts using `{ path: ..., component: ... }`. "
                    "Import shared Angular modules (CommonModule, FormsModule, etc.) directly "
                    "in the component's `imports` array, not in any NgModule."
                )
            else:
                lines.append("Architecture: NgModule-based")

            # Include existing routing/config files so the developer can follow the pattern
            for rel_path in ("src/app/app.routes.ts", "src/app/app.config.ts", "src/main.ts"):
                snippet = _read_file_head(cwd / rel_path, max_chars=600)
                if snippet:
                    lines.append(f"\n### {rel_path}\n```typescript\n{snippet}\n```")

        test_runner = _detect_js_test_runner(js_deps)
        if test_runner:
            lines.append(f"\nTest runner: {test_runner}")

        config_files = [
            f for f in ("angular.json", "tsconfig.json", "package.json", "vite.config.ts",
                         "vite.config.js", "webpack.config.js", "jest.config.js",
                         "jest.config.ts", ".eslintrc.json", ".eslintrc.js")
            if (cwd / f).exists()
        ]
        if config_files:
            lines.append(f"Config files: {', '.join(config_files)}")

        # Truncate and return
        output = "\n".join(lines)
        return output[:_MAX_OUTPUT_CHARS]

    # ── Python projects ───────────────────────────────────────────────────────
    pyproject = _read_pyproject(cwd)
    if pyproject or (cwd / "requirements.txt").exists():
        req_framework = _read_requirements(cwd)
        lines.append("=== Project Context ===")
        if pyproject.get("name"):
            lines.append(f"Project: {pyproject['name']}")
        lines.append(f"Language: Python {pyproject.get('python', '').strip('>=<~^') or '3.x'}")
        framework = pyproject.get("framework") or req_framework
        if framework:
            lines.append(f"Framework: {framework}")
        config_files = [
            f for f in ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg")
            if (cwd / f).exists()
        ]
        lines.append(f"Config files: {', '.join(config_files)}")
        return "\n".join(lines)[:_MAX_OUTPUT_CHARS]

    # ── Go projects ───────────────────────────────────────────────────────────
    go = _read_go_mod(cwd)
    if go:
        lines.append("=== Project Context ===")
        lines.append(f"Language: Go {go.get('go', '')}")
        if go.get("module"):
            lines.append(f"Module: {go['module']}")
        return "\n".join(lines)[:_MAX_OUTPUT_CHARS]

    # ── Rust projects ─────────────────────────────────────────────────────────
    cargo = _read_cargo_toml(cwd)
    if cargo:
        lines.append("=== Project Context ===")
        lines.append(f"Language: Rust (edition {cargo.get('edition', '2021')})")
        if cargo.get("name"):
            lines.append(f"Project: {cargo['name']}")
        return "\n".join(lines)[:_MAX_OUTPUT_CHARS]

    return ""


_DEV_GUIDELINES_MAX_CHARS = 3000
_CMD_TIMEOUT_S = 120


def read_manifest_scripts(cwd: Path) -> dict[str, str]:
    """Read the scripts/commands section from the project manifest.

    Returns the raw scripts dict (e.g. ``{"build": "ng build", "test": "ng test"}``
    from ``package.json``), or an equivalent for Python/Go/Rust projects.
    The caller (typically the ``detect_commands`` AI node) uses this raw data
    to determine the correct shell commands.

    Never raises — returns an empty dict on any error.
    """
    # ── JavaScript / TypeScript (package.json) ────────────────────────────────
    pkg_path = cwd / "package.json"
    if pkg_path.exists():
        try:
            data = json.loads(pkg_path.read_text(encoding="utf-8"))
            return data.get("scripts", {})
        except Exception:
            return {}

    # ── Python (pyproject.toml) ───────────────────────────────────────────────
    if (cwd / "pyproject.toml").exists():
        scripts: dict[str, str] = {}
        try:
            text = (cwd / "pyproject.toml").read_text(encoding="utf-8")
            if "[tool.pytest" in text or "pytest" in text:
                scripts["test_hint"] = "pytest is configured"
            if "[tool.ruff" in text or "ruff" in text:
                scripts["lint_hint"] = "ruff is configured"
        except Exception:
            pass
        return scripts

    # ── Go ────────────────────────────────────────────────────────────────────
    if (cwd / "go.mod").exists():
        return {"build_hint": "go project", "test_hint": "go project"}

    # ── Rust ──────────────────────────────────────────────────────────────────
    if (cwd / "Cargo.toml").exists():
        return {"build_hint": "cargo project", "test_hint": "cargo project"}

    return {}


def run_project_command(cmd: str, cwd: Path, max_output: int = 4000) -> tuple[bool, str]:
    """Run a single shell command string and return (success, truncated_output).

    Uses shell=True so that npm/npx commands and PATH-based binaries resolve
    correctly (these commands come from AI-detected manifest scripts, not
    untrusted user input).
    Never raises — returns (False, error_message) on any exception.
    """
    try:
        result = subprocess.run(  # noqa: S603, S602
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=_CMD_TIMEOUT_S,
            shell=True,
        )
        output = (result.stdout + result.stderr)[:max_output]
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {_CMD_TIMEOUT_S}s: {cmd}"
    except Exception as exc:
        return False, f"Command failed to run: {exc}"


def _extract_readme_dev_sections(text: str, max_chars: int = 1000) -> str:
    """Extract development-relevant sections from a README."""
    dev_keywords = {"development", "getting started", "contributing", "setup", "running"}
    lines = text.splitlines()
    capturing = False
    captured: list[str] = []
    total = 0

    for line in lines:
        stripped = line.strip().lower().lstrip("#").strip()
        is_heading = line.strip().startswith("#")
        if is_heading:
            if any(kw in stripped for kw in dev_keywords):
                capturing = True
            elif capturing and captured:
                break
            else:
                capturing = False
        if capturing:
            captured.append(line)
            total += len(line) + 1
            if total >= max_chars:
                break

    return "\n".join(captured)


def read_dev_guidelines(cwd: Path) -> str:
    """Read project documentation to extract developer guidelines for LLM injection.

    Reads (in priority order):
    1. CLAUDE.md  — AI coding assistant context (first 1500 chars)
    2. README.md  — development/getting-started sections (up to 1000 chars)
    3. CONTRIBUTING.md — first 1000 chars

    Returns a combined text block capped at _DEV_GUIDELINES_MAX_CHARS.
    This text is injected verbatim into developer prompts — NOT parsed for commands.
    Returns empty string if nothing found. Never raises.
    """
    parts: list[str] = []
    total = 0

    def _add(label: str, content: str) -> None:
        nonlocal total
        if not content.strip() or total >= _DEV_GUIDELINES_MAX_CHARS:
            return
        block = f"### {label}\n{content.strip()}\n"
        remaining = _DEV_GUIDELINES_MAX_CHARS - total
        parts.append(block[:remaining])
        total += len(block)

    claude_md = cwd / "CLAUDE.md"
    if claude_md.exists():
        try:
            _add("CLAUDE.md", claude_md.read_text(encoding="utf-8", errors="ignore")[:1500])
        except Exception:
            pass

    readme = cwd / "README.md"
    if readme.exists():
        try:
            raw = readme.read_text(encoding="utf-8", errors="ignore")
            section = _extract_readme_dev_sections(raw, max_chars=1000)
            if section:
                _add("README.md (development sections)", section)
        except Exception:
            pass

    contributing = cwd / "CONTRIBUTING.md"
    if contributing.exists():
        try:
            text = contributing.read_text(encoding="utf-8", errors="ignore")[:1000]
            _add("CONTRIBUTING.md", text)
        except Exception:
            pass

    return "\n".join(parts)


def run_compile_check(cwd: Path) -> list[str]:
    """Run a type-check / compile-check for the target project.

    Currently supports TypeScript projects (Angular and plain TS).
    Returns a list of human-readable error strings (empty = no errors / check skipped).
    Errors are capped at 30 lines to avoid overwhelming the LLM prompt.
    """
    if not (cwd / "tsconfig.json").exists():
        return []

    # Prefer the local tsc binary if node_modules is present (avoids npx network hit).
    tsc_local = cwd / "node_modules" / ".bin" / "tsc"
    args = (
        [str(tsc_local), "--noEmit"]
        if tsc_local.exists()
        else ["npx", "--yes", "typescript", "--noEmit"]
    )

    try:
        result = subprocess.run(  # noqa: S603
            args,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=_COMPILE_TIMEOUT_S,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if result.returncode == 0:
        return []

    errors: list[str] = []
    for line in (result.stdout + result.stderr).splitlines():
        line = line.strip()
        if line and ("error TS" in line or "error:" in line.lower()):
            errors.append(line)
        if len(errors) >= 30:
            break
    return errors


# ── Test file discovery ──────────────────────────────────────────────────────

# Common test file patterns across ecosystems, ordered by specificity.
_TEST_GLOBS: list[str] = [
    "**/*.spec.ts",      # Angular, TypeScript
    "**/*.test.ts",      # Vitest, Jest (TS)
    "**/*.spec.js",      # JavaScript
    "**/*.test.js",      # Jest (JS)
    "**/*.spec.tsx",     # React TSX
    "**/*.test.tsx",     # React TSX
    "**/test_*.py",      # pytest
    "**/*_test.py",      # pytest alt
    "**/*_test.go",      # Go
    "**/*Test.java",     # JUnit
    "**/*_spec.rb",      # RSpec
    "**/*.test.rs",      # Rust
    "**/*.spec.cs",      # .NET
]

# Directories to skip during test file search.
_SKIP_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__", ".next", "vendor"}


def find_example_test_file(cwd: Path, max_chars: int = 3000) -> str:
    """Find and read one existing test file from the project.

    Returns the file contents (truncated to *max_chars*) prefixed with the
    file path, or an empty string if no test file is found.  The result is
    suitable for injection into an LLM prompt as a "follow this pattern"
    reference.

    Technology-agnostic: searches common test-file patterns across JS/TS,
    Python, Go, Java, Ruby, Rust, and .NET projects.
    """
    for pattern in _TEST_GLOBS:
        # Use rglob but skip node_modules etc. via manual filter
        for candidate in sorted(cwd.rglob(pattern)):
            # Skip files inside ignored directories
            if any(part in _SKIP_DIRS for part in candidate.parts):
                continue
            # Skip very small files (likely empty stubs)
            try:
                if candidate.stat().st_size < 50:
                    continue
                content = candidate.read_text(encoding="utf-8")[:max_chars]
                rel_path = candidate.relative_to(cwd)
                return f"### {rel_path}\n```\n{content}\n```"
            except Exception:
                continue
    return ""
