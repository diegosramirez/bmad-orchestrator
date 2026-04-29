from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from bmad_orchestrator.services.github_token_provider import (
    GitHubAppAuthError,
    GitHubAppTokenProvider,
)


@pytest.fixture(scope="module")
def rsa_pem() -> str:
    """Generate a small RSA key once per module for JWT signing tests."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem_bytes.decode()


@pytest.fixture(scope="module")
def rsa_public_pem(rsa_pem: str) -> str:
    """Public-key counterpart for verifying JWTs minted in tests."""
    private = serialization.load_pem_private_key(rsa_pem.encode(), password=None)
    public_bytes = private.public_key().public_bytes(  # type: ignore[union-attr]
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return public_bytes.decode()


def _frozen_clock(now: datetime):
    def _clock() -> datetime:
        return now
    return _clock


def _mock_transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _success_handler(token: str = "ghs_inst", expires_at: str | None = None):
    if expires_at is None:
        expires_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={"token": token, "expires_at": expires_at, "permissions": {}},
        )

    return handler


# ── Constructor validation ────────────────────────────────────────────────────


def test_rejects_empty_app_id(rsa_pem: str) -> None:
    with pytest.raises(ValueError, match="App id"):
        GitHubAppTokenProvider("", "1", rsa_pem)


def test_rejects_empty_installation_id(rsa_pem: str) -> None:
    with pytest.raises(ValueError, match="installation id"):
        GitHubAppTokenProvider("1", "", rsa_pem)


def test_rejects_non_pem_private_key() -> None:
    with pytest.raises(ValueError, match="PEM"):
        GitHubAppTokenProvider("1", "2", "not a pem")


# ── JWT minting ──────────────────────────────────────────────────────────────


def test_mint_jwt_payload(rsa_pem: str, rsa_public_pem: str) -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    provider = GitHubAppTokenProvider(
        "12345",
        "99",
        rsa_pem,
        clock=_frozen_clock(now),
        http_client=_mock_transport(_success_handler()),
    )
    token = provider._mint_jwt()
    decoded = jwt.decode(
        token,
        rsa_public_pem,
        algorithms=["RS256"],
        # Disable exp validation: the test uses a frozen clock in the past,
        # so the JWT exp is in the past relative to the real wall-clock.
        options={"verify_signature": True, "verify_exp": False},
    )
    assert decoded["iss"] == "12345"
    assert decoded["exp"] - decoded["iat"] <= 10 * 60 + 60  # ≤ 10min + skew
    assert decoded["iat"] <= int(now.timestamp())


# ── Caching ──────────────────────────────────────────────────────────────────


def test_caches_within_window(rsa_pem: str) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            201,
            json={
                "token": f"ghs_{call_count}",
                "expires_at": (
                    datetime.now(UTC) + timedelta(hours=1)
                ).isoformat(),
                "permissions": {},
            },
        )

    provider = GitHubAppTokenProvider(
        "1",
        "2",
        rsa_pem,
        http_client=_mock_transport(handler),
    )
    t1 = provider.get_installation_token()
    t2 = provider.get_installation_token()
    t3 = provider.get_installation_token()
    assert t1 == t2 == t3 == "ghs_1"
    assert call_count == 1


def test_refreshes_after_expiry(rsa_pem: str) -> None:
    now = [datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)]

    def clock() -> datetime:
        return now[0]

    seq = iter([
        ("ghs_first", now[0] + timedelta(minutes=5)),
        ("ghs_second", now[0] + timedelta(hours=1)),
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        token, expiry = next(seq)
        return httpx.Response(
            201,
            json={
                "token": token,
                "expires_at": expiry.isoformat(),
                "permissions": {},
            },
        )

    provider = GitHubAppTokenProvider(
        "1",
        "2",
        rsa_pem,
        clock=clock,
        http_client=_mock_transport(handler),
        skew_seconds=60,
    )
    assert provider.get_installation_token() == "ghs_first"
    # Advance past expiry-skew window
    now[0] = now[0] + timedelta(minutes=10)
    assert provider.get_installation_token() == "ghs_second"


def test_invalidate_forces_refresh(rsa_pem: str) -> None:
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(
            201,
            json={
                "token": f"ghs_{counter['n']}",
                "expires_at": (
                    datetime.now(UTC) + timedelta(hours=1)
                ).isoformat(),
                "permissions": {},
            },
        )

    provider = GitHubAppTokenProvider(
        "1",
        "2",
        rsa_pem,
        http_client=_mock_transport(handler),
    )
    assert provider.get_installation_token() == "ghs_1"
    provider.invalidate()
    assert provider.get_installation_token() == "ghs_2"


# ── Error paths ──────────────────────────────────────────────────────────────


def test_401_raises_typed_error(rsa_pem: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    provider = GitHubAppTokenProvider(
        "1",
        "2",
        rsa_pem,
        http_client=_mock_transport(handler),
    )
    with pytest.raises(GitHubAppAuthError, match="401"):
        provider.get_installation_token()


def test_network_error_wraps_into_auth_error(rsa_pem: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = GitHubAppTokenProvider(
        "1",
        "2",
        rsa_pem,
        http_client=_mock_transport(handler),
    )
    with pytest.raises(GitHubAppAuthError):
        provider.get_installation_token()


# ── close() ───────────────────────────────────────────────────────────────────


def test_close_only_closes_owned_client(rsa_pem: str) -> None:
    """When the caller passes an http_client, the provider must not close it."""
    client = _mock_transport(_success_handler())
    provider = GitHubAppTokenProvider("1", "2", rsa_pem, http_client=client)
    provider.close()
    # Should still be usable
    assert client.post(
        "https://api.github.com/test", json={}
    ).status_code in (201, 200, 404)


def test_close_closes_owned_client(rsa_pem: str) -> None:
    """When the provider builds its own client, close() releases it."""
    provider = GitHubAppTokenProvider("1", "2", rsa_pem)
    # Just confirm close() doesn't raise; the client is owned internally.
    provider.close()


# ── Settings.resolve_github_app_private_key ───────────────────────────────────


def test_resolve_private_key_from_path(tmp_path: Any, rsa_pem: str) -> None:
    from bmad_orchestrator.config import Settings

    pem_path = tmp_path / "key.pem"
    pem_path.write_text(rsa_pem)

    s = Settings(
        anthropic_api_key="test",  # type: ignore[arg-type]
        jira_base_url="https://test.atlassian.net",
        jira_username="t@t.com",
        jira_api_token="x",  # type: ignore[arg-type]
        jira_project_key="T",
        github_repo="org/repo",
        github_app_id="1",
        github_app_installation_id="2",
        github_app_private_key_path=pem_path,
    )
    assert s.resolve_github_app_private_key() == rsa_pem


def test_resolve_private_key_from_inline(rsa_pem: str) -> None:
    from bmad_orchestrator.config import Settings

    s = Settings(
        anthropic_api_key="test",  # type: ignore[arg-type]
        jira_base_url="https://test.atlassian.net",
        jira_username="t@t.com",
        jira_api_token="x",  # type: ignore[arg-type]
        jira_project_key="T",
        github_repo="org/repo",
        github_app_id="1",
        github_app_installation_id="2",
        github_app_private_key=rsa_pem,  # type: ignore[arg-type]
    )
    assert s.resolve_github_app_private_key() == rsa_pem
