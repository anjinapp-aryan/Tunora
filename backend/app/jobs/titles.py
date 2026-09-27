"""Human-readable song titles.

A title is separate from the prompt, the job id and the storage key. The
strategy is deliberately simple and deterministic (no LLM): use the title the
user typed, otherwise the first few words of the prompt.
"""

from __future__ import annotations

import re

MAX_TITLE_LENGTH = 80
DEFAULT_TITLE = "Untitled song"
_DERIVED_WORDS = 6
_DERIVED_MAX_LENGTH = 60


def clean_title(text: object) -> str:
    """Strip control characters, collapse whitespace, and cap the length."""

    if not isinstance(text, str):
        return ""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:MAX_TITLE_LENGTH].strip()


def derive_title(prompt: object, provided: object = None) -> str:
    """The user's title if given, else the first words of the prompt, else a default."""

    title = clean_title(provided)
    if title:
        return title
    words = clean_title(prompt).split(" ")
    derived = " ".join(w for w in words[:_DERIVED_WORDS] if w)[:_DERIVED_MAX_LENGTH]
    derived = derived.rstrip(" ,.;:-–—").strip()
    if not derived:
        return DEFAULT_TITLE
    return derived[0].upper() + derived[1:]
