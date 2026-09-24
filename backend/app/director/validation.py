"""Validation for the AI Song Director's output.

The planner's output is treated as UNTRUSTED input (docs/PHASE-7-AI-SONG-DIRECTOR.md
§"Security"), exactly like any other external response: checked here before it is
allowed to become a `SongSpec`, never passed straight through. Generation must
never start from an unvalidated plan.
"""

from __future__ import annotations

import math
from typing import Optional

from app.director.errors import InvalidDirectorRequestError, InvalidSongPlanError

PROMPT_MAX = 2000  # the LM's "caption" can run longer than a hand-typed prompt
LYRICS_MAX = 5000  # matches the existing Create Song limit (lib/create-song-schema.ts)
TITLE_MAX = 80
LANGUAGE_MAX = 10
KEY_SCALE_MAX = 40
TIME_SIGNATURE_MAX = 10
DURATION_MIN = 5.0
DURATION_MAX = 600.0
BPM_MIN = 20
BPM_MAX = 300


def _finite_number(value: object) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def validate_prompt(prompt: object) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise InvalidSongPlanError("The AI director did not return a usable song description.")
    prompt = prompt.strip()
    if len(prompt) > PROMPT_MAX:
        raise InvalidSongPlanError(f"The AI director's description was too long (over {PROMPT_MAX} characters).")
    return prompt


def validate_lyrics(lyrics: object, *, instrumental: bool) -> str:
    if instrumental:
        return ""
    if not isinstance(lyrics, str):
        raise InvalidSongPlanError("The AI director returned invalid lyrics.")
    if len(lyrics) > LYRICS_MAX:
        raise InvalidSongPlanError(f"The AI director's lyrics were too long (over {LYRICS_MAX} characters).")
    return lyrics


def validate_title(title: object) -> str:
    if title is None:
        return ""
    if not isinstance(title, str):
        raise InvalidSongPlanError("The AI director returned an invalid title.")
    title = title.strip()
    if len(title) > TITLE_MAX:
        title = title[:TITLE_MAX]
    return title


def validate_language(language: object) -> str:
    """"" / "unknown" both mean "no vocal language" (instrumental or unspecified)."""

    if language is None:
        return ""
    if not isinstance(language, str):
        raise InvalidSongPlanError("The AI director returned an invalid language.")
    language = language.strip().lower()
    if language in ("", "unknown"):
        return ""
    if len(language) > LANGUAGE_MAX or not all(c.isalnum() or c == "-" for c in language):
        raise InvalidSongPlanError("The AI director returned an unsupported language code.")
    return language


def validate_duration(duration: object) -> Optional[float]:
    if duration is None:
        return None
    value = _finite_number(duration)
    if value is None or value <= 0:
        raise InvalidSongPlanError("The AI director returned an invalid duration.")
    if not DURATION_MIN <= value <= DURATION_MAX:
        raise InvalidSongPlanError(
            f"The AI director suggested a duration outside the supported range ({DURATION_MIN:g}-{DURATION_MAX:g}s)."
        )
    return value


def validate_bpm(bpm: object) -> Optional[int]:
    """Informational only (never sent to generation) -- validated leniently: an
    out-of-range or unparsable value is dropped, not treated as a fatal error."""

    value = _finite_number(bpm)
    if value is None or not BPM_MIN <= value <= BPM_MAX:
        return None
    return int(value)


def validate_short_text(value: object, max_length: int) -> Optional[str]:
    """Informational only (key_scale / time_signature): dropped, not fatal, when malformed."""

    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    return value[:max_length] if len(value) > max_length else value


INSTRUCTION_MAX = 500


def validate_instruction(instruction: object) -> str:
    """The user's own refinement request -- checked as ordinary user input (not AI
    output): non-empty, bounded length. Free text; no shell/URL/path semantics are
    ever attached to it (see docs/PHASE-8, "Security")."""

    if not isinstance(instruction, str) or not instruction.strip():
        raise InvalidDirectorRequestError("Describe the change you want first.")
    instruction = instruction.strip()
    if len(instruction) > INSTRUCTION_MAX:
        raise InvalidDirectorRequestError(f"Keep the refinement instruction under {INSTRUCTION_MAX} characters.")
    return instruction
