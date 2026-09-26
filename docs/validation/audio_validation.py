"""Phase 19 developer-only audio validation helpers (no product code, no new dependency).

Runs with ACE-Step's existing virtualenv, which already has numpy, scipy, soundfile and httpx:
    ACE-Step-1.5\\.venv\\Scripts\\python.exe docs\\validation\\audio_validation.py chain --work-dir <scratch> --kit-dir <outside repo>
    ACE-Step-1.5\\.venv\\Scripts\\python.exe docs\\validation\\audio_validation.py stems --db <t.db> --audio-root <audio dir> --kit-dir <outside repo>

`ffmpeg` (a developer-local tool, never called by Tunora) is used only to make an MP3 of the lossless master and to
decode files to a common format for measurement.

IMPORTANT: everything printed here is an INSTRUMENT MEASUREMENT. None of it is listening evidence; the kits it writes
exist so that a human can do the blind listening (see docs/validation/README.md).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sqlite3
import subprocess
import time

import httpx
import numpy as np
import soundfile as sf
from scipy import signal

ACE = "http://127.0.0.1:8001"
PROMPT = "upbeat pop song with clear female vocals, drums, bass and synth"
LYRICS = "la la la sing along tonight, we are alive, dancing in the light"


# -- helpers ------------------------------------------------------------------------------------------------


def ffmpeg_to_wav(src: str, dst: str, seconds: float | None = None, start: float = 0.0) -> None:
    """Decode any file to 48 kHz stereo 16-bit-safe float WAV (drops the MP3 encoder delay via the gapless header)."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src]
    if start:
        cmd += ["-ss", str(start)]
    if seconds:
        cmd += ["-t", str(seconds)]
    subprocess.run(cmd + ["-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le", dst], check=True)


def load(path: str) -> np.ndarray:
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    assert rate == 48000, rate
    return data


def mono(x: np.ndarray) -> np.ndarray:
    return x.mean(axis=1)


def dbfs(v: float) -> float:
    return round(20 * np.log10(max(v, 1e-9)), 2)


def band_fractions(x: np.ndarray) -> dict:
    f, p = signal.welch(mono(x), fs=48000, nperseg=4096)
    total = p.sum() or 1e-20
    edges = [(0, 250, "lt_250hz"), (250, 2000, "250hz_2khz"), (2000, 6000, "2_6khz"), (6000, 16000, "6_16khz"), (16000, 24000, "gt_16khz")]
    return {name: round(float(p[(f >= lo) & (f < hi)].sum() / total), 4) for lo, hi, name in edges}


def snr_db(truth: np.ndarray, x: np.ndarray) -> float:
    n = min(len(truth), len(x))
    e = float(((truth[:n] - x[:n]) ** 2).sum()) or 1e-20
    return round(10 * np.log10(float((truth[:n] ** 2).sum()) / e), 1)


