"""Extract plain-text lyrics from a Genius song page.

Modern Genius pages render lyrics inside one or more
``<div data-lyrics-container="true">`` elements. Within a container, visual line
breaks are ``<br>`` tags and section headers (``[Verse 1]`` etc.) sit in their
own inline elements. :func:`extract_lyrics` flattens a container to text while
preserving line breaks, and drops the inline UI cruft Genius injects
(annotation-share buttons, "Read More" links, ad placeholders).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

# Elements whose text is UI chrome, not lyrics.
_JUNK_SELECTORS = [
    '[class*="LyricsHeader"]',
    '[class*="RightSidebar"]',
    '[class*="Ad__"]',
    '[data-exclude-from-selection]',
]


def extract_lyrics(html: str) -> str:
    """Return the plain-text lyrics found in a Genius song-page ``html``.

    Line breaks are preserved; leading/trailing whitespace is stripped and runs
    of 3+ blank lines are collapsed to 2. Returns ``""`` if no lyrics container
    is present (e.g. an interstitial or non-song page).
    """
    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select('div[data-lyrics-container="true"]')
    if not containers:
        # Fall back to the legacy single ``.lyrics`` block if present.
        legacy = soup.select_one(".lyrics")
        containers = [legacy] if legacy else []

    parts = [_container_text(c) for c in containers if c is not None]
    text = "\n".join(p for p in parts if p)
    return _tidy(text)


def _container_text(container: Tag) -> str:
    """Flatten a lyrics container to text, turning ``<br>`` into newlines."""
    for junk_sel in _JUNK_SELECTORS:
        for junk in container.select(junk_sel):
            junk.decompose()

    out: list[str] = []

    def walk(node: Tag | NavigableString) -> None:
        if isinstance(node, NavigableString):
            out.append(str(node))
            return
        if not isinstance(node, Tag):
            return
        if node.name == "br":
            out.append("\n")
            return
        for child in node.children:
            walk(child)
        # Section headers like ``[Verse 1]`` render as block-ish elements; a
        # trailing newline keeps them on their own line.
        if node.name in {"div", "p"}:
            out.append("\n")

    walk(container)
    return "".join(out)


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\xa0", " ")
    # Trim trailing spaces on each line.
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # Collapse 3+ blank lines to a single blank line separator.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
