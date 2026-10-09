#!/usr/bin/env bash
# Phase 31 stage 2a: waits for stage 1 to finish (never two controllers at once), then runs composition.json.
cd "$(dirname "$0")"
until grep -q "end matrix" logs/stage1.log; do sleep 30; done
echo "=== $(date '+%F %T') start composition"
../.venv/Scripts/python.exe controller.py jobs/composition.json --min-free-gb 2.0 2>&1 | tee -a logs/composition.controller.log
echo "=== $(date '+%F %T') end composition rc=${PIPESTATUS[0]}"
