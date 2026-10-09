#!/usr/bin/env bash
# peek.sh <id> [id...]: build missing strips, stack the given clips into contact-sheets/_tmp.jpg, print metrics.
cd "$(dirname "$0")"
PY=../.venv/Scripts/python.exe; FF=/i/Tunora/backend/tools/ffmpeg/bin/ffmpeg.exe
$PY review.py strips >/dev/null
ins=(); n=0; clips=()
for id in "$@"; do ins+=(-i "file:contact-sheets/strips/$id.jpg"); n=$((n+1)); clips+=($(ls outputs/*/$id.mp4)); done
if [ $n -gt 1 ]; then $FF -v error -y "${ins[@]}" -filter_complex "vstack=inputs=$n" -q:v 3 contact-sheets/_tmp.jpg
else cp "contact-sheets/strips/$1.jpg" contact-sheets/_tmp.jpg; fi
$PY motion_metrics.py "${clips[@]}" | $PY _fmt.py
