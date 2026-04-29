"""GitHub App authentication: JWT signing + installation-token caching."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt

from bmad_orchestrator.utils.logger import get_logger

logger = get_logger(__name__)

# GitHub allows JWTs up to 10 minutes; mint for 9 to leave clock-skew headroom.
_JWT_LIFETIME = timedelta(minutes=9)


class GitHubAppAuthError(RuntimeError):
    """Raised when JWT minting or installation-token exchange fails."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class GitHubAppTokenProvider:
    """Thread-safe provider that mints installation access tokens for a GitHub App.

    Tokens are cached until ``skew_seconds`` before declared expiry, then refreshed
    on the next ``get_installation_token()`` call.
    """

    def __init__(
        self,
        app_id: str,
        installation_id: str,
        private_key_pem: str,
        *,
        clock: Callable[[], datetime] = _utc_now,
        http_client: httpx.Client | None = None,
        skew_seconds: int = 60,
    ) -> None:
        if not app_id:
            raise ValueError("GitHub App id is required")
        if not installation_id:
            raise ValueError("GitHub App installation id is required")
        if not private_key_pem or not private_key_pem.lstrip().startswith("-----BEGIN"):
            raise ValueError(
                "GitHub App private key must be a PEM-encoded RSA key "
                "(starts with '-----BEGIN')"
            )

        self._app_id = app_id
        self._installation_id = installation_id
        self._private_key = private_key_pem
        self._clock = clock
        self._http = http_client or httpx.Client(timeout=10.0)
        self._owns_http = http_client is None
        self._skew = timedelta(seconds=skew_seconds)
        self._lock = threading.Lock()
        self._cached_token: str | None = None
        self._cached_expiry: datetime | None = None

    def get_installation_token(self) -> str:
        """Return a cached or freshly-minted installation access token."""
        with self._lock:
            if self._is_cached_valid():
                assert self._cached_token is not None
                return self._cached_token
            jwt_token = self._mint_jwt()
            token, expires_at = self._exchange_for_token(jwt_token)
            self._cached_token = token
            self._cached_expiry = expires_at
            logger.info(
                "github_app_token_minted",
                app_id=self._app_id,
                installation_id=self._installation_id,
                expires_at=expires_at.isoformat(),
            )
            return token

    def invalidate(self) -> None:
        """Drop the cached token; the next call will refresh."""
        with self._lock:
            self._cached_token = None
            self._cached_expiry = None

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def _is_cached_valid(self) -> bool:
        if self._cached_token is None or self._cached_expiry is None:
            return False
        return self._clock() + self._skew < self._cached_expiry

    def _mint_jwt(self) -> str:
        now = self._clock()
        payload: dict[str, Any] = {
            "iat": int(now.timestamp()) - 60,  # backdate for clock skew
            "exp": int((now + _JWT_LIFETIME).timestamp()),
            "iss": self._app_id,
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    def _exchange_for_token(self, jwt_token: str) -> tuple[str, datetime]:
        url = (
            f"https://api.github.com/app/installations/"
            f"{self._installation_id}/access_tokens"
        )
        try:
            response = self._http.post(
                url,
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        except httpx.HTTPError as exc:
            raise GitHubAppAuthError(
                f"GitHub App token exchange failed: {exc}"
            ) from exc

        if response.status_code != 201:
            raise GitHubAppAuthError(
                f"GitHub App token exchange returned {response.status_code}: "
                f"{response.text[:300]}"
            )

        data = response.json()
        token = data["token"]
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        return token, expires_at
