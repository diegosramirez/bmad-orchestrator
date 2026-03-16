from __future__ import annotations

import json
from pathlib import Path

from bmad_orchestrator.utils.project_context import (
    gather_project_context,
    read_dev_guidelines,
    read_manifest_scripts,
)


def _write_pkg(tmp_path: Path, deps: dict[str, str], name: str = "my-app") -> None:
    pkg = {"name": name, "dependencies": deps}
    (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")


# ── JavaScript / TypeScript detection ─────────────────────────────────────────

def test_detects_angular(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"@angular/core": "^17.0.0"})
    result = gather_project_context(tmp_path)
    assert "Angular" in result


def test_detects_react(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"react": "^18.0.0", "react-dom": "^18.0.0"})
    result = gather_project_context(tmp_path)
    assert "React" in result


def test_detects_nextjs_over_react(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"next": "^14.0.0", "react": "^18.0.0"})
    result = gather_project_context(tmp_path)
    assert "Next.js" in result


def test_detects_typescript_via_tsconfig(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"react": "^18.0.0"})
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    result = gather_project_context(tmp_path)
    assert "TypeScript" in result


def test_detects_jest_test_runner(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"react": "^18.0.0", "jest": "^29.0.0"})
    result = gather_project_context(tmp_path)
    assert "Jest" in result


def test_angular_defaults_to_jasmine_karma(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"@angular/core": "^17.0.0"})
    result = gather_project_context(tmp_path)
    assert "Jasmine" in result


def test_package_name_included(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"react": "^18.0.0"}, name="cool-frontend")
    result = gather_project_context(tmp_path)
    assert "cool-frontend" in result


def test_config_files_listed(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"@angular/core": "^17.0.0"})
    (tmp_path / "angular.json").write_text("{}", encoding="utf-8")
    result = gather_project_context(tmp_path)
    assert "angular.json" in result


# ── Python detection ──────────────────────────────────────────────────────────

def test_detects_python_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "my-service"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    result = gather_project_context(tmp_path)
    assert "Python" in result
    assert "my-service" in result


def test_detects_fastapi_framework(tmp_path: Path) -> None:
    toml = (
        '[project]\nname = "api"\nrequires-python = ">=3.11"\n'
        '\n[project.dependencies]\nfastapi = "*"\n'
    )
    (tmp_path / "pyproject.toml").write_text(toml, encoding="utf-8")
    result = gather_project_context(tmp_path)
    assert "FastAPI" in result


