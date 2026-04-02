from __future__ import annotations

import subprocess

import pytest

from bmad_orchestrator.utils.retry import retry_on_subprocess_error


def _make_cpe(stderr: str = "") -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(
        returncode=1, cmd=["test"], output="", stderr=stderr,
    )


def test_succeeds_first_attempt():
    calls: list[int] = []

    def fn() -> str:
        calls.append(1)
        return "ok"

    result = retry_on_subprocess_error(fn, label="test")
    assert result == "ok"
    assert len(calls) == 1


def test_retries_once_then_succeeds():
    calls: list[int] = []

    def fn() -> str:
        calls.append(1)
        if len(calls) == 1:
            raise _make_cpe("transient")
        return "ok"

    result = retry_on_subprocess_error(
        fn, delay_seconds=0, label="test",
    )
    assert result == "ok"
    assert len(calls) == 2


def test_raises_after_all_attempts_exhausted():
    def fn() -> str:
        raise _make_cpe("persistent error")

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        retry_on_subprocess_error(fn, delay_seconds=0, label="test")
    assert "persistent error" in (exc_info.value.stderr or "")


def test_does_not_retry_non_subprocess_errors():
    """Only CalledProcessError triggers retry; other exceptions propagate immediately."""

    def fn() -> str:
        raise ValueError("not a subprocess error")

    with pytest.raises(ValueError, match="not a subprocess error"):
        retry_on_subprocess_error(fn, delay_seconds=0, label="test")
