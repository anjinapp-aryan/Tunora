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

CREATIVE_OPERATIONS = (EXTEND, REMIX, REPAINT)
ALL_OPERATIONS = (ORIGINAL, *CREATIVE_OPERATIONS)

# Limits come from the provider's documented repaint range (3-90 s) and are enforced server-side.
EXTEND_MIN_SECONDS = 5.0
EXTEND_MAX_SECONDS = 90.0
REPAINT_MIN_SECONDS = 3.0
REPAINT_MAX_SECONDS = 90.0
DEFAULT_REMIX_STRENGTH = 0.7
