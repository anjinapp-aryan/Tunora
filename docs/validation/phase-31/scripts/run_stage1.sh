#!/usr/bin/env bash
# Phase 31 stage 1: baseline -> keyframes -> 28-clip matrix, one controller run each (lab only).
cd "$(dirname "$0")"
PY=../.venv/Scripts/python.exe
for w in baseline keyframes matrix; do
  echo "=== $(date '+%F %T') start $w"
  $PY controller.py jobs/$w.json --min-free-gb 2.0 2>&1 | tee -a logs/$w.controller.log
  echo "=== $(date '+%F %T') end $w rc=${PIPESTATUS[0]}"
done
