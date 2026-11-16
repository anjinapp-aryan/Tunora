"""E6: analyse the real Tunora song with existing OSS only (librosa ISC, Beat This! MIT).

Writes song/analysis.json: duration, sample rate, ACE-Step BPM, librosa tempo/beats,
Beat This! beats/downbeats, and the section boundary taken from Tunora's own TimedLyrics.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import librosa
import numpy as np

LAB = Path(__file__).resolve().parents[1]
SONG = LAB / "song"


def main() -> None:
    song = json.loads((SONG / "song.json").read_text(encoding="utf-8"))
    timed = json.loads((SONG / "timed_lyrics.json").read_text(encoding="utf-8"))
    audio = SONG / "source.mp3"
    meta_bpm = 77  # Version metadata from ACE-Step (versions/job result), recorded in song.json

    t0 = time.perf_counter()
    y, sr = librosa.load(audio, sr=None, mono=True)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, start_bpm=meta_bpm, units="time")
    t_librosa = time.perf_counter() - t0

    from beat_this.inference import File2Beats

    t0 = time.perf_counter()
    f2b = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)
    bt_beats, bt_downbeats = f2b(str(audio))
    t_bt = time.perf_counter() - t0

    lines = [{"start": l["words"][0]["start"], "end": l["words"][-1]["end"], "text": l["text"]} for l in timed["lines"]]
    chorus = next(l for l in lines if l["text"].lower().startswith("i will rise"))

    ibi = np.diff(bt_beats)
    out = {
        "duration": round(len(y) / sr, 3), "sample_rate": int(sr),
        "ace_step_bpm": meta_bpm,
        "librosa": {"tempo": float(np.atleast_1d(tempo)[0]), "beats": [round(float(b), 3) for b in beats], "seconds": round(t_librosa, 2)},
        "beat_this": {"beats": [round(float(b), 3) for b in bt_beats], "downbeats": [round(float(b), 3) for b in bt_downbeats],
                      "tempo_from_median_ibi": round(60 / float(np.median(ibi)), 1) if len(ibi) else None, "seconds": round(t_bt, 2)},
        "timed_lyrics_lines": lines,
        "chorus_start": chorus["start"],
        "first_vocal": lines[0]["start"],
    }
    (SONG / "analysis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("timed_lyrics_lines",)}, indent=None)[:3000])


if __name__ == "__main__":
    main()
