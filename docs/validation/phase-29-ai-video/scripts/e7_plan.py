"""E7: deterministic shot plan for a section of the real Tunora song (lab script, not production).

Inputs (all produced by existing OSS / existing Tunora data): song/analysis.json (Beat This! downbeats,
TimedLyrics lines, ACE-Step BPM) and jobs/character.json. One shot per 4/4 bar; the verse/chorus
boundary comes from TimedLyrics. Output: jobs/plan_<orientation>.json + keyframe/clip job files.

Usage: python e7_plan.py <start_downbeat_s> <bars> <portrait|landscape>
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
FPS = 24

VERSE = [  # (keyframe framing + environment, motion prompt, camera)
    ("Medium shot of {c}, eyes closed, hands in a soft mudra", "she sways gently and slowly opens her eyes, small graceful hand movements", "slow push-in", "sandstone palace courtyard at dusk, marigold garlands, oil lamps"),
    ("Full body shot of {c}, walking forward with the dupatta trailing", "she walks forward gracefully, the saffron dupatta trailing in the breeze", "slow tracking shot", "long colonnade of carved sandstone arches at dusk"),
    ("Close-up of {c}, looking over her shoulder", "she turns her head toward the camera and smiles softly, earrings swaying", "static close-up", "warm lantern light, blurred palace background"),
    ("Full body shot of {c}, in a classical dance pose", "she performs slow classical dance steps with expressive arm movements", "slow orbit around her", "palace courtyard with a reflecting pool at dusk"),
    ("Medium shot of {c}, raising both arms toward the sky", "she lifts both arms upward with rising energy, bangles catching the light", "slow tilt up", "rooftop terrace at golden hour, misty old city behind"),
]
CHORUS = [
    ("Full body shot of {c}, mid-spin", "she spins energetically, the lehenga flaring out and the dupatta flying", "wide shot, slight low angle", "rooftop terrace at sunrise, warm golden backlight"),
    ("Full body shot of {c}, dancing joyfully", "she dances with energetic rhythmic footwork and sweeping arm movements", "handheld follow shot", "festival courtyard full of hanging marigolds and string lights at night"),
    ("Medium shot of {c}, laughing with arms open wide", "she opens her arms wide and leans back joyfully, flower petals falling around her", "slow push-in", "temple steps lit by hundreds of small oil lamps at night"),
    ("Full body shot of {c}, leaping", "she performs a graceful leap and lands softly, dupatta flowing", "wide shot", "open field of tall golden grass at sunrise"),
    ("Full body shot of {c}, final triumphant pose", "she finishes a spin and strikes a triumphant pose with one arm raised high", "slow pull-back crane shot", "palace rooftop at night with fireworks in the sky"),
]


def main() -> None:
    start, bars, orientation = float(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    w, h = (704, 1280) if orientation == "portrait" else (1280, 704)
    ana = json.loads((LAB / "song/analysis.json").read_text(encoding="utf-8"))
    ch = json.loads((LAB / "jobs/character.json").read_text(encoding="utf-8"))
    downs = [d for d in ana["beat_this"]["downbeats"] if d >= start - 1e-6]
    bar = 60 / ana["beat_this"]["tempo_from_median_ibi"] * 4
    edges = [downs[i] if i < len(downs) else downs[-1] + bar * (i - len(downs) + 1) for i in range(bars + 1)]
    chorus = ana["chorus_start"]
    style = ch["style"].replace("vertical composition", "vertical composition" if orientation == "portrait" else "wide cinematic composition")
    boundary = min(edges, key=lambda d: abs(d - chorus))  # section change snaps to the downbeat nearest the chorus vocal
    shots, v, c = [], 0, 0
    for i in range(bars):
        s, e = round(edges[i], 3), round(edges[i + 1], 3)
        section = "chorus" if s >= boundary - 1e-6 else "verse"
        tmpl = (CHORUS[c % len(CHORUS)] if section == "chorus" else VERSE[v % len(VERSE)])
        c, v = (c + 1, v) if section == "chorus" else (c, v + 1)
        frame_desc, motion, camera, env = tmpl
        dur = e - s
        frames = 4 * math.ceil((dur * FPS - 1) / 4) + 1  # Wan needs 4k+1 frames and must cover the bar
        key_prompt = f"{frame_desc.format(c=ch['character'])}, {env}. {style}"
        clip_prompt = (f"{ch['character']}. {motion}. Setting: {env}. Camera: {camera}. "
                       f"Cinematic Indian music video, smooth natural motion, consistent costume.")
        shots.append({"index": i + 1, "start": s, "end": e, "duration": round(dur, 3), "section": section,
                      "camera": camera, "environment": env, "action": motion, "frames": frames,
                      "seed": 1000 + i, "keyframe": f"shot{i+1:02d}_{orientation}", "keyframe_prompt": key_prompt,
                      "clip_prompt": clip_prompt, "width": w, "height": h})
    plan = {"song_version": "ver-53c1604d-ccc4-46ac-ae2c-2b172d6dc3c1", "orientation": orientation,
            "window": [edges[0], edges[-1]], "bar_seconds": round(bar, 3), "chorus_start": chorus, "shots": shots}
    (LAB / f"jobs/plan_{orientation}.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
    kf = [{"name": s["keyframe"], "prompt": s["keyframe_prompt"], "width": w, "height": h, "seed": 500 + s["index"]} for s in shots]
    (LAB / f"jobs/keyframes_{orientation}.json").write_text(json.dumps(kf, indent=1, ensure_ascii=False), encoding="utf-8")
    clips = [{"name": f"clip{s['index']:02d}_{orientation}", "prompt": s["clip_prompt"], "width": w, "height": h,
              "frames": s["frames"], "seed": s["seed"],
              "image": str(LAB / f"outputs/keyframes_{orientation}/{s['keyframe']}.png")} for s in shots]
    (LAB / f"jobs/clips_{orientation}.json").write_text(json.dumps(clips, indent=1, ensure_ascii=False), encoding="utf-8")
    for s in shots:
        print(f"Shot {s['index']:02d} {s['start']:6.2f}-{s['end']:6.2f} {s['section']:6} {s['frames']}f  {s['camera']:28} | {s['action'][:60]}")


if __name__ == "__main__":
    main()
