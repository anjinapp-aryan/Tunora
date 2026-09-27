"""Creative operations that create a NEW Version from an existing one.

Verified capability (docs/PHASE-5B-EXTEND-REMIX-REPAINT.md): with ACE-Step's turbo model
EXTEND, REMIX and REPAINT all condition on the source audio. A provider advertises what it
honestly supports through `MusicGenerationProvider.supported_operations`.
"""

from __future__ import annotations

ORIGINAL = "ORIGINAL"
EXTEND = "EXTEND"
REMIX = "REMIX"
REPAINT = "REPAINT"
EXTRACT = "EXTRACT"
# Phase 13: a fresh text-to-music generation of the same creative idea (no source audio).
ANOTHER_TAKE = "ANOTHER_TAKE"

CREATIVE_OPERATIONS = (EXTEND, REMIX, REPAINT, EXTRACT, ANOTHER_TAKE)
ALL_OPERATIONS = (ORIGINAL, *CREATIVE_OPERATIONS)

# Limits come from the provider's documented repaint range (3-90 s) and are enforced server-side.
EXTEND_MIN_SECONDS = 5.0
EXTEND_MAX_SECONDS = 90.0
REPAINT_MIN_SECONDS = 3.0
REPAINT_MAX_SECONDS = 90.0
DEFAULT_REMIX_STRENGTH = 0.7

# Track types verified against a real running base-tier generation provider server (Phase 11
# spike, docs/PHASE-11-IMPLEMENTATION.md): each of these was actually extracted from a real
# Tunora generation and produced a valid, distinct audio file. The provider documents 8 more
# track types (woodwinds, brass, fx, synth, strings, percussion, keyboard, backing_vocals) that
# were not individually spike-verified this session -- deliberately not exposed here (never
# invent/expose an unverified capability); add them only after the same real-extraction
# verification.
TRACK_NAMES = ("vocals", "drums", "bass", "guitar")
