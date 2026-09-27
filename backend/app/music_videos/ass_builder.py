"""TimedLyrics -> an ASS subtitle script that libass (ISC) renders inside FFmpeg.

Reused unchanged from the validated Phase 22B prototype (docs/PHASE-23-MUSIC-VIDEO-COMPOSER.md).

Layout is delegated to libass instead of hand-placed pixel rows (the cause of the Phase 22A
overlap): each screen is ONE event holding the active line and, dimmed below it, the next line,
separated by a hard break. libass wraps long lines inside the side margins (WrapStyle 0) and
stacks the wrapped rows of a single event itself, so rows can never overlap, however long.

Animation: a short fade per line, and a left-to-right karaoke fill per word (\\kf).
Style values adapted from dcmcand/dynamic-typography-videos src/styles/presets.ts (Apache-2.0).
Lyric text is untrusted: ASS override syntax ({, }, \\) is neutralised before it is written.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.music_videos.timed_lyrics import TimedLyrics

LEAD_IN = 0.35        # show a line this long before its first word
HOLD = 1.2            # keep the last line up this long after its last word
GAP_BLANK = 4.0       # longer silences between lines (instrumental) clear the screen
FADE_MS = 150


@dataclass(frozen=True)
class Style:
    font: str
    active_size: int
    next_size: int
    sung: str           # RGB hex, colour once a word is reached
    unsung: str         # RGB hex, colour before
    unsung_alpha: int   # 0 opaque .. 255 invisible
    next_alpha: int
    outline: float
    shadow: float
    dim: float          # 0..1 black overlay on the background for readability
    margin_x: int = 90  # side safe margin at 1080 px wide


STYLES = {
    # White, clean, soft shadow -- closest to the reference videos.
    "minimal_white": Style("Poppins SemiBold", 92, 60, "FFFFFF", "FFFFFF", 0x50, 0x40, 3.0, 3, 0.30),
    # Adapted from the candidate's "dreamy" preset (#cc99ff / #ff99cc).
    "dreamy": Style("Poppins SemiBold", 90, 58, "FF99CC", "CC99FF", 0x30, 0x80, 2.0, 4, 0.35),
    # Adapted from the candidate's "bold" preset (white -> #ffff00 highlight).
    "bold": Style("Poppins SemiBold", 100, 62, "FFFF00", "FFFFFF", 0x00, 0x60, 5.0, 2, 0.25),
}


def _colour(rgb: str, alpha: int = 0) -> str:
    return f"&H{alpha:02X}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}"


def escape(text: str) -> str:
    """Neutralise ASS override/escape syntax in untrusted lyric text."""
    # Fullwidth look-alikes (U+FF3C, U+FF5B, U+FF5D) cannot start an escape or override block.
    return text.replace("\\", "＼").replace("{", "｛").replace("}", "｝")


def _ts(seconds: float) -> str:
    cs = max(0, round(seconds * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def build(lyrics: TimedLyrics, style_name: str, width: int, height: int,
          title: str | None = None) -> str:
    s = STYLES[style_name]
    margin_v = int(height * 0.08)
    header = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Active,{s.font},{s.active_size},{_colour(s.sung)},{_colour(s.unsung, s.unsung_alpha)},"
        f"{_colour('000000', 0x40)},{_colour('000000', 0x50)},0,0,0,0,100,100,0,0,1,{s.outline},{s.shadow},"
        f"5,{s.margin_x},{s.margin_x},{margin_v},1",
        f"Style: Next,{s.font},{s.next_size},{_colour('FFFFFF', s.next_alpha)},{_colour('FFFFFF', s.next_alpha)},"
        f"{_colour('000000', 0x60)},{_colour('000000', 0x70)},0,0,0,0,100,100,0,0,1,2,2,"
        f"5,{s.margin_x},{s.margin_x},{margin_v},1",
        f"Style: Title,{s.font},{s.active_size + 8},{_colour('FFFFFF')},{_colour('FFFFFF')},"
        f"{_colour('000000', 0x60)},{_colour('000000', 0x80)},0,0,0,0,100,100,2,0,1,{s.outline},{s.shadow},"
        f"5,{s.margin_x},{s.margin_x},{margin_v},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events = []
    lines = lyrics.lines
    if title and lines and lines[0].start >= 3.0:
        events.append(f"Dialogue: 0,{_ts(0.5)},{_ts(lines[0].start - 0.8)},Title,,0,0,0,,"
                      f"{{\\fad(600,400)}}{escape(title)}")
    shown_until = 0.0
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        start = max(line.start - LEAD_IN, shown_until)
        end = min(line.end + HOLD, lyrics.duration)
        if nxt and nxt.start - line.end < GAP_BLANK:
            end = max(line.end, nxt.start - LEAD_IN)
        if end <= start:
            continue
        shown_until = end
        parts, cursor = [f"{{\\fad({FADE_MS},{FADE_MS})}}"], start
        for w in line.words:
            wait = max(0, round((w.start - cursor) * 100))
            fill = max(1, round((w.end - w.start) * 100))
            parts.append(f"{{\\k{wait}\\kf{fill}}}{escape(w.text)} ")
            cursor = w.start + fill / 100
        text = "".join(parts).rstrip()
        if nxt and nxt.start - line.end < GAP_BLANK:
            text += f"\\N{{\\rNext}}{escape(nxt.text)}"
        events.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Active,,0,0,0,,{text}")
    return "\n".join(header + events) + "\n"