def test_detects_python_requirements_txt(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("flask>=3.0\n", encoding="utf-8")
    result = gather_project_context(tmp_path)
    assert "Python" in result


# ── Go / Rust detection ───────────────────────────────────────────────────────

def test_detects_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module github.com/org/repo\n\ngo 1.22\n", encoding="utf-8")
    result = gather_project_context(tmp_path)
    assert "Go" in result


def test_detects_cargo_toml(tmp_path: Path) -> None:
    cargo_toml = '[package]\nname = "mybin"\nedition = "2021"\n'
    (tmp_path / "Cargo.toml").write_text(cargo_toml, encoding="utf-8")
    result = gather_project_context(tmp_path)
    assert "Rust" in result


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_dir_returns_empty_string(tmp_path: Path) -> None:
    assert gather_project_context(tmp_path) == ""


def test_malformed_package_json_does_not_crash(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("NOT JSON {{{{", encoding="utf-8")
    result = gather_project_context(tmp_path)
    assert isinstance(result, str)


def test_output_does_not_exceed_max_chars(tmp_path: Path) -> None:
    _write_pkg(tmp_path, {"@angular/core": "^17.0.0"})
    result = gather_project_context(tmp_path)
    assert len(result) <= 4000


def test_angular_standalone_detected_when_no_app_module(tmp_path: Path) -> None:
    """No app.module.ts → standalone architecture warning is injected."""
    _write_pkg(tmp_path, {"@angular/core": "^17.0.0"})
    # No app.module.ts created → standalone
    result = gather_project_context(tmp_path)
    assert "Standalone Components" in result
    assert "Do NOT create app.module.ts" in result


def test_angular_ngmodule_detected_when_app_module_present(tmp_path: Path) -> None:
    """app.module.ts present → NgModule architecture reported."""
    _write_pkg(tmp_path, {"@angular/core": "^15.0.0"})
    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "app" / "app.module.ts").write_text("@NgModule({})")
    result = gather_project_context(tmp_path)
    assert "NgModule-based" in result
    assert "Standalone" not in result


def test_angular_includes_routes_file_snippet(tmp_path: Path) -> None:
    """Existing app.routes.ts content is included in context."""
    _write_pkg(tmp_path, {"@angular/core": "^17.0.0"})
    routes_dir = tmp_path / "src" / "app"
    routes_dir.mkdir(parents=True)
    (routes_dir / "app.routes.ts").write_text("export const routes: Routes = [];")
    result = gather_project_context(tmp_path)
    assert "app.routes.ts" in result
    assert "export const routes" in result


# ── read_manifest_scripts ────────────────────────────────────────────────────

def _write_pkg_with_scripts(tmp_path: Path, scripts: dict[str, str]) -> None:
    pkg = {"name": "app", "scripts": scripts, "dependencies": {}}
    (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")


def test_read_manifest_scripts_package_json(tmp_path: Path) -> None:
    scripts = {"build": "ng build", "test": "vitest run", "lint": "eslint ."}
    _write_pkg_with_scripts(tmp_path, scripts)
    scripts = read_manifest_scripts(tmp_path)
    assert scripts["build"] == "ng build"
    assert scripts["test"] == "vitest run"
    assert scripts["lint"] == "eslint ."


def test_read_manifest_scripts_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="svc"\n\n[tool.pytest.ini_options]\n\n[tool.ruff]\n',
        encoding="utf-8",
    )
    scripts = read_manifest_scripts(tmp_path)
    assert "test_hint" in scripts
    assert "lint_hint" in scripts


def test_read_manifest_scripts_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/m\ngo 1.22\n", encoding="utf-8")
    scripts = read_manifest_scripts(tmp_path)
    assert "build_hint" in scripts
    assert "test_hint" in scripts


def test_read_manifest_scripts_cargo_toml(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "mybin"\n', encoding="utf-8")
    scripts = read_manifest_scripts(tmp_path)
    assert "build_hint" in scripts
    assert "test_hint" in scripts


def test_read_manifest_scripts_empty_dir(tmp_path: Path) -> None:
    assert read_manifest_scripts(tmp_path) == {}


def test_read_manifest_scripts_missing_scripts_key(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name":"app","dependencies":{}}', encoding="utf-8")
    scripts = read_manifest_scripts(tmp_path)
    assert scripts == {}


def test_read_manifest_scripts_malformed_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("NOT JSON {{{{", encoding="utf-8")
    assert read_manifest_scripts(tmp_path) == {}


# ── read_dev_guidelines ───────────────────────────────────────────────────────

def test_read_dev_guidelines_reads_claude_md(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("## Commands\nnpm run dev", encoding="utf-8")
    result = read_dev_guidelines(tmp_path)
    assert "npm run dev" in result
    assert "CLAUDE.md" in result


def test_read_dev_guidelines_reads_readme_dev_section(tmp_path: Path) -> None:
    readme = "# My App\n\n## Getting Started\nnpm install && npm start\n\n## Other\nfoo\n"
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    result = read_dev_guidelines(tmp_path)
    assert "npm install" in result


def test_read_dev_guidelines_reads_contributing(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text("Run tests with pytest", encoding="utf-8")
    result = read_dev_guidelines(tmp_path)
    assert "pytest" in result


def test_read_dev_guidelines_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert read_dev_guidelines(tmp_path) == ""


def test_read_dev_guidelines_capped_at_max_chars(tmp_path: Path) -> None:
    # Write a very large CLAUDE.md
    (tmp_path / "CLAUDE.md").write_text("x" * 5000, encoding="utf-8")
    result = read_dev_guidelines(tmp_path)
    assert len(result) <= 3200  # slight buffer above 3000 for the header line
