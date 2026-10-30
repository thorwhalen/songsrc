"""HTTP client for the Genius API, spanning the token'd and tokenless surfaces.

Genius exposes two JSON surfaces that share the same response envelope
(``{"meta": ..., "response": ...}``):

- **Official API** — ``https://api.genius.com``. Requires a *Client Access
  Token* (Bearer). Serves songs, albums, referents and annotations, but **not**
  lyrics.
- **Public web API** — ``https://genius.com/api``. Needs no token. Serves the
  same song/album/referent JSON *and* backs the lyrics pages.

``GeniusClient`` picks the official API when a token is available (constructor
argument or ``GENIUS_ACCESS_TOKEN`` env var) and falls back to the tokenless
public API otherwise. Either way, the caller-facing methods are identical.

The lyrics themselves never come from JSON — they are scraped from the rendered
song page (see :func:`fetch_song_page`), which needs no token.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

_OFFICIAL_API = "https://api.genius.com"
_PUBLIC_API = "https://genius.com/api"
_WEB = "https://genius.com"

# A browser-like UA keeps the tokenless public endpoints and page scrapes happy.
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class GeniusClient:
    """Thin, polite client over the Genius JSON API and song pages.

    Args:
        access_token: Official API Client Access Token. Defaults to the
            ``GENIUS_ACCESS_TOKEN`` env var. When absent, the tokenless public
            endpoints are used instead.
        user_agent: ``User-Agent`` header for every request.
        min_interval: Minimum seconds between requests (simple rate limit).
        max_retries: Retries for transient failures (429 / 5xx / network).
        timeout: Per-request timeout in seconds.
    """

    access_token: str | None = field(
        default_factory=lambda: os.environ.get("GENIUS_ACCESS_TOKEN") or None
    )
    user_agent: str = _DEFAULT_UA
    min_interval: float = 0.34
    max_retries: int = 4
    timeout: float = 30.0

    def __post_init__(self) -> None:
        self._last_request_at = 0.0
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        # Two clients: JSON (api or public) and web (page scraping, HTML).
        self._api_base = _OFFICIAL_API if self.access_token else _PUBLIC_API
        self._json_client = httpx.Client(
            headers=headers, timeout=self.timeout, follow_redirects=True
        )
        self._web_client = httpx.Client(
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
            follow_redirects=True,
        )

    # -- lifecycle ---------------------------------------------------------
    @property
    def uses_token(self) -> bool:
        """Whether the client is talking to the token'd official API."""
        return bool(self.access_token)

    def close(self) -> None:
        self._json_client.close()
        self._web_client.close()

    def __enter__(self) -> "GeniusClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- low-level ---------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _get(self, client: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                resp = client.get(url, **kwargs)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"transient {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                resp.raise_for_status()
                return resp
            except (httpx.HTTPError,) as exc:  # network + transient status
                last_exc = exc
                if attempt == self.max_retries:
                    break
                time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"GET {url} failed after retries: {last_exc}") from last_exc

    def _api_get(self, path: str, **params: Any) -> dict[str, Any]:
        """GET a JSON API path and return the unwrapped ``response`` object."""
        url = f"{self._api_base}{path}"
        resp = self._get(self._json_client, url, params=params or None)
        return resp.json()["response"]

    # -- resources ---------------------------------------------------------
    def album(self, album_id: int, *, text_format: str = "plain") -> dict[str, Any]:
        """Return the album object (name, artist, cover art, ...)."""
        return self._api_get(f"/albums/{album_id}", text_format=text_format)["album"]

    def album_tracks(self, album_id: int, *, per_page: int = 50) -> list[dict[str, Any]]:
        """Return the ordered track list for an album.

        Each element is a track object whose ``song`` key holds the song stub.
        """
        return self._api_get(f"/albums/{album_id}/tracks", per_page=per_page)["tracks"]

    def song(self, song_id: int, *, text_format: str = "plain") -> dict[str, Any]:
        """Return the full song object for ``song_id``."""
        return self._api_get(f"/songs/{song_id}", text_format=text_format)["song"]

    def iter_referents(
        self, song_id: int, *, text_format: str = "plain,html", per_page: int = 50
    ) -> Iterator[dict[str, Any]]:
        """Yield every referent for a song, transparently paginating.

        Each referent carries an ``annotations`` list; each annotation has a
        ``verified`` flag (authorial annotations are ``verified: true``).
        """
        page = 1
        while True:
            resp = self._api_get(
                "/referents",
                song_id=song_id,
                text_format=text_format,
                per_page=per_page,
                page=page,
            )
            referents = resp.get("referents", [])
            if not referents:
                break
            yield from referents
            if len(referents) < per_page:
                break
            page += 1

    def referents(self, song_id: int, **kwargs: Any) -> list[dict[str, Any]]:
        """Eager list form of :meth:`iter_referents`."""
        return list(self.iter_referents(song_id, **kwargs))

    def fetch_song_page(self, url: str) -> str:
        """Fetch the rendered HTML of a Genius song page (for lyrics scraping)."""
        return self._get(self._web_client, url).text
