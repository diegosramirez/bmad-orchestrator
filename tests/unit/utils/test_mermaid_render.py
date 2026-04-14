from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.mermaid_render import (
    has_mermaid_fences,
    png_dimensions,
    render_mermaid_to_png,
)

_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
)


def _settings(**kwargs: object) -> Settings:
    return Settings(
        anthropic_api_key="k",  # type: ignore[arg-type]
        jira_base_url="https://x.atlassian.net",
        jira_username="u",
        jira_api_token="t",  # type: ignore[arg-type]
        github_repo="a/b",
        **kwargs,
    )


def test_png_dimensions_reads_ihdr() -> None:
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        + (10).to_bytes(4, "big")
        + (20).to_bytes(4, "big")
        + b"\x00\x00\x00\x00"
    )
    assert png_dimensions(png) == (10, 20)


def test_png_dimensions_invalid_fallback() -> None:
    assert png_dimensions(b"notpng") == (800, 600)


def test_has_mermaid_fences() -> None:
    assert has_mermaid_fences("```mermaid\nx\n```")
    assert not has_mermaid_fences("```python\nx\n```")


def test_render_mermaid_off_returns_error() -> None:
    s = _settings(mermaid_renderer="off")
    out, err = render_mermaid_to_png(s, "graph TD; A-->B")
    assert out is None
    assert err is not None


def test_render_kroki_success(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(mermaid_renderer="kroki")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = _PNG_1X1

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client.post.return_value = mock_resp

    monkeypatch.setattr(
        "bmad_orchestrator.utils.mermaid_render.httpx.Client",
        lambda **_k: mock_client,
    )

    out, err = render_mermaid_to_png(s, "graph TD; A-->B")
    assert err is None
    assert out == _PNG_1X1
    posted = mock_client.post.call_args.kwargs.get("content") or mock_client.post.call_args[0][1]
    assert posted.startswith(b"%%{init: ")
    assert b'"theme":"base"' in posted
    assert b'"background":"#ffffff"' in posted
    assert b"themeVariables" in posted


def test_render_kroki_skips_init_when_user_has_init(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(mermaid_renderer="kroki")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = _PNG_1X1
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client.post.return_value = mock_resp
    monkeypatch.setattr(
        "bmad_orchestrator.utils.mermaid_render.httpx.Client",
        lambda **_k: mock_client,
    )
    user = '%%{init: {"theme": "dark"}}%%\ngraph TD; A-->B'
    out, err = render_mermaid_to_png(s, user)
    assert err is None
    posted = mock_client.post.call_args.kwargs.get("content") or mock_client.post.call_args[0][1]
    decoded = posted.decode("utf-8")
    assert decoded.strip().startswith('%%{init: {"theme": "dark"}}%%')
    assert decoded.count('%%{init:') == 1


def test_render_mmdc_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    s = _settings(mermaid_renderer="mmdc")

    def fake_run(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        assert "-b" in cmd and "white" in cmd
        out_idx = cmd.index("-o") + 1
        out_path = cmd[out_idx]
        with open(out_path, "wb") as f:
            f.write(_PNG_1X1)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(
        "bmad_orchestrator.utils.mermaid_render.subprocess.run",
        fake_run,
    )

    out, err = render_mermaid_to_png(s, "graph TD; A-->B")
    assert err is None
    assert out == _PNG_1X1


def test_render_mmdc_writes_prefixed_source(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    s = _settings(mermaid_renderer="mmdc")
    written: list[str] = []

    def fake_run(cmd: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
        in_idx = cmd.index("-i") + 1
        in_path = cmd[in_idx]
        written.append(Path(in_path).read_text(encoding="utf-8"))
        out_idx = cmd.index("-o") + 1
        out_path = cmd[out_idx]
        Path(out_path).write_bytes(_PNG_1X1)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(
        "bmad_orchestrator.utils.mermaid_render.subprocess.run",
        fake_run,
    )
    out, err = render_mermaid_to_png(s, "graph TD; A-->B")
    assert err is None
    assert written and written[0].startswith("%%{init: ")
    assert '"theme":"base"' in written[0]
    assert '"background":"#ffffff"' in written[0]


def test_render_kroki_bad_status(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(mermaid_renderer="kroki")
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "err"

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client.post.return_value = mock_resp

    monkeypatch.setattr(
        "bmad_orchestrator.utils.mermaid_render.httpx.Client",
        lambda **_k: mock_client,
    )

    out, err = render_mermaid_to_png(s, "graph TD; A-->B")
    assert out is None
    assert err is not None
