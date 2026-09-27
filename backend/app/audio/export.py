"""On-demand FLAC -> MP3/WAV export (Phase 21).

Reuses `soundfile` (BSD-3-Clause, already installed for ACE-Step's own environment; verified in the
Phase 20 audit to convert FLAC to MP3/WAV without FFmpeg — see docs/PHASE-21-IMPLEMENTATION.md).
This module never touches canonical storage: it reads one already-resolved, trusted source file and
writes one temporary file, whose lifecycle the caller owns (see `export_audio`'s docstring).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import soundfile as sf

SUPPORTED_EXPORT_FORMATS = frozenset({"mp3", "wav"})

# libsndfile's own default MP3 encoder settings (no `compression_level`/`bitrate_mode` override):
# measured in the Phase 20 audit at ~155 kbps VBR for a 48 kHz stereo source — a reasonable default
# listening quality. Deliberately not tuned further for Phase 21 (MVP: one sensible default, not a
# bitrate/quality picker).
_MEDIA_TYPE = {"mp3": "audio/mpeg", "wav": "audio/wav"}
_SOUNDFILE_FORMAT = {"mp3": "MP3", "wav": "WAV"}
_SOUNDFILE_SUBTYPE = {"mp3": "MPEG_LAYER_III", "wav": "PCM_16"}


class ExportError(Exception):
    """The source could not be converted (unreadable/corrupt source, or the encoder rejected it)."""


@dataclass(frozen=True)
class ExportedAudio:
    path: Path
    media_type: str


def media_type_for(export_format: str) -> str:
    return _MEDIA_TYPE[export_format]


def export_audio(source_path: Path, export_format: str, *, title: Optional[str] = None) -> ExportedAudio:
    """Convert `source_path` (the canonical stored file) to `export_format` and return the temporary
    file that holds the result. The caller is responsible for deleting `ExportedAudio.path` once it
    has been sent (e.g. via a Starlette `BackgroundTask`); this function never leaves a partially
    written file behind on its own failure.

    `export_format` must be one of `SUPPORTED_EXPORT_FORMATS`. `title` is embedded as a string tag
    when the encoder supports it (best-effort: some containers/subtypes do not; that is not an error).
    Raises `ExportError` if the source cannot be read or the encoder rejects the data.
    """

    if export_format not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError(f"Unsupported export format {export_format!r}")

    fd, tmp_name = tempfile.mkstemp(suffix=f".{export_format}", prefix="tunora-export-")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        data, sample_rate = sf.read(source_path, dtype="float32", always_2d=True)
    except Exception as exc:  # noqa: BLE001 -- any libsndfile/decoding failure is an ExportError to the caller
        tmp_path.unlink(missing_ok=True)
        raise ExportError(f"Could not read the source audio: {exc}") from exc

    try:
        with sf.SoundFile(
            tmp_path,
            mode="w",
            samplerate=sample_rate,
            channels=data.shape[1],
            format=_SOUNDFILE_FORMAT[export_format],
            subtype=_SOUNDFILE_SUBTYPE[export_format],
        ) as out:
            if title:
                try:
                    out.title = title
                except Exception:  # noqa: BLE001 -- best-effort metadata; never fails the export
                    pass
            out.write(data)
    except Exception as exc:  # noqa: BLE001 -- any libsndfile/encoding failure is an ExportError to the caller
        tmp_path.unlink(missing_ok=True)
        raise ExportError(f"Could not encode the export: {exc}") from exc

    return ExportedAudio(path=tmp_path, media_type=_MEDIA_TYPE[export_format])
