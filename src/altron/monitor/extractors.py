"""HTML extraction using only the standard library.

Why no BeautifulSoup / lxml? Two heavy dependencies for what is, at the
end of the day, "give me the text inside these elements" and "is this
word on the page". ``html.parser.HTMLParser`` handles that in ~80 lines
and means the monitor has zero third-party deps beyond what the rest of
Altron already requires (pydantic, pyyaml, numpy, pandas).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable


@dataclass
class ExtractionResult:
    found: bool
    values: list[str]
    error: str | None = None


# --------------------------------------------------------------------------- #
# text normalization
# --------------------------------------------------------------------------- #


_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _WS.sub(" ", text).strip()


def strip_tags(html: str) -> str:
    """Remove ``<script>``/``<style>``/``<noscript>`` then drop all tags."""
    cleaned = re.sub(
        r"<(script|style|noscript)\b[^>]*>.*?</\1\s*>",
        " ",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return normalize(cleaned)


def visible_text(html: str, ignore_selectors: Iterable[str] = ()) -> str:
    """Return the page's visible text with the noise selectors removed.

    ``ignore_selectors`` is a tiny CSS-subset that matches elements by
    tag name, ``id`` value, or a single class name. Enough to strip
    ``<nav>``, ``<footer>``, ``<div id="cookie-banner">`` etc. before
    hashing.
    """
    body = html
    for selector in ignore_selectors:
        body = _strip_simple(body, selector)
    return strip_tags(body)


_SELECTOR_RE = re.compile(
    r"^(?P<tag>[a-zA-Z][a-zA-Z0-9]*)?"
    r"(?:\#(?P<id>[A-Za-z0-9_\-]+))?"
    r"(?:\.(?P<cls>[A-Za-z0-9_\-]+))?$"
)


def _strip_simple(html: str, selector: str) -> str:
    match = _SELECTOR_RE.match(selector.strip())
    if not match:
        return html
    tag = (match.group("tag") or "").lower()
    eid = match.group("id")
    cls = match.group("cls")
    if eid:
        # <tag id="value" ...> ... </tag>
        pattern = re.compile(
            rf"<\s*{tag or '[a-zA-Z][a-zA-Z0-9]*'}\b[^>]*\bid\s*=\s*[\"']{re.escape(eid)}[\"'][^>]*>.*?</\s*{tag or '[a-zA-Z][a-zA-Z0-9]*'}\s*>",
            re.IGNORECASE | re.DOTALL,
        )
        return pattern.sub(" ", html)
    if cls:
        pattern = re.compile(
            rf"<\s*{tag or '[a-zA-Z][a-zA-Z0-9]*'}\b[^>]*\bclass\s*=\s*[\"'][^\"']*\b{re.escape(cls)}\b[^\"']*[\"'][^>]*>.*?</\s*{tag or '[a-zA-Z][a-zA-Z0-9]*'}\s*>",
            re.IGNORECASE | re.DOTALL,
        )
        return pattern.sub(" ", html)
    if tag:
        pattern = re.compile(
            rf"<\s*{tag}\b[^>]*>.*?</\s*{tag}\s*>", re.IGNORECASE | re.DOTALL
        )
        return pattern.sub(" ", html)
    return html


# --------------------------------------------------------------------------- #
# selector extraction
# --------------------------------------------------------------------------- #


class _SelectorParser(HTMLParser):
    """Collect text for elements whose tag/id/class matches a target selector.

    Supports a tiny CSS subset: ``tag``, ``#id``, ``.class``, and
    ``tag.class`` / ``tag#id``. It also matches when the *attribute* is
    present even if the tag is different (e.g. ``.price`` matches any
    element with class="...price..."). XPath is not supported.
    """

    def __init__(self, tag: str | None, eid: str | None, cls: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self._tag = (tag or "").lower()
        self._eid = eid
        self._cls = cls
        self._depth: list[tuple[bool, str]] = []  # (matches, text accumulator)
        self._results: list[str] = []
        self._error: str | None = None

    def _attrs_match(self, attrs: list[tuple[str, str | None]]) -> bool:
        attr_map = {k.lower(): (v or "").lower() for k, v in attrs}
        if self._eid and attr_map.get("id") != self._eid.lower():
            return False
        if self._cls and self._cls.lower() not in attr_map.get("class", "").split():
            return False
        return True

    def _tag_match(self, tag: str) -> bool:
        # If no tag was specified in the selector, accept any tag.
        return not self._tag or self._tag == tag.lower()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._depth.append((self._attrs_match(attrs) and self._tag_match(tag), ""))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # self-closing tags: nothing to descend into
        return

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        matched, text = self._depth.pop()
        if matched and text.strip():
            self._results.append(normalize(text))

    def handle_data(self, data: str) -> None:
        # Walk up the open-tag stack and append to the *innermost matching*
        # ancestor. Otherwise text inside a nested non-matching child
        # (e.g. <div id="main"><span>hello</span></div>) would be lost.
        for index in range(len(self._depth) - 1, -1, -1):
            if self._depth[index][0]:
                matched, text = self._depth[index]
                self._depth[index] = (matched, text + data)
                return


def extract_selectors(html: str, selectors: Iterable[str]) -> dict[str, ExtractionResult]:
    results: dict[str, ExtractionResult] = {}
    for selector in selectors:
        selector = selector.strip()
        match = _SELECTOR_RE.match(selector)
        if not match:
            results[selector] = ExtractionResult(False, [], f"unsupported selector: {selector}")
            continue
        parser = _SelectorParser(match.group("tag"), match.group("id"), match.group("cls"))
        try:
            parser.feed(html)
            parser.close()
        except Exception as exc:  # noqa: BLE001
            results[selector] = ExtractionResult(False, [], str(exc))
            continue
        results[selector] = ExtractionResult(
            found=bool(parser._results),  # noqa: SLF001
            values=parser._results,  # noqa: SLF001
        )
    return results


# --------------------------------------------------------------------------- #
# keyword / regex
# --------------------------------------------------------------------------- #


def extract_keywords(html: str, keywords: Iterable[str]) -> dict[str, bool]:
    text = html.lower()
    return {kw.lower(): kw.lower() in text for kw in keywords}


def extract_regex(html: str, pattern: str) -> ExtractionResult:
    compiled = re.compile(pattern)
    matches = compiled.findall(html)[:5]
    values = [m if isinstance(m, str) else " ".join(m) for m in matches]
    return ExtractionResult(found=bool(matches), values=values)


def strip_ignored(html: str, ignore_selectors: Iterable[str]) -> str:
    if not ignore_selectors:
        return html
    for selector in ignore_selectors:
        html = _strip_simple(html, selector)
    return html
