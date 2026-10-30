"""Song acquisition from Genius and LRCLIB, with only ``httpx`` and ``beautifulsoup4``.

The song-generic half of what a lyrics-driven production needs, kept lean so a
lyrics-only consumer (a song video, an album study) does not install a commentary
stack:

- :class:`GeniusClient`: a polite client (throttle, retry with backoff) over Genius's
  official and tokenless JSON APIs and song pages;
- :func:`extract_lyrics`: plain-text lyrics from a Genius song page;
- :func:`acquire_song`: one song's metadata, lyrics and normalised referents/annotations;
- :func:`fetch_synced_lyrics`, :func:`parse_lrc`, :class:`LyricTiming`: crowd-synced
  line timings from LRCLIB, with an explicit ``[start, end)`` window per line.

Genius's tokenless path is behind Cloudflare for non-browsers; set ``GENIUS_ACCESS_TOKEN``
for the official API.
"""

from songsrc.acquire import acquire_song, slug
from songsrc.client import GeniusClient
from songsrc.lyrics import extract_lyrics
from songsrc.timing import (
    LyricTiming,
    fetch_synced_lyrics,
    parse_lrc,
    search_lrclib,
    timings_to_dicts,
)

__all__ = [
    "GeniusClient",
    "LyricTiming",
    "acquire_song",
    "extract_lyrics",
    "fetch_synced_lyrics",
    "parse_lrc",
    "search_lrclib",
    "slug",
    "timings_to_dicts",
]
