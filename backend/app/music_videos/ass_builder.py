"""TimedLyrics -> an ASS subtitle script that libass (ISC) renders inside FFmpeg.

Reused from the validated Phase 22B prototype (docs/PHASE-23-MUSIC-VIDEO-COMPOSER.md), extended in
Phase 25 with composable style primitives (docs/PHASE-25-MUSIC-VIDEO-VISUAL-POLISH.md).

Layout is delegated to libass instead of hand-placed pixel rows (the cause of the Phase 22A
overlap): each screen is ONE event holding the active line and, dimmed below it, the next line,
separated by a hard break. libass wraps long lines inside the side margins (WrapStyle 0) and
stacks the wrapped rows of a single event itself, so rows can never overlap, however long.

Animation (Phase 23 styles): a short fade per line and a left-to-right karaoke fill per word
(\\kf). Phase 25 styles add, as data on `Style`: capitals, a per-word "pop" (active word recoloured
with a vertical-only scale ease), a soft glow, a rising entrance, letter spacing, and a title card
from the first frame plus an end card. A Phase 23 style never uses the new path, so its output is
byte-identical to before.

Style values adapted from dcmcand/dynamic-typography-videos src/styles/presets.ts (Apache-2.0).
The per-word pop technique is adapted from sebetancurch/auto-caption autocaption/ass_builder.py
(MIT). Lyric text is untrusted: ASS override syntax ({, }, \\) is neutralised before it is written.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.music_videos.timed_lyrics import TimedLyrics

LEAD_IN = 0.35        # show a line this long before its first word
HOLD = 1.2            # keep the last line up this long after its last word
GAP_BLANK = 4.0       # longer silences between lines (instrumental) clear the screen
FADE_MS = 150
CARD_MIN = 1.5        # a title / end card needs at least this much free time


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
    dim: float          # 0..1 darkening of the background for readability
    margin_x: int = 90  # side safe margin at 1080 px wide
    # -- Phase 25 composable primitives. The defaults reproduce the Phase 23 look exactly. --
    caps: bool = False            # show lyrics and title in capitals
    word_mode: str = "fill"       # "fill": karaoke sweep | "pop": active word recoloured + popped
    highlight: str = "FFFFFF"     # RGB hex of the active word in "pop" mode
    pop_scale: int = 118          # vertical % the active word starts at before easing to 100; vertical
                                  # only, so a pop can never change the line's width or wrapping
    glow: float = 0.0             # blur radius on the text border: a soft halo instead of a hard edge
    rise: int = 0                 # px the lines rise into place as they fade in
    spacing: float = 0.0          # letter spacing
    title_card: str = "plain"     # "plain" | "cinematic": title from the first frame + an end card
    vignette: bool = False        # darken the frame edges (FFmpeg vignette filter, LGPL)
    drift: bool = False           # slow pan over video backgrounds too (images always pan)


STYLES = {
    # White, clean, soft shadow -- closest to the reference videos.
    "minimal_white": Style("Poppins SemiBold", 92, 60, "FFFFFF", "FFFFFF", 0x50, 0x40, 3.0, 3, 0.30),
    # Adapted from the candidate's "dreamy" preset (#cc99ff / #ff99cc).
    "dreamy": Style("Poppins SemiBold", 90, 58, "FF99CC", "CC99FF", 0x30, 0x80, 2.0, 4, 0.35),
    # Adapted from the candidate's "bold" preset (white -> #ffff00 highlight).
    "bold": Style("Poppins SemiBold", 100, 62, "FFFF00", "FFFFFF", 0x00, 0x60, 5.0, 2, 0.25),
    # Phase 25: big capitals, the sung word pops in warm gold, soft glow, lines rise in, title cards.
    "cinematic": Style("Poppins ExtraBold", 104, 62, "FFFFFF", "FFFFFF", 0x28, 0x40, 2.0, 0, 0.25,
                       caps=True, word_mode="pop", highlight="FFD98A", glow=6.0, rise=28, spacing=1.5,
                       title_card="cinematic", vignette=True, drift=True),
    # Phase 25: big capitals with a bright gold left-to-right sweep and a strong outline.
    "karaoke": Style("Poppins ExtraBold", 100, 62, "FFD23F", "FFFFFF", 0x00, 0x40, 5.0, 3, 0.30,
                     caps=True, glow=1.0, rise=20, spacing=1.0, title_card="cinematic",
                     vignette=True, drift=True),
}

_PHASE23 = Style("", 0, 0, "", "", 0, 0, 0, 0, 0)
_PRIMITIVES = ("caps", "word_mode", "glow", "rise", "spacing", "title_card")


def uses_primitives(s: Style) -> bool:
    """True if the style opts into any Phase 25 text primitive (else: the Phase 23 path)."""
    return any(getattr(s, f) != getattr(_PHASE23, f) for f in _PRIMITIVES)


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
    if uses_primitives(s):
        return "\n".join(header + _styled_events(lyrics, s, width, height, title)) + "\n"
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


# -- Phase 25: composable primitives ------------------------------------------------------------------


def _text(s: Style, raw: str) -> str:
    return escape(raw.upper() if s.caps else raw)


def _windows(lyrics: TimedLyrics) -> list[tuple]:
    """(line, joined_next_line_or_None, start, end): the same on-screen windows as the Phase 23 path."""
    out, shown_until, lines = [], 0.0, lyrics.lines
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        start = max(line.start - LEAD_IN, shown_until)
        end = min(line.end + HOLD, lyrics.duration)
        joined = nxt is not None and nxt.start - line.end < GAP_BLANK
        if joined:
            end = max(line.end, nxt.start - LEAD_IN)
        if end <= start:
            continue
        shown_until = end
        out.append((line, nxt if joined else None, start, end))
    return out


def _cards(lyrics: TimedLyrics, s: Style, windows: list, cx: int, cy: int, title: str) -> list[str]:
    """An opening title that is fully visible on the very first frame (the thumbnail) and slowly
    grows, and an end card, so the video never opens or closes on an empty background."""
    first = windows[0][2] if windows else lyrics.duration
    last = windows[-1][3] if windows else 0.0
    card = f"\\an5\\pos({cx},{cy})\\blur{max(s.glow, 2):g}\\fsp{max(s.spacing, 1) * 4:g}"
    events = []
    if first >= CARD_MIN:
        grow = round((first - 0.1) * 1000)
        events.append(f"Dialogue: 1,{_ts(0)},{_ts(first - 0.1)},Title,,0,0,0,,"
                      f"{{{card}\\fad(0,350)\\t(0,{grow},\\fscx108\\fscy108)}}{_text(s, title)}")
    if lyrics.duration - last >= CARD_MIN:
        events.append(f"Dialogue: 1,{_ts(last + 0.1)},{_ts(lyrics.duration)},Title,,0,0,0,,"
                      f"{{{card}\\fad(500,0)}}{_text(s, title)}")
    return events


def _styled_events(lyrics: TimedLyrics, s: Style, width: int, height: int, title: str | None) -> list[str]:
    cx, cy = width // 2, height // 2
    look = (f"\\blur{s.glow:g}" if s.glow else "") + (f"\\fsp{s.spacing:g}" if s.spacing else "")
    enter = f"\\an5\\move({cx},{cy + s.rise},{cx},{cy},0,320)" if s.rise else f"\\an5\\pos({cx},{cy})"
    still = f"\\an5\\pos({cx},{cy})"
    windows = _windows(lyrics)
    events = _cards(lyrics, s, windows, cx, cy, title) if title and s.title_card == "cinematic" else []

    for line, nxt, start, end in windows:
        tail = f"\\N{{\\rNext}}{_text(s, nxt.text)}" if nxt else ""
        if s.word_mode != "pop":
            parts, cursor = [f"{{{enter}{look}\\fad({FADE_MS * 2},{FADE_MS})}}"], start
            for w in line.words:
                wait = max(0, round((w.start - cursor) * 100))
                fill = max(1, round((w.end - w.start) * 100))
                parts.append(f"{{\\k{wait}\\kf{fill}}}{_text(s, w.text)} ")
                cursor = w.start + fill / 100
            events.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Active,,0,0,0,,{''.join(parts).rstrip()}{tail}")
            continue
        # "pop": one event per active word. Every event lays out the same text, so nothing moves:
        # only the active word's colour and vertical scale change (a pop never re-wraps a line).
        bounds = [start] + [w.start for w in line.words] + [end]
        segments = [(k, bounds[k], bounds[k + 1]) for k in range(len(bounds) - 1)
                    if round(bounds[k + 1] * 100) > round(bounds[k] * 100)]
        for n, (k, a, b) in enumerate(segments):
            active = k - 1  # -1 = lead-in, nothing sung yet
            words = []
            for j, w in enumerate(line.words):
                t = _text(s, w.text)
                if j == active:
                    words.append(f"{{\\1c{_colour(s.highlight)}\\fscy{s.pop_scale}\\t(0,140,\\fscy100)}}{t}"
                                 f"{{\\1c{_colour(s.sung)}\\fscy100}}")
                elif j > active:
                    words.append(f"{{\\1a&H{s.unsung_alpha:02X}&}}{t}{{\\1a&H00&}}")
                else:
                    words.append(t)
            first_seg, last_seg = n == 0, n == len(segments) - 1
            fade = f"\\fad({FADE_MS * 2 if first_seg else 0},{FADE_MS if last_seg else 0})"
            events.append(f"Dialogue: 0,{_ts(a)},{_ts(b)},Active,,0,0,0,,"
                          f"{{{enter if first_seg else still}{look}{fade}}}{' '.join(words)}{tail}")
    return events
