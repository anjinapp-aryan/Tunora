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


def guess_media_type(path: Union[str, Path]) -> str:
    """Best-effort media type for an audio file, defaulting to a generic type."""

    suffix = Path(path).suffix.lower()
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    return _FALLBACK_TYPES.get(suffix, "application/octet-stream")
