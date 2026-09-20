"""Song and Version identifiers.

Same philosophy as job ids (`tunora-<uuid4>`): random, opaque, stable and
never derived from a title, prompt, path or provider value.
"""

from __future__ import annotations

import re
import uuid

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,79}$")


def new_song_id() -> str:
    return f"song-{uuid.uuid4()}"


def new_version_id() -> str:
    return f"ver-{uuid.uuid4()}"


def is_valid_id(value: object) -> bool:
    """True for ids made of letters, digits and hyphens only (no separators, dots or spaces)."""

    return isinstance(value, str) and _ID_PATTERN.fullmatch(value) is not None
