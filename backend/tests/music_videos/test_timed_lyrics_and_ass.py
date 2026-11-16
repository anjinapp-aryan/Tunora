"""TimedLyrics validation, ASS text safety, and the aligner's grouping rules (Phase 23; the
malicious-input cases are the Phase 22B security suite, ported)."""

from __future__ import annotations

import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.music_videos import ass_builder, timed_lyrics as tl
from app.music_videos.align_worker import group, lyric_lines


def doc(**over):
    d = {"version": 1, "duration": 60.0, "lines": [
        {"text": "hello world", "words": [{"text": "hello", "start": 1.0, "end": 1.5},
                                          {"text": "world", "start": 1.5, "end": 2.0}]}]}
    d.update(over)
    return d


def word_doc(start, end):
    return doc(lines=[{"text": "x", "words": [{"text": "x", "start": start, "end": end}]}])


@pytest.mark.parametrize("bad, message", [
    (word_doc(-1.0, 1.0), "non-negative"),
    (word_doc(math.nan, 1.0), "finite"),
    (word_doc(1.0, math.inf), "finite"),
    (word_doc(5.0, 4.0), "ends before it starts"),
    (word_doc(70.0, 71.0), "after the song"),
    (word_doc(True, 2.0), "must be a number"),
    (word_doc("1", 2.0), "must be a number"),
    (doc(version=2), "version 1"),
    (doc(duration=math.nan), "finite"),
    (doc(lines=[{"text": "a b", "words": [{"text": "a", "start": 5, "end": 6}, {"text": "b", "start": 1, "end": 2}]}]), "out of order"),
    (doc(lines=[doc()["lines"][0]] * (tl.MAX_LINES + 1)), "at most"),
    (doc(lines=[{"text": "a" * 500, "words": [{"text": "a", "start": 1, "end": 2}]}]), "longer than"),
    (doc(lines=[{"text": "x", "words": []}]), "1..64 words"),
    ("not a dict", "version 1"),
])
def test_malformed_timed_lyrics_are_rejected(bad, message):
    with pytest.raises(tl.TimedLyricsError, match=message):
        tl.parse(bad)


def test_huge_or_malformed_files_are_rejected(tmp_path):
    big = tmp_path / "big.json"
    big.write_text(" " * (tl.MAX_FILE_BYTES + 1))
    with pytest.raises(tl.TimedLyricsError, match="too large"):
        tl.load(big)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(tl.TimedLyricsError, match="UTF-8 JSON"):
        tl.load(bad)
    with pytest.raises(tl.TimedLyricsError, match="not found"):
        tl.load(tmp_path / "missing.json")


EVIL = [
    "{\\p1}m 0 0 l 1080 0 1080 1920 0 1920{\\p0}",   # ASS vector drawing
    "{\\fnImpact\\fs400}HUGE",                         # font/size override
    "a\\Nb\\nc",                                       # ASS line breaks
    "[0:v]drawtext=text=x,ass=../../etc/passwd",       # FFmpeg filter syntax
    "'; rm -rf / ; $(calc.exe) `whoami` %PATH%",       # shell syntax
    "line\r\nbreak\x00\x07",                           # control characters
]


def test_lyric_text_is_neutralised_into_plain_text():
    lines = [{"text": t, "words": [{"text": t, "start": 1.0 + i, "end": 1.5 + i}]} for i, t in enumerate(EVIL)]
    script = ass_builder.build(tl.parse(doc(lines=lines)), "minimal_white", 1080, 1920, title="{\\p1}evil title")
    events = [l.split(",,", 1)[1] for l in script.splitlines() if l.startswith("Dialogue:")]
    assert len(events) == len(EVIL) + 0  # title needs a >= 3 s intro; lines start at 1 s here
    for e in events:
        user_part = re.sub(r"\{\\(fad|k|kf|r)[^}]*\}", "", e)  # remove only the tags Tunora writes
        assert "{" not in user_part and "}" not in user_part and "\\p" not in user_part and "\\fn" not in user_part
        assert all(ch.isprintable() for ch in user_part)
    assert "[Events]" in script and script.count("[Events]") == 1  # no section injection


def test_long_lines_are_one_event_so_libass_stacks_the_wrapped_rows():
    long = "When the night is getting colder and I cannot see the way ahead of me I remember why"
    lines = [{"text": t, "words": [{"text": w, "start": 1 + i * 4 + j * 0.2, "end": 1.15 + i * 4 + j * 0.2}
                                   for j, w in enumerate(t.split())]} for i, t in enumerate([long, long])]
    script = ass_builder.build(tl.parse(doc(lines=lines)), "bold", 1080, 1920)
    assert "WrapStyle: 0" in script
    first = [l for l in script.splitlines() if l.startswith("Dialogue:")][0]
    assert first.count("\\N{\\rNext}") == 1  # active line + next line in one event, never two rows placed by hand


def test_lyric_lines_skip_section_tags_and_punctuation_only_tokens():
    assert lyric_lines("[Verse 1]\nI wake up - today\n\n  [Chorus]  \n...\nRise!") == ["I wake up today", "Rise!"]


def test_grouping_drops_pinned_tail_and_collapsed_lines_but_keeps_real_ones():
    lines = ["one two", "three four", "five six"]
    words = [("one", 1.0, 1.4), ("two", 1.4, 2.0),        # real
             ("three", 5.0, 5.0), ("four", 5.0, 5.05),   # collapsed (0.05 s for 2 words)
             ("five", 60.0, 60.0), ("six", 60.0, 60.0)]  # pinned at the end of a 60 s song
    timed, unaligned = group(words, lines, 60.0)
    assert [l["text"] for l in timed] == ["one two"] and unaligned == ["three four", "five six"]


def test_a_line_whose_tail_is_pinned_to_the_end_is_dropped_even_if_it_is_not_collapsed():
    # The real Phase 22A case: "There" aligned at 55.1 s, the rest of the line pinned at 60.0 s.
    words = [("There", 55.11, 55.81), ("were", 60.0, 60.0), ("times", 60.0, 60.0), ("I", 60.0, 60.0)]
    timed, unaligned = group(words, ["There were times I"], 60.0)
    assert timed == [] and unaligned == ["There were times I"]


def test_align_worker_refuses_to_run_with_an_unapproved_ffmpeg(tmp_path):
    lyrics = tmp_path / "l.txt"
    lyrics.write_text("hello")
    proc = subprocess.run([sys.executable, "-m", "app.music_videos.align_worker", "--audio", "x.flac",
                           "--lyrics-file", str(lyrics), "--ffmpeg-dir", str(tmp_path), "--out", str(tmp_path / "o")],
                          capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2])
    assert proc.returncode == 6
