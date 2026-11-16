"""TimedLyrics: the only lyric input the Music Video renderer accepts (Phase 22B, reused unchanged).

The renderer never decides *what* the lyrics are or *when* they are sung. Something upstream
(forced alignment, manual timing, a future provider) produces TimedLyrics; the renderer only draws
them. Everything here is validated as untrusted input: finite, non-negative, ordered times,
bounded sizes, and text reduced to printable single-line strings.

Data model (JSON):
    {"version": 1, "duration": 60.0,
     "source": {"kind": "forced_alignment", ...},          # provenance, informational only
     "lines": [{"text": "...", "words": [{"text": "I", "start": 15.1, "end": 15.3}, ...]}],
     "unaligned_lines": ["..."]}                            # lyrics that could NOT be timed

`source.kind` names the provider ("forced_alignment" today). A future manual-timing provider
produces the same document with kind "manual"; the renderer does not change.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_BYTES = 5_000_000
MAX_DURATION = 1200.0          # 20 minutes; ACE-Step itself caps songs at 10
MAX_LINES = 2000
MAX_WORDS_PER_LINE = 64
MAX_LINE_CHARS = 200
TIME_SLACK = 0.5               # a word may end at most this far past the stated duration


class TimedLyricsError(ValueError):
    """The TimedLyrics payload is malformed or unsafe. Message is safe to show."""


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Line:
    text: str
    words: tuple[Word, ...]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end


@dataclass(frozen=True)
class TimedLyrics:
    duration: float
    lines: tuple[Line, ...]
    source: dict
    unaligned_lines: tuple[str, ...] = ()


def _time(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TimedLyricsError(f"{what} must be a number")
    if not math.isfinite(value) or value < 0:
        raise TimedLyricsError(f"{what} must be a finite, non-negative number")
    return float(value)


def clean_text(value: object, what: str) -> str:
    """Collapse all whitespace (incl. newlines) and drop non-printable characters."""
    if not isinstance(value, str):
        raise TimedLyricsError(f"{what} must be text")
    text = "".join(ch for ch in " ".join(value.split()) if ch.isprintable())
    if not text:
        raise TimedLyricsError(f"{what} is empty")
    if len(text) > MAX_LINE_CHARS:
        raise TimedLyricsError(f"{what} is longer than {MAX_LINE_CHARS} characters")
    return text


def parse(data: object) -> TimedLyrics:
    """Validate a decoded JSON object and return TimedLyrics, or raise TimedLyricsError."""
    if not isinstance(data, dict) or data.get("version") != 1:
        raise TimedLyricsError("unsupported TimedLyrics document (expected version 1)")
    duration = _time(data.get("duration"), "duration")
    if not 0 < duration <= MAX_DURATION:
        raise TimedLyricsError(f"duration must be in (0, {MAX_DURATION}] seconds")
    raw_lines = data.get("lines")
    if not isinstance(raw_lines, list) or len(raw_lines) > MAX_LINES:
        raise TimedLyricsError(f"lines must be a list of at most {MAX_LINES} entries")

    lines: list[Line] = []
    previous_start = 0.0
    for i, raw in enumerate(raw_lines):
        if not isinstance(raw, dict):
            raise TimedLyricsError(f"line {i} is not an object")
        raw_words = raw.get("words")
        if not isinstance(raw_words, list) or not 0 < len(raw_words) <= MAX_WORDS_PER_LINE:
            raise TimedLyricsError(f"line {i} must have 1..{MAX_WORDS_PER_LINE} words")
        words = []
        for j, w in enumerate(raw_words):
            if not isinstance(w, dict):
                raise TimedLyricsError(f"line {i} word {j} is not an object")
            start = _time(w.get("start"), f"line {i} word {j} start")
            end = _time(w.get("end"), f"line {i} word {j} end")
            if end < start:
                raise TimedLyricsError(f"line {i} word {j} ends before it starts")
            if end > duration + TIME_SLACK:
                raise TimedLyricsError(f"line {i} word {j} ends after the song")
            if start < previous_start:
                raise TimedLyricsError(f"line {i} word {j} is out of order")
            previous_start = start
            words.append(Word(clean_text(w.get("text"), f"line {i} word {j}"), start, end))
        lines.append(Line(clean_text(raw.get("text"), f"line {i}"), tuple(words)))

    unaligned = data.get("unaligned_lines", [])
    if not isinstance(unaligned, list) or len(unaligned) > MAX_LINES:
        raise TimedLyricsError("unaligned_lines must be a list")
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    return TimedLyrics(duration, tuple(lines), source,
                       tuple(clean_text(t, "unaligned line") for t in unaligned))


def load(path: Path) -> TimedLyrics:
    """Read TimedLyrics from a JSON file (a file, never a command-line argument)."""
    path = Path(path)
    if not path.is_file():
        raise TimedLyricsError("TimedLyrics file not found")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise TimedLyricsError("TimedLyrics file is too large")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TimedLyricsError("TimedLyrics file is not valid UTF-8 JSON") from exc
    return parse(data)
