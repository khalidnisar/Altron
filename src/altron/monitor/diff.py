"""Tiny change detection: hash normalized text + a short excerpt of what changed.

We do not compute character-level diffs here — the runner only needs to
answer two questions:

  1. "Did the page change?"  (compare SHA-256 of normalized text)
  2. "What does the new content look like?"  (return the first ~200 chars
     of the new visible text as a sample)

That's enough for the alert message. Users who need the full diff can
open the page.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass
class PageDiff:
    changed: bool
    reason: str
    old_hash: str
    new_hash: str
    new_excerpt: str


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def diff_pages(
    old_text: str,
    new_text: str,
    *,
    min_change_chars: int = 20,
    excerpt_chars: int = 200,
) -> PageDiff:
    """Compare two normalized page texts.

    A change is reported when the SHA-256 of the normalized text differs
    *and* the length delta (cheap proxy for "how much actually changed")
    is at least ``min_change_chars``. The cheap length check filters out
    whitespace jitter, banner rotations, and other tiny re-renders.
    """
    old_n = _normalize(old_text)
    new_n = _normalize(new_text)
    old_hash = hash_text(old_n)
    new_hash = hash_text(new_n)
    if old_hash == new_hash:
        return PageDiff(False, "identical", old_hash, new_hash, "")
    delta = abs(len(new_n) - len(old_n))
    if delta < min_change_chars:
        return PageDiff(False, f"below threshold ({delta}<{min_change_chars})", old_hash, new_hash, "")
    excerpt = new_n[:excerpt_chars] + ("…" if len(new_n) > excerpt_chars else "")
    return PageDiff(True, "content changed", old_hash, new_hash, excerpt)


def values_changed(old: list[str], new: list[str]) -> bool:
    """Stable comparison that ignores order and whitespace jitter."""
    norm = lambda vs: sorted(_norm(v) for v in vs)  # noqa: E731
    return norm(old) != norm(new)


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
