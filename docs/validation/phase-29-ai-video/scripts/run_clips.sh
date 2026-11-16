#!/usr/bin/env bash
# Lab resume driver: one process per clip (isolation), per-clip timeout, one retry, skip finished clips.
# Usage: run_clips.sh <clips.json> <out_dir> <log>
set -u
LAB=/i/Tunora-validation/ai-video-feasibility
JOBS=$(realpath "$1"); OUT=$2; LOG=$(realpath -m "$3")
FW=$(ls -d $LAB/hf-home/hub/models--FastVideo--FastWan2.2-TI2V-5B-FullAttn-Diffusers/snapshots/*/transformer | sed 's#^/i#I:#')
BASE="I:/Tunora-validation/ai-video-feasibility/hf-home/hub/models--Wan-AI--Wan2.2-TI2V-5B-Diffusers/snapshots/b8fff7315c768468a5333511427288870b2e9635"
cd $LAB/scripts
N=$(PYTHONUTF8=1 ../.venv/Scripts/python.exe -c "import json,sys;print(len(json.load(open(sys.argv[1],encoding='utf-8'))))" "$JOBS")
for ((i=0; i<N; i++)); do
  NAME=$(PYTHONUTF8=1 ../.venv/Scripts/python.exe -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))[int(sys.argv[2])]['name'])" "$JOBS" $i)
  if [ -s "$OUT/$NAME.mp4" ]; then echo "SKIP $NAME (exists)" | tee -a $LOG; continue; fi
  PYTHONUTF8=1 ../.venv/Scripts/python.exe -c "import json,sys;j=json.load(open(sys.argv[1],encoding='utf-8'));json.dump([j[int(sys.argv[2])]],open(sys.argv[3],'w',encoding='utf-8'),ensure_ascii=False)" "$JOBS" $i "$LAB/jobs/_single.json"
  for attempt in 1 2; do
    t0=$(date +%s)
    HF_HOME="I:/Tunora-validation/ai-video-feasibility/hf-home" HF_HUB_OFFLINE=1 PYTHONUTF8=1 timeout 900 \
      ../.venv/Scripts/python.exe -X faulthandler e2_wan.py "$(cygpath -w $LAB/jobs/_single.json)" "$OUT" --offload model --precompute-embeds \
      --vae-tiling --model "$BASE" --transformer "$FW" --dmd-sigmas 1.0,0.757,0.522 >> $LOG 2>&1
    rc=$?; dt=$(( $(date +%s) - t0 ))
    echo "CLIP $NAME attempt=$attempt rc=$rc wall=${dt}s" | tee -a $LOG
    [ $rc -eq 0 ] && [ -s "$OUT/$NAME.mp4" ] && break
    # timeout only kills the venv launcher; also stop its interpreter child (only processes running e2_wan.py)
    powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*e2_wan.py*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" >/dev/null 2>&1 || true
  done
done
echo "DRIVER_DONE" | tee -a $LOG
