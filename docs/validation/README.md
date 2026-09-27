# Validation tools and procedures (Phase 19)

Developer-only. Nothing here is part of the running product: no endpoint, no dependency, no database change.

| File | What it does | Runs with |
|---|---|---|
| `gpu_envelope.py` | Runs real Tunora operations against a throwaway backend (own DB/storage, port 8010) and samples `nvidia-smi` every 0.5 s | `backend\.venv` python (standard library only) |
| `audio_validation.py chain` | Builds an MP3 lineage and a FLAC lineage (3 chained Repaints each) from one lossless master, measures them, and writes a **blind listening kit** | ACE-Step's venv (numpy, scipy, soundfile, httpx) + local `ffmpeg` |
| `audio_validation.py stems` | Measures the real Extract stems of one Song and writes a **blind stem kit** | same |
| `../../backend/scripts/storage_report.py` | Read-only storage usage report and projection | `backend\.venv` python (standard library only) |
| `results/` | The raw measurement outputs quoted in `docs/PHASE-19-IMPLEMENTATION.md` | |

`ffmpeg` here is a developer-local tool used only to make the MP3 copy of the lossless master and to decode files for measurement; Tunora never calls it. Everything the scripts print is an **instrument measurement, not listening evidence**.

## Commands

```powershell
# GPU envelope (ACE-Step running via start-tunora.ps1)
backend\.venv\Scripts\python.exe docs\validation\gpu_envelope.py --work-dir <scratch> --out <scratch>\gpu.json

# MP3 chain vs FLAC chain, plus the blind kit (write the kit OUTSIDE the repository)
ACE-Step-1.5\.venv\Scripts\python.exe docs\validation\audio_validation.py chain --work-dir <scratch> --kit-dir <folder outside the repo>

# Extract stems of one Song (a Tunora database + its audio folder) and the blind stem kit
ACE-Step-1.5\.venv\Scripts\python.exe docs\validation\audio_validation.py stems --db <t.db> --audio-root <audio dir> --source-job <job id of the mix Version> --work-dir <scratch> --kit-dir <folder outside the repo>

# Storage report
cd backend; .venv\Scripts\python.exe scripts\storage_report.py --storage-root .\data\audio --db tunora.db
```

Sampling note: GPU numbers are the maximum of samples taken every 0.5 s. They are **observed peaks, not guaranteed absolute hardware peaks**; a shorter spike can be missed.

## Manual procedure: Safari (real Safari on macOS or iPhone/iPad)

Nobody has run this yet; the Safari status is **NOT VALIDATED** until someone does. Do not use Playwright WebKit on Windows as a substitute (it fails to play even MP3 here).

1. On the Windows machine build and serve the production frontend so it can be reached from the LAN (the dev server only allows `127.0.0.1` as a dev origin): start the stack with `start-tunora.ps1`, then in `frontend` run `npm run build` and `$env:TUNORA_API_URL='http://127.0.0.1:8000'; npx next start -H 0.0.0.0 -p 3100`. Allow Windows Firewall for port 3100 when prompted.
2. On the Mac/iPhone (same network) open Safari at `http://<Windows LAN IPv4>:3100/library`.
3. Open a Song that has a FLAC Version (create one first if the library only has MP3 Versions), then a short FLAC Version and, if practical, a 2-3 minute one.
4. For each: press Play (audio starts), Seek (drag the slider and click the waveform), Pause, Resume, check the waveform is drawn, press Download and check the file opens/plays (QuickTime/Music), then refresh the page and repeat Play.
5. Also play an old MP3 Version.
6. Record: device, macOS/iOS version, Safari version, and PASS/FAIL per step. Add it to `docs/PHASE-19-IMPLEMENTATION.md` (Safari section). If FLAC fails while MP3 passes, that is a real compatibility bug in the Phase 17 default; the rollback is `TUNORA_AUDIO_FORMAT=mp3`.

## Blind listening: MP3 vs FLAC (needs a human)

The kit folder (`response_sheet.md`, `trial_NN_A.wav`/`_B.wav`, `answer_key.json`) contains 6 trials: A/B pairs with randomized order and neutral labels. Two trials compare the generation-3 MP3 lineage with the generation-3 FLAC lineage, two compare the plain 128 kbps MP3 with the lossless master, and two play the identical file twice to measure false positives. Levels were matched to within 0.2 dB by a gain change only (no normalization or compression); the applied gains are in the script output and `answer_key.json`.

Listen with the same headphones/speakers and volume for every trial, fill the sheet using NOT NOTICEABLE / SLIGHT / MODERATE / CLEAR, and open `answer_key.json` only afterwards. Conclusion options: 1 no audible difference detected, 2 difference occasionally detected, 3 difference consistently detected, 4 inconclusive. Do not conclude "FLAC sounds better" unless the answers show it.

## Blind listening: Extract stems (needs a human)

The stem kit has five shuffled files (`stem_S1..S5.wav`: the full mix and four stems) and `stem_response_sheet.md`; identify what you hear in each first, then rate each with CLEAN / USABLE / PARTIALLY USABLE / POOR / UNUSABLE, and only then open `stem_answer_key.json`. The ratings are descriptive observations, not a product ranking, and not a comparison with commercial separators.
