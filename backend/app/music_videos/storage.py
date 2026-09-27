"""Music Video file storage (Phase 23): a separate namespace from audio.

Layout under its own root (default `./data/music-videos`, never the audio root):
    <root>/<music-video-id>/background.<ext>     the uploaded background
    <root>/<music-video-id>/<music-video-id>.mp4 the rendered video

Keys are resolved with exactly the same traversal/containment rules as audio storage (it composes
`LocalAudioStorage`, which already rejects absolute paths, drive letters and `..`, and checks the
resolved path is inside the root). Nothing a client sends is ever used as a path; ids are
Tunora-generated and extensions come from an allowlist.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import AsyncIterator, Union

from app.music_videos.errors import InvalidMusicVideoRequestError
from app.songs.ids import is_valid_id
from app.storage.local import LocalAudioStorage


class MusicVideoStorage:
    def __init__(self, root: Union[str, Path]) -> None:
        self._keys = LocalAudioStorage(root)  # reused for key validation + containment only
        self.root = Path(root).resolve()

    @staticmethod
    def background_key(music_video_id: str, extension: str) -> str:
        return f"{music_video_id}/background{extension}"

    @staticmethod
    def output_key(music_video_id: str) -> str:
        return f"{music_video_id}/{music_video_id}.mp4"

    def get_path(self, key: str) -> Path:
        return self._keys.get_path(key)

    async def save_stream(self, key: str, chunks: AsyncIterator[bytes], max_bytes: int) -> int:
        """Write an upload to `key` atomically (temp file in the same directory, then rename).
        Stops reading and removes the partial file as soon as `max_bytes` is exceeded."""

        final = self.get_path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = final.parent / f".{final.name}.tmp-{uuid.uuid4().hex}"
        size = 0
        try:
            with open(tmp, "wb") as handle:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise InvalidMusicVideoRequestError(
                            f"The background file is larger than {max_bytes // (1024 * 1024)} MB.")
                    handle.write(chunk)
            if size == 0:
                raise InvalidMusicVideoRequestError("The background file is empty.")
            os.replace(tmp, final)
            return size
        finally:
            tmp.unlink(missing_ok=True)

    def delete_video(self, music_video_id: str) -> None:
        """Remove one Music Video's directory (background + output). Idempotent."""

        if not is_valid_id(music_video_id):
            return
        directory = self.get_path(f"{music_video_id}/x").parent
        if directory != self.root and directory.parent == self.root:
            shutil.rmtree(directory, ignore_errors=True)
