# songsrc

Lean song acquisition from Genius and LRCLIB. Dependencies: `httpx` and `beautifulsoup4`, nothing else.

```python
from songsrc import GeniusClient, acquire_song, fetch_synced_lyrics, parse_lrc

with GeniusClient() as client:                      # GENIUS_ACCESS_TOKEN switches to the official API
    song = acquire_song(client, {"id": 12345})      # metadata, lyrics, referents with annotations

rows = parse_lrc(fetch_synced_lyrics(track="Burn", artist="Hamilton")["syncedLyrics"])
rows[0].start_s, rows[0].end_s, rows[0].text         # one [start, end) window per line
```

`acquire_song` returns the record Hamilton's `data/songs/*.json` is made of, so its keys are stable. The Genius client throttles (0.34 s) and retries 429/5xx with backoff. Genius's tokenless path is behind Cloudflare for non-browsers: set `GENIUS_ACCESS_TOKEN` for the official API.

Used by [griot](https://github.com/thorwhalen/griot) (research adapters) and Hamilton (`hamilton_genius`).
