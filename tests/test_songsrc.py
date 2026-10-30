"""The pure parts: lyrics extraction, LRC parsing, annotation normalisation, and the client's retry."""

import httpx

from songsrc import GeniusClient, LyricTiming, extract_lyrics, parse_lrc, slug
from songsrc.acquire import _normalise_referent

HTML = (
    '<div data-lyrics-container="true">[Verse 1]<br/>Line one<br/>Line two'
    '<div data-exclude-from-selection="true">junk</div></div>'
)


def test_extract_lyrics_keeps_lines_and_drops_chrome():
    assert extract_lyrics(HTML) == "[Verse 1]\nLine one\nLine two"
    assert extract_lyrics("<html>nothing</html>") == ""


def test_parse_lrc_windows_and_gaps():
    rows = parse_lrc("[00:01.50] a\n[00:03.00]\n[00:05.00] b\nnot a stamp")
    assert rows == [LyricTiming(0, 1.5, 3.0, "a"), LyricTiming(1, 5.0, None, "b")]
    assert rows[0].duration_s == 1.5 and rows[1].duration_s is None


def test_referent_keeps_the_verified_flag():
    ref = {"id": 1, "fragment": "f", "annotations": [{"verified": 1, "body": {"plain": "x"}, "authors": []}]}
    assert _normalise_referent(ref)["annotations"][0]["verified"] is True


def test_slug():
    assert slug("My Shot!") == "my-shot"


def test_client_retries_transient_failures(monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"response": {"song": {"id": 1}}})

    monkeypatch.setattr("time.sleep", lambda s: None)
    client = GeniusClient(access_token=None, min_interval=0)
    client._json_client = httpx.Client(transport=httpx.MockTransport(handler))
    assert client.song(1) == {"id": 1} and len(calls) == 3
