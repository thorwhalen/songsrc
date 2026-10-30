"""Timestamped lyrics for song segmentation.

To play the *right slice of audio* for a lyric, we need to know **when** each
lyric line occurs in the recording. Two levels of precision:

- **Line-level** (this module): fetched for free from `LRCLIB
  <https://lrclib.net>`_, which serves crowd-synced ``.lrc`` lyrics (a
  ``[mm:ss.xx] text`` per line). No audio and no API key required.
- **Word-level** (later, see the ``audio`` module + issue #4): forced alignment
  (aeneas / WhisperX / MFA) run against a local audio file you own.

:func:`fetch_synced_lyrics` returns a raw LRCLIB record; :func:`parse_lrc`
turns its ``syncedLyrics`` into ``LyricTiming`` rows with an explicit
``[start, end)`` window per line (``end`` = next line's start), which is exactly
what you hand to a ``lacing`` ``MediaRef`` / ``TimeInterval`` to cut a segment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

import httpx

_LRCLIB = "https://lrclib.net/api"
_UA = "songsrc (https://github.com/thorwhalen/songsrc; personal research)"
_LRC_LINE = re.compile(r"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$")


@dataclass(frozen=True)
class LyricTiming:
    """One synced lyric line with a half-open ``[start_s, end_s)`` window."""

    index: int
    start_s: float
    end_s: float | None  # None for the final line (unknown tail)
    text: str

    @property
    def duration_s(self) -> float | None:
        return None if self.end_s is None else round(self.end_s - self.start_s, 3)


def search_lrclib(
    query: str, *, timeout: float = 30.0
) -> list[dict[str, Any]]:
    """Search LRCLIB; each result may carry ``syncedLyrics`` (LRC) + metadata."""
    r = httpx.get(
        f"{_LRCLIB}/search",
        params={"q": query},
        headers={"User-Agent": _UA},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def fetch_synced_lyrics(
    *,
    track: str,
    artist: str,
    album: str | None = None,
    duration: float | None = None,
    lrclib_id: int | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Return the best LRCLIB record for a song (raw dict with ``syncedLyrics``).

    Prefer the exact-match ``/get`` endpoint (needs track+artist, optionally
    album+duration for disambiguation); fall back to ``/search`` and pick the
    first result that actually has synced lyrics.
    """
    headers = {"User-Agent": _UA}
    if lrclib_id is not None:
        r = httpx.get(f"{_LRCLIB}/get/{lrclib_id}", headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()

    params: dict[str, Any] = {"track_name": track, "artist_name": artist}
    if album:
        params["album_name"] = album
    if duration is not None:
        params["duration"] = round(duration)
    r = httpx.get(f"{_LRCLIB}/get", params=params, headers=headers, timeout=timeout)
    if r.status_code == 200:
        rec = r.json()
        if rec.get("syncedLyrics"):
            return rec

    # Fall back to search.
    for rec in search_lrclib(f"{track} {artist}", timeout=timeout):
        if rec.get("syncedLyrics"):
            return rec
    raise LookupError(f"No synced lyrics found for {track!r} by {artist!r}")


def parse_lrc(synced_lyrics: str) -> list[LyricTiming]:
    """Parse an LRC blob into ``LyricTiming`` rows with computed end times.

    Blank lyric lines (instrumental gaps) are kept as timing anchors only if
    they carry text; empty-text timestamps still advance the clock, so the
    previous line's ``end_s`` reflects the real gap.
    """
    stamped: list[tuple[float, str]] = []
    for raw in synced_lyrics.splitlines():
        m = _LRC_LINE.match(raw.strip())
        if not m:
            continue
        minutes, seconds, text = m.groups()
        start = int(minutes) * 60 + float(seconds)
        stamped.append((round(start, 3), text.strip()))

    stamped.sort(key=lambda t: t[0])
    rows: list[LyricTiming] = []
    idx = 0
    for i, (start, text) in enumerate(stamped):
        end = stamped[i + 1][0] if i + 1 < len(stamped) else None
        if not text:  # pure timing anchor / instrumental — skip as a lyric row
            continue
        rows.append(LyricTiming(index=idx, start_s=start, end_s=end, text=text))
        idx += 1
    return rows


def timings_to_dicts(rows: list[LyricTiming]) -> list[dict[str, Any]]:
    """Serialisable form (for JSON / handing into the lacing loader)."""
    return [asdict(r) | {"duration_s": r.duration_s} for r in rows]