def gain_matched(truth: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    """(best scalar gain in dB, SNR after applying it): separates a plain level change from real waveform error."""
    n = min(len(truth), len(x))
    t, y = truth[:n].astype(np.float64), x[:n].astype(np.float64)
    g = float((t * y).sum() / ((y ** 2).sum() or 1e-20))
    return round(20 * np.log10(max(g, 1e-9)), 2), snr_db(t, y * g)


def rms_db(x: np.ndarray) -> float:
    return dbfs(float(np.sqrt((x ** 2).mean())))


def peak_db(x: np.ndarray) -> float:
    return dbfs(float(np.abs(x).max()))


# -- ACE-Step REST (the same calls Tunora's provider makes) ---------------------------------------------------


def run(form: dict, files: dict | None = None) -> tuple[bytes, dict]:
    r = httpx.post(ACE + "/release_task", data=form if files else None, json=None if files else form, files=files, timeout=300).json()
    tid = r["data"]["task_id"]
    while True:
        q = httpx.post(ACE + "/query_result", json={"task_id_list": [tid]}, timeout=120).json()["data"][0]
        if q["status"] != 0:
            break
        time.sleep(0.5)
    item = json.loads(q["result"])[0]
    assert item.get("file"), f"no output: {(q.get('progress_text') or '')[-160:]}"
    return httpx.get(ACE + item["file"], timeout=300).content, item


def repaint(src_bytes: bytes, name: str, mime: str, fmt: str, start: int, end: int) -> bytes:
    form = {"prompt": PROMPT, "lyrics": LYRICS, "vocal_language": "en", "use_random_seed": "true", "task_type": "repaint",
            "repainting_start": str(start), "repainting_end": str(end), "chunk_mask_mode": "explicit", "audio_format": fmt, "batch_size": "1"}
    return run(form, {"src_audio": (name, src_bytes, mime)})[0]


# -- command: MP3 chain vs FLAC chain ---------------------------------------------------------------------------


def cmd_chain(a) -> None:
    work, kit = a.work_dir, a.kit_dir
    if a.reuse and os.path.exists(f"{work}/master.flac"):
        master_bytes = open(f"{work}/master.flac", "rb").read()
        chains = {"mp3": [open(f"{work}/mp3_{g}.mp3", "rb").read() for g in range(4)], "flac": [open(f"{work}/flac_{g}.flac", "rb").read() for g in range(4)]}
    else:
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        master_bytes, _ = run({"prompt": PROMPT, "lyrics": LYRICS, "vocal_language": "en", "audio_duration": 20, "use_random_seed": True, "audio_format": "flac"})
        open(f"{work}/master.flac", "wb").write(master_bytes)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{work}/master.flac", "-c:a", "libmp3lame", "-b:a", "128k", f"{work}/mp3_0.mp3"], check=True)
        chains = {"mp3": [open(f"{work}/mp3_0.mp3", "rb").read()], "flac": [master_bytes]}
        for g in (1, 2, 3):
            chains["mp3"].append(repaint(chains["mp3"][-1], "source.mp3", "audio/mpeg", "mp3", 12, 18))
            chains["flac"].append(repaint(chains["flac"][-1], "source.flac", "audio/flac", "flac", 12, 18))
            print("generation", g, "done", flush=True)
    os.makedirs(kit, exist_ok=True)
    wav = {}
    ffmpeg_to_wav(f"{work}/master.flac", f"{work}/master.wav")
    truth = load(f"{work}/master.wav")
    wav["truth"] = truth
    for kind, ext in (("mp3", "mp3"), ("flac", "flac")):
        for g, b in enumerate(chains[kind]):
            open(f"{work}/{kind}_{g}.{ext}", "wb").write(b)
            ffmpeg_to_wav(f"{work}/{kind}_{g}.{ext}", f"{work}/{kind}_{g}.wav")
            wav[(kind, g)] = load(f"{work}/{kind}_{g}.wav")
    sr = 48000
    seg = slice(0, 10 * sr)  # the first 10 s are outside the repainted 12-18 s window
    report = {"region": "0-10 s of a 20 s song (untouched by every Repaint of 12-18 s)", "rows": []}
    t = truth[seg]
    report["rows"].append({"file": "lossless master", "snr_vs_master_db": None, "rms_db": rms_db(t), "peak_db": peak_db(t), "bands": band_fractions(t)})
    for kind in ("mp3", "flac"):
        for g in range(4):
            x = wav[(kind, g)][seg]
            report["rows"].append({"file": f"{kind} chain, generation {g}" + (" (the source)" if g == 0 else ""), "bytes": len(chains[kind][g]),
                                   "snr_vs_master_db": snr_db(t, x), "level_change_db": gain_matched(t, x)[0], "snr_after_level_match_db": gain_matched(t, x)[1], "rms_db": rms_db(x), "peak_db": peak_db(x), "bands": band_fractions(x)})
    # Blind kit: 5 s windows; trials compare the generation-3 MP3 lineage with the generation-3 FLAC lineage (and the
    # plain 128k MP3 with the lossless master), plus catch trials (the same file twice) to measure false positives.
    rng = random.Random(a.seed)
    windows = [(0, 5), (5, 10)]
    mp3g3, flacg3, mp3g0, mast = wav[("mp3", 3)], wav[("flac", 3)], wav[("mp3", 0)], truth

    def clip(x, lo, hi):
        return x[lo * sr:hi * sr]

    trials = []
    for lo, hi in windows:
        trials.append(("mp3 chain g3", clip(mp3g3, lo, hi), "flac chain g3", clip(flacg3, lo, hi), f"chain generation 3, window {lo}-{hi} s"))
        trials.append(("mp3 source g0", clip(mp3g0, lo, hi), "lossless master", clip(mast, lo, hi), f"128k MP3 vs lossless master, window {lo}-{hi} s"))
    trials.append(("catch", clip(mast, 0, 5), "catch", clip(mast, 0, 5), "identical pair (false-positive check)"))
    trials.append(("catch", clip(flacg3, 5, 10), "catch", clip(flacg3, 5, 10), "identical pair (false-positive check)"))
    rng.shuffle(trials)
    key, level_notes = [], []
    for i, (na, xa, nb, xb, desc) in enumerate(trials, start=1):
        swap = rng.random() < 0.5
        (na, xa), (nb, xb) = ((nb, xb), (na, xa)) if swap else ((na, xa), (nb, xb))
        gain_db = rms_db(xa) - rms_db(xb)  # level match only when the difference exceeds 0.2 dB (documented in the sheet)
        if na != "catch" and abs(gain_db) > 0.2:
            level_notes.append((i, round(gain_db, 2)))
            if gain_db > 0:
                xa = xa * 10 ** (-gain_db / 20)
            else:
                xb = xb * 10 ** (gain_db / 20)
        sf.write(f"{kit}/trial_{i:02d}_A.wav", xa, sr, subtype="PCM_16")
        sf.write(f"{kit}/trial_{i:02d}_B.wav", xb, sr, subtype="PCM_16")
        key.append({"trial": i, "A": na, "B": nb, "what": desc, "rms_diff_db_A_minus_B": round(rms_db(xa) - rms_db(xb), 2)})
    json.dump({"note": "DO NOT OPEN UNTIL ALL TRIALS ARE ANSWERED", "trials": key}, open(f"{kit}/answer_key.json", "w"), indent=1)
    open(f"{kit}/response_sheet.md", "w", encoding="utf-8").write(RESPONSE_SHEET.format(
        n=len(trials), rows="\n".join(f"| {i:02d} | | | | | | | | | |" for i in range(1, len(trials) + 1))))
    json.dump(report, open(f"{work}/chain_report.json", "w"), indent=1)
    print(json.dumps(report, indent=1))
    print("level matching applied (trial, dB):", level_notes)


RESPONSE_SHEET = """# Blind listening sheet: {n} trials (Phase 19)

Do not open answer_key.json until you have answered every trial. Use the same headphones/speakers and volume for all.
For each trial play A and B (any number of times, any order) and fill in one line.

Categories for each aspect: NOT NOTICEABLE / SLIGHT / MODERATE / CLEAR (difference between A and B).

| Trial | Different? (yes/no/unsure) | Clarity | Vocal quality | High-frequency artifacts | Stereo image | Transients | Distortion | Which do you prefer (A/B/none) | Confidence (low/medium/high) |
|---|---|---|---|---|---|---|---|---|---|
{rows}

Some trials play the identical file twice (to measure false positives); do not try to guess which.
Level matching: the loudness of A and B was matched to within 0.2 dB by a gain change only (no normalization or
compression); see answer_key.json (rms_diff_db) afterwards.
Conclusion options: 1 no audible difference detected / 2 difference occasionally detected / 3 difference consistently
detected / 4 inconclusive. Record which one applies and do not report "FLAC sounds better" unless your answers show it.
"""


# -- command: stems ------------------------------------------------------------------------------------------------


def frames_silent(x: np.ndarray, thresh_db: float) -> float:
    m = mono(x)
    n = 4800
    fr = m[: len(m) // n * n].reshape(-1, n)
    lv = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    return round(float((lv < thresh_db).mean()), 3)


def onset_rate(x: np.ndarray) -> float:
    f, t, s = signal.stft(mono(x), fs=48000, nperseg=1024, noverlap=512)
    mag = np.abs(s)
    flux = np.maximum(mag[:, 1:] - mag[:, :-1], 0).sum(axis=0)
    if flux.max() <= 0:
        return 0.0
    thr = flux.mean() + 1.5 * flux.std()
    peaks, _ = signal.find_peaks(flux, height=thr, distance=6)
    return round(len(peaks) / (len(mono(x)) / 48000), 2)


def centroid_hz(x: np.ndarray) -> float:
    f, p = signal.welch(mono(x), fs=48000, nperseg=4096)
    return round(float((f * p).sum() / (p.sum() or 1e-20)), 0)


def stereo_corr(x: np.ndarray) -> float:
    l, r = x[:, 0], x[:, 1]
    d = float(np.sqrt((l ** 2).sum() * (r ** 2).sum())) or 1e-20
    return round(float((l * r).sum() / d), 3)


def cmd_stems(a) -> None:
    kit = a.kit_dir
    os.makedirs(kit, exist_ok=True)
    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    rows = conn.execute(
        "select v.version_number, v.operation, v.operation_params, j.id, j.result_json, v.song_id from versions v join jobs j on j.version_id = v.id "
        "where j.status = 'COMPLETED' order by v.created_at").fetchall()
    song = next(r[5] for r in rows if r[3] == a.source_job)  # only this Song's Versions: the database may hold other Songs' stems
    items = {}
    for num, op, params, jid, result, song_id in rows:
        if song_id != song:
            continue
        audio = json.loads(result)["audio"]
        path = os.path.join(a.audio_root, audio["key"])
        title = None
        if op == "EXTRACT":
            items[json.loads(params)["track_name"]] = path
        elif op == "ORIGINAL" and a.source_job and jid == a.source_job:
            items["mix"] = path
    assert "mix" in items, "pass --source-job <job id of the mix Version>"
    work = a.work_dir
    os.makedirs(work, exist_ok=True)
    wav = {}
    for name, path in items.items():
        ffmpeg_to_wav(path, f"{work}/{name}.wav")
        wav[name] = load(f"{work}/{name}.wav")
    mix = wav["mix"]
    report = []
    for name, x in wav.items():
        row = {"item": name, "seconds": round(len(x) / 48000, 1), "rms_db": rms_db(x), "peak_db": peak_db(x), "silent_frames_below_-60db": frames_silent(x, -60),
               "silent_frames_below_-45db": frames_silent(x, -45), "bands": band_fractions(x), "spectral_centroid_hz": centroid_hz(x),
               "onsets_per_second": onset_rate(x), "stereo_correlation": stereo_corr(x)}
        if name != "mix":
            n = min(len(x), len(mix))
            a_, b_ = mono(x)[:n], mono(mix)[:n]
            row["correlation_with_mix"] = round(float((a_ * b_).sum() / (np.sqrt((a_ ** 2).sum() * (b_ ** 2).sum()) or 1e-20)), 3)
            row["energy_share_of_mix_db"] = round(10 * np.log10(float((a_ ** 2).sum()) / (float((b_ ** 2).sum()) or 1e-20)), 1)
        report.append(row)
    stems = [w for k, w in wav.items() if k != "mix"]
    if stems:
        n = min(len(w) for w in stems + [mix])
        s = sum(mono(w)[:n] for w in stems)
        g = float((s * mono(mix)[:n]).sum() / ((s ** 2).sum() or 1e-20))
        residual = mono(mix)[:n] - g * s
        report.append({"item": "sum of the extracted stems vs mix", "best_gain": round(g, 2), "snr_db": round(10 * np.log10(float((mono(mix)[:n] ** 2).sum()) / (float((residual ** 2).sum()) or 1e-20)), 1)})
    # Blind stem kit: shuffled neutral labels; the listener identifies what they hear and rates it.
    names = list(wav)
    rng = random.Random(a.seed)
    order = names[:]
    rng.shuffle(order)
    key = {}
    for i, name in enumerate(order, start=1):
        sf.write(f"{kit}/stem_S{i}.wav", wav[name], 48000, subtype="PCM_16")
        key[f"S{i}"] = name
    json.dump({"note": "DO NOT OPEN UNTIL ALL FILES ARE RATED", "labels": key}, open(f"{kit}/stem_answer_key.json", "w"), indent=1)
    open(f"{kit}/stem_response_sheet.md", "w", encoding="utf-8").write(STEM_SHEET)
    json.dump(report, open(f"{work}/stem_report.json", "w"), indent=1)
    print(json.dumps(report, indent=1))


STEM_SHEET = """# Blind stem listening sheet (Phase 19)

Files stem_S1.wav ... stem_S5.wav are shuffled and unlabeled: one is the full mix, the others are extracted stems.
Do not open stem_answer_key.json until you are done. For each file write what you hear, then rate it.

Rating categories: CLEAN / USABLE / PARTIALLY USABLE / POOR / UNUSABLE (descriptive, not a product ranking).

| File | What do you think it is? | Expected content present? | Unwanted bleed | Artifacts | Missing content | Distortion | Phase/hollow sound | Musically useful | Rating |
|---|---|---|---|---|---|---|---|---|---|
| S1 | | | | | | | | | |
| S2 | | | | | | | | | |
| S3 | | | | | | | | | |
| S4 | | | | | | | | | |
| S5 | | | | | | | | | |

Do not call anything "professional" or "studio quality" without a reference to compare against.
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("chain")
    c.add_argument("--work-dir", required=True)
    c.add_argument("--kit-dir", required=True)
    c.add_argument("--seed", type=int, default=19)
    c.add_argument("--reuse", action="store_true", help="re-analyse the files already in --work-dir instead of generating")
    s = sub.add_parser("stems")
    s.add_argument("--db", required=True)
    s.add_argument("--audio-root", required=True)
    s.add_argument("--kit-dir", required=True)
    s.add_argument("--work-dir", required=True)
    s.add_argument("--source-job", required=True)
    s.add_argument("--seed", type=int, default=19)
    a = ap.parse_args()
    (cmd_chain if a.cmd == "chain" else cmd_stems)(a)


if __name__ == "__main__":
    main()
