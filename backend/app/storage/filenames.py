"""User-facing filenames for stored audio.

The stored filename is Tunora-controlled in normal operation
(`<job-id>.<ext>`), but it is read back from a database record, so it is
sanitized once here, at the boundary, before it reaches an HTTP header or the
public API. Nothing a client sends is ever used to build it.
"""

from __future__ import annotations

import os
import re

ALLOWED_EXTENSIONS = frozenset({".mp3", ".wav", ".flac", ".ogg", ".opus", ".aac"})

_EXTENSION_BY_MEDIA_TYPE = {
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/aac": ".aac",
}
_DEFAULT_EXTENSION = ".mp3"
_MAX_STEM_LENGTH = 100


def _clean(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = re.sub(r"\.{2,}", ".", text)
    return text.strip("._-")[:_MAX_STEM_LENGTH]


def safe_audio_filename(raw: object, *, job_id: str, media_type: str) -> str:
    """Return a filename safe for a Content-Disposition header and the public API.

    Guarantees: no path separators, no traversal sequences, no control
    characters (CR/LF included), only `[A-Za-z0-9._-]`, an allowed audio
    extension, and a deterministic fallback (`tunora-<job-id>.<ext>`) when the
    stored name is empty or unusable.
    """

    base = re.split(r"[\\/]", raw if isinstance(raw, str) else "")[-1]
    stem, ext = os.path.splitext(base)
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = _EXTENSION_BY_MEDIA_TYPE.get(media_type, _DEFAULT_EXTENSION)
        stem = base  # the "extension" was part of the name; keep it as text
    stem = _clean(stem)
    if not stem:
        stem = f"tunora-{_clean(job_id) or 'audio'}"
    return f"{stem}{ext}"
