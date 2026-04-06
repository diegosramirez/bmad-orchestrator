"""Unit tests for ``github_active_run`` (GitHub Actions duplicate-run detection)."""
from __future__ import annotations

import httpx
import pytest

from bmad_orchestrator.webhook import github_active_run


class _MockAsyncClient:
    """Minimal async context manager matching ``httpx.AsyncClient`` usage in the module."""

    def __init__(self, get_impl):
        self._get_impl = get_impl

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object):
        return None

    async def get(self, url: str, **kwargs: object):
        return await self._get_impl(url)


@pytest.mark.asyncio
async def test_returns_false_when_credentials_missing() -> None:
    assert await github_active_run.has_active_bmad_run_for_prompt("") is False
    assert await github_active_run.has_active_bmad_run_for_prompt("X-1", github_repo="") is False
    assert await github_active_run.has_active_bmad_run_for_prompt("X-1", github_token="") is False


@pytest.mark.asyncio
async def test_returns_false_when_list_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_impl(url: str) -> httpx.Response:
        assert "workflows/bmad-start-run.yml/runs" in url
        return httpx.Response(200, json={"workflow_runs": []})

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )


@pytest.mark.asyncio
async def test_returns_false_when_no_active_status(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_impl(url: str) -> httpx.Response:
        if "workflows/bmad-start-run.yml/runs" in url:
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {"id": 99, "status": "completed"},
                    ]
                },
            )
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )


def test_run_matches_issue_key_prefers_inputs_prompt() -> None:
    matched, reason = github_active_run._run_matches_issue_key(
        {"inputs": {"prompt": "SAM1-275"}},
        "SAM1-275",
    )
    assert matched is True
    assert reason == "inputs.prompt"


def test_run_matches_issue_key_display_title_fallback() -> None:
    matched, reason = github_active_run._run_matches_issue_key(
        {"display_title": "SAM1-400 · inline", "event": "workflow_dispatch"},
        "SAM1-400",
    )
    assert matched is True
    assert reason == "display_title"


def test_run_matches_issue_key_wrong_prompt_no_title() -> None:
    matched, _reason = github_active_run._run_matches_issue_key(
        {"inputs": {"prompt": "OTHER-9"}},
        "SAM1-1",
    )
    assert matched is False


@pytest.mark.asyncio
async def test_returns_true_when_active_run_matches_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    issue = "SAM1-275"

    async def get_impl(url: str) -> httpx.Response:
        if "workflows/bmad-start-run.yml/runs" in url:
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {"id": 42, "status": "in_progress"},
                    ]
                },
            )
        if url.endswith("/actions/runs/42"):
            return httpx.Response(
                200,
                json={"inputs": {"prompt": issue}},
            )
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            issue,
            github_repo="o/r",
            github_token="tok",
        )
        is True
    )


@pytest.mark.asyncio
async def test_returns_true_when_display_title_matches_without_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue = "SAM1-400"

    async def get_impl(url: str) -> httpx.Response:
        if "workflows/bmad-start-run.yml/runs" in url:
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {"id": 24015281943, "status": "in_progress"},
                    ]
                },
            )
        if url.endswith(f"/actions/runs/{24015281943}"):
            return httpx.Response(
                200,
                json={
                    "event": "workflow_dispatch",
                    "display_title": f"{issue} · inline",
                },
            )
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            issue,
            github_repo="o/r",
            github_token="tok",
        )
        is True
    )


@pytest.mark.asyncio
async def test_returns_false_when_prompt_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_impl(url: str) -> httpx.Response:
        if "workflows/bmad-start-run.yml/runs" in url:
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {"id": 42, "status": "queued"},
                    ]
                },
            )
        if url.endswith("/actions/runs/42"):
            return httpx.Response(
                200,
                json={"inputs": {"prompt": "OTHER-1"}},
            )
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )


@pytest.mark.asyncio
async def test_returns_false_fail_open_on_list_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_impl(url: str) -> httpx.Response:
        if "workflows/bmad-start-run.yml/runs" in url:
            return httpx.Response(403, json={"message": "no"})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )


@pytest.mark.asyncio
async def test_returns_false_fail_open_when_run_detail_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_impl(url: str) -> httpx.Response:
        if "workflows/bmad-start-run.yml/runs" in url:
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {"id": 42, "status": "in_progress"},
                    ]
                },
            )
        if url.endswith("/actions/runs/42"):
            return httpx.Response(404)
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )


@pytest.mark.asyncio
async def test_returns_false_when_workflow_runs_not_list(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_impl(url: str) -> httpx.Response:
        if "workflows/bmad-start-run.yml/runs" in url:
            return httpx.Response(200, json={"workflow_runs": "bad"})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )


@pytest.mark.asyncio
async def test_skips_non_dict_workflow_run_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_impl(url: str) -> httpx.Response:
        if "workflows/bmad-start-run.yml/runs" in url:
            return httpx.Response(
                200,
                json={"workflow_runs": ["skip", {"id": 1, "status": "in_progress"}]},
            )
        if url.endswith("/actions/runs/1"):
            return httpx.Response(200, json={"inputs": {"prompt": "X"}})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )


@pytest.mark.asyncio
async def test_returns_false_when_run_id_not_int(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_impl(url: str) -> httpx.Response:
        if "workflows/bmad-start-run.yml/runs" in url:
            return httpx.Response(
                200,
                json={"workflow_runs": [{"id": "not-int", "status": "in_progress"}]},
            )
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )


@pytest.mark.asyncio
async def test_returns_false_fail_open_on_list_json_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadListResponse:
        status_code = 200

        def json(self) -> dict:
            raise ValueError("bad json")

    async def get_impl(url: str):
        if "workflows/bmad-start-run.yml/runs" in url:
            return BadListResponse()
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )


@pytest.mark.asyncio
async def test_returns_false_fail_open_on_outer_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a, **kw):
        raise RuntimeError("no client")

    monkeypatch.setattr(github_active_run.httpx, "AsyncClient", boom)

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )


@pytest.mark.asyncio
async def test_returns_false_fail_open_when_run_detail_json_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BadRunDetailResponse:
        status_code = 200

        def json(self) -> dict:
            raise ValueError("bad run json")

    async def get_impl(url: str):
        if "workflows/bmad-start-run.yml/runs" in url:
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {"id": 42, "status": "in_progress"},
                    ]
                },
            )
        if url.endswith("/actions/runs/42"):
            return BadRunDetailResponse()
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )


@pytest.mark.asyncio
async def test_returns_false_when_inputs_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_impl(url: str) -> httpx.Response:
        if "workflows/bmad-start-run.yml/runs" in url:
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {"id": 42, "status": "in_progress"},
                    ]
                },
            )
        if url.endswith("/actions/runs/42"):
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        github_active_run.httpx,
        "AsyncClient",
        lambda *a, **kw: _MockAsyncClient(get_impl),
    )

    assert (
        await github_active_run.has_active_bmad_run_for_prompt(
            "SAM1-1",
            github_repo="o/r",
            github_token="tok",
        )
        is False
    )
