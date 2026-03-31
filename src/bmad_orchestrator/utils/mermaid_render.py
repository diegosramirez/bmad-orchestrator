"""Render Mermaid source to PNG bytes (Kroki HTTP or local mmdc)."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Final

import httpx

from bmad_orchestrator.config import Settings
from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

_PNG_SIG: Final[bytes] = b"\x89PNG\r\n\x1a\n"


def png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    """Read width/height from PNG IHDR; fallback if invalid."""
    if len(png_bytes) < 24 or not png_bytes.startswith(_PNG_SIG):
        return (800, 600)
    width = int.from_bytes(png_bytes[16:20], "big")
    height = int.from_bytes(png_bytes[20:24], "big")
    if width <= 0 or height <= 0 or width > 32767 or height > 32767:
        return (800, 600)
    return (width, height)


def render_mermaid_to_png(settings: Settings, source: str) -> tuple[bytes | None, str | None]:
    """
    Render Mermaid diagram text to PNG.

    Returns (png_bytes, None) on success, or (None, error_message) on failure.
    """
    text = (source or "").strip()
    if not text:
        return None, "empty mermaid source"
    if len(text) > settings.mermaid_max_source_chars:
        return None, "mermaid source exceeds configured max length"

    renderer = settings.mermaid_renderer.lower()
    if renderer == "kroki":
        return _render_kroki(settings, text)
    if renderer == "mmdc":
        return _render_mmdc(settings, text)
    return None, f"unknown mermaid renderer: {renderer}"


def _render_kroki(settings: Settings, text: str) -> tuple[bytes | None, str | None]:
    base = (settings.kroki_url or "https://kroki.io").rstrip("/")
    url = f"{base}/mermaid/png"
    try:
        with httpx.Client(timeout=settings.mermaid_kroki_timeout_seconds) as client:
            r = client.post(
                url,
                content=text.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
            )
    except httpx.HTTPError as exc:
        logger.warning("mermaid_kroki_http_error", error=str(exc))
        return None, f"kroki request failed: {exc}"
    if r.status_code != 200:
        logger.warning(
            "mermaid_kroki_bad_status",
            status=r.status_code,
            body_preview=r.text[:200],
        )
        return None, f"kroki returned {r.status_code}"
    data = r.content
    if not data.startswith(_PNG_SIG):
        return None, "kroki response is not a valid PNG"
    return data, None


def _render_mmdc(settings: Settings, text: str) -> tuple[bytes | None, str | None]:
    exe = settings.mmdc_path or "mmdc"
    try:
        with (
            tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".mmd",
                delete=False,
                encoding="utf-8",
            ) as f_in,
            tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f_out,
        ):
            in_path = Path(f_in.name)
            out_path = Path(f_out.name)
            f_in.write(text)
            f_in.flush()
        try:
            proc = subprocess.run(
                [exe, "-i", str(in_path), "-o", str(out_path), "-b", "transparent"],
                capture_output=True,
                text=True,
                timeout=float(settings.mermaid_mmdc_timeout_seconds),
                check=False,
            )
        finally:
            in_path.unlink(missing_ok=True)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            logger.warning("mermaid_mmdc_failed", returncode=proc.returncode, stderr=err[:500])
            out_path.unlink(missing_ok=True)
            return None, f"mmdc failed: {err[:200] or proc.returncode}"
        data = out_path.read_bytes()
        out_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("mermaid_mmdc_os_error", error=str(exc))
        return None, f"mmdc os error: {exc}"
    except subprocess.TimeoutExpired:
        logger.warning("mermaid_mmdc_timeout")
        return None, "mmdc timed out"
    if not data.startswith(_PNG_SIG):
        return None, "mmdc output is not a valid PNG"
    return data, None


def has_mermaid_fences(markdown: str) -> bool:
    """True if markdown contains a ```mermaid fenced block."""
    return bool(re.search(r"^\s*```\s*mermaid\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE))
