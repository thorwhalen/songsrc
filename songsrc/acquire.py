"""Acquire one song from Genius: metadata, lyrics and every referent/annotation.

:func:`acquire_song` scrapes a song's lyrics and collects every referent/annotation,
normalising the pieces we care about (keeping the authorial ``verified`` flag). The
record it returns is the on-disk shape consumers (e.g. Hamilton's ``data/songs``)
depend on, so its keys are stable.

Design note: normalisation is intentionally lossless-ish — the raw Genius fields
we drop are UI plumbing, not commentary. The two things the task cares about —
lyrics text and annotation bodies with their ``verified`` flag — are preserved
verbatim.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from songsrc.client import GeniusClient
from songsrc.lyrics import extract_lyrics

# A progress callback receives a human-readable status line.
Progress = Callable[[str], None]


def slug(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_-]+", "-", text) or "untitled"


def _normalise_annotation(ann: dict[str, Any]) -> dict[str, Any]:
    """Keep the commentary + the metadata that gives it authority/provenance."""
    body = ann.get("body") or {}
    authors = []
    for a in ann.get("authors") or []:
        if not isinstance(a, dict):
            authors.append({"name": a, "login": None, "attribution": None})
            continue
        user = a.get("user") or {}
        authors.append(
            {
                "name": user.get("name"),
                "login": user.get("login"),
                "attribution": a.get("attribution"),
            }
        )
    return {
        "id": ann.get("id"),
        "verified": bool(ann.get("verified")),  # authorial annotations are True
        "state": ann.get("state"),
        "url": ann.get("url"),
        "votes_total": ann.get("votes_total"),
        "comment_count": ann.get("comment_count"),
        "verified_by": [
            u.get("name") if isinstance(u, dict) else u
            for u in ann.get("verified_by") or []
        ],
        "authors": authors,
        "body_plain": body.get("plain"),
        "body_html": body.get("html"),
    }


def _normalise_referent(ref: dict[str, Any]) -> dict[str, Any]:
    """Keep the annotated fragment + its annotations."""
    return {
        "id": ref.get("id"),
        "fragment": ref.get("fragment"),
        "classification": ref.get("classification"),
        "is_description": ref.get("is_description"),
        "url": ref.get("url"),
        "range": ref.get("range"),
        "annotations": [_normalise_annotation(a) for a in ref.get("annotations") or []],
    }


def acquire_song(
    client: GeniusClient,
    song_stub: dict[str, Any],
    *,
    number: int | None = None,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Acquire one song: full metadata, lyrics, and all referents/annotations.

    Args:
        client: A live :class:`GeniusClient`.
        song_stub: A song object (at least ``id``); a track's ``song`` works.
        number: Track number within the album, if known.
        progress: Optional status callback.
    """
    song_id = song_stub["id"]
    song = client.song(song_id)
    title = song.get("title") or song_stub.get("title") or f"song-{song_id}"

    if progress:
        progress(f"  lyrics: {title}")
    html = client.fetch_song_page(song["url"])
    lyrics = extract_lyrics(html)

    if progress:
        progress(f"  annotations: {title}")
    referents = [_normalise_referent(r) for r in client.iter_referents(song_id)]
    n_verified = sum(
        1 for r in referents for a in r["annotations"] if a["verified"]
    )
    n_annotations = sum(len(r["annotations"]) for r in referents)

    return {
        "number": number,
        "id": song_id,
        "title": title,
        "full_title": song.get("full_title"),
        "url": song.get("url"),
        "primary_artist": (song.get("primary_artist") or {}).get("name"),
        "release_date": song.get("release_date"),
        "lyrics": lyrics,
        "lyrics_char_count": len(lyrics),
        "referent_count": len(referents),
        "annotation_count": n_annotations,
        "verified_annotation_count": n_verified,
        "referents": referents,
    }
