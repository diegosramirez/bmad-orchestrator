from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def test_orchestrator_env_loaded_as_base(tmp_path, monkeypatch):
    """Orchestrator .env provides defaults when target project has no .env."""
    monkeypatch.delenv("BMAD_TEST_BASE", raising=False)

    # Simulate orchestrator root with .env
    orch_root = tmp_path / "orchestrator"
    orch_root.mkdir()
    (orch_root / ".env").write_text("BMAD_TEST_BASE=from_orchestrator\n")

    # Target project has no .env
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.chdir(target)

    load_dotenv(orch_root / ".env", override=False)
    load_dotenv(target / ".env", override=True)

    assert os.environ["BMAD_TEST_BASE"] == "from_orchestrator"
    monkeypatch.delenv("BMAD_TEST_BASE", raising=False)


def test_target_project_env_overrides_orchestrator(tmp_path, monkeypatch):
    """Target project .env values override orchestrator .env values."""
    monkeypatch.delenv("BMAD_TEST_OVERRIDE", raising=False)

    orch_root = tmp_path / "orchestrator"
    orch_root.mkdir()
    (orch_root / ".env").write_text("BMAD_TEST_OVERRIDE=from_orchestrator\n")

    target = tmp_path / "target"
    target.mkdir()
    (target / ".env").write_text("BMAD_TEST_OVERRIDE=from_target\n")
    monkeypatch.chdir(target)

    load_dotenv(orch_root / ".env", override=False)
    load_dotenv(target / ".env", override=True)

    assert os.environ["BMAD_TEST_OVERRIDE"] == "from_target"
    monkeypatch.delenv("BMAD_TEST_OVERRIDE", raising=False)


def test_shell_env_wins_over_orchestrator(tmp_path, monkeypatch):
    """Shell env vars are not overwritten by orchestrator .env (override=False)."""
    orch_root = tmp_path / "orchestrator"
    orch_root.mkdir()
    (orch_root / ".env").write_text("BMAD_TEST_SHELL=from_orchestrator\n")

    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.chdir(target)

    # Shell env var set before load_dotenv
    monkeypatch.setenv("BMAD_TEST_SHELL", "from_shell")

    load_dotenv(orch_root / ".env", override=False)
    # No target .env → nothing to override
    load_dotenv(target / ".env", override=True)

    assert os.environ["BMAD_TEST_SHELL"] == "from_shell"
    monkeypatch.delenv("BMAD_TEST_SHELL", raising=False)


def test_orchestrator_root_resolves_to_app_dir():
    """bmad_orchestrator.__file__ resolves to the expected app root."""
    import bmad_orchestrator as _pkg

    orch_root = Path(_pkg.__file__).resolve().parent.parent.parent
    # The app root should contain pyproject.toml
    assert (orch_root / "pyproject.toml").exists(), (
        f"Expected pyproject.toml in {orch_root}"
    )
