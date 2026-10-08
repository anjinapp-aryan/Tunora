"""VideoOutputProfile (Phase 27): the one canonical list of music video output formats.

A client only ever sends a profile id; width, height, aspect ratio and encoder settings come from
here and nowhere else (the API, the service, the renderer and the response all read this table).

Each profile has two sizes:
  * `width` x `height` -- the real output frame (what FFmpeg encodes, what ffprobe reports);
  * `canvas_width` x `canvas_height` -- the layout canvas the ASS lyric script is written for
    (its PlayRes). libass scales a script from its PlayRes to the frame it draws on, so a 4K profile
    reuses its HD layout unchanged and the glyphs are still rasterised at full 4K resolution.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.music_videos.errors import InvalidMusicVideoRequestError


@dataclass(frozen=True)
class VideoOutputProfile:
    id: str
    orientation: str        # "portrait" | "landscape" | "square"
    aspect_ratio: str       # "9:16" | "16:9" | "1:1"
    width: int
    height: int
    resolution_class: str   # "HD" | "4K"
    display_name: str
    canvas_width: int
    canvas_height: int
    video_bitrate: str      # OpenH264 target; max rate and buffer are derived from it
    max_bitrate: str
    buffer_size: str

    @property
    def pixel_factor(self) -> float:
        """Frame area relative to 1080x1920 (render time and timeout scale with it)."""
        return (self.width * self.height) / (1080 * 1920)


PROFILES: dict[str, VideoOutputProfile] = {
    # The Phase 23-26 output: unchanged dimensions and encoder settings.
    "vertical_hd": VideoOutputProfile("vertical_hd", "portrait", "9:16", 1080, 1920, "HD",
                                      "9:16 Vertical HD", 1080, 1920, "8M", "10M", "16M"),
    "vertical_4k": VideoOutputProfile("vertical_4k", "portrait", "9:16", 2160, 3840, "4K",
                                      "9:16 Vertical 4K", 1080, 1920, "32M", "40M", "64M"),
    "landscape_hd": VideoOutputProfile("landscape_hd", "landscape", "16:9", 1920, 1080, "HD",
                                       "16:9 Landscape HD", 1920, 1080, "8M", "10M", "16M"),
    "landscape_4k": VideoOutputProfile("landscape_4k", "landscape", "16:9", 3840, 2160, "4K",
                                       "16:9 Landscape 4K", 1920, 1080, "32M", "40M", "64M"),
    # No square 4K: no mainstream platform delivers 1:1 above 1080x1080.
    "square_hd": VideoOutputProfile("square_hd", "square", "1:1", 1080, 1080, "HD",
                                    "1:1 Square HD", 1080, 1080, "8M", "10M", "16M"),
}
PROFILE_IDS = tuple(PROFILES)
DEFAULT_PROFILE_ID = "vertical_hd"
ASPECT_RATIOS = tuple(dict.fromkeys(p.aspect_ratio for p in PROFILES.values()))


def get_profile(profile_id: str) -> VideoOutputProfile:
    """The profile for an allowlisted id. Raises InvalidMusicVideoRequestError otherwise."""

    profile = PROFILES.get(profile_id) if isinstance(profile_id, str) else None
    if profile is None:
        raise InvalidMusicVideoRequestError("Unknown output profile.")
    return profile


def renderer_profile(value: str) -> VideoOutputProfile | None:
    """A profile id, or the legacy Phase 23 aspect ratio "9:16" (= vertical_hd), or None."""

    if value == "9:16":
        return PROFILES[DEFAULT_PROFILE_ID]
    return PROFILES.get(value)
