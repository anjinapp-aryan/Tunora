#!/usr/bin/env bash
# Assemble the Phase 31 montages with the UNCHANGED Phase 29 montage script (approved LGPL FFmpeg, 30 fps, H.264, AAC).
cd "$(dirname "$0")"
PY=../.venv/Scripts/python.exe
$PY ../scripts/e8_montage.py jobs/plan_montage_9x16.json outputs/montage/clips p31 outputs/montage/montage_9x16.mp4 portrait
$PY ../scripts/e8_montage.py jobs/plan_montage_16x9_chorus.json outputs/montage_16x9/clips p31 outputs/montage_16x9/montage_16x9.mp4 landscape
