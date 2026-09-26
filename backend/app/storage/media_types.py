"""Media-type inference for stored audio, reusing the stdlib `mimetypes`
table rather than hand-maintaining one — extended only for the couple of
audio formats ACE-Step supports that `mimetypes` doesn't reliably know.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Union

_FALLBACK_TYPES = {
    ".opus": "audio/opus",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".wav32": "audio/wav",
}


# Python's mimetypes table differs by platform (`.flac` is `audio/x-flac` on some); the registered
# type is `audio/flac`. Only this known variant is rewritten (Phase 17); everything else is untouched.
_NORMALIZED_TYPES = {"audio/x-flac": "audio/flac"}


def guess_media_type(path: Union[str, Path]) -> str:
    """Best-effort media type for an audio file, defaulting to a generic type."""

    suffix = Path(path).suffix.lower()
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return _NORMALIZED_TYPES.get(guessed, guessed)
    return _FALLBACK_TYPES.get(suffix, "application/octet-stream")
