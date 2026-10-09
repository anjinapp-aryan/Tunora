"""Phase 31: controlled motion-vocabulary workloads (lab only). Deterministic: re-running yields identical files.

Design (isolates motion):
  * identity  = Phase 30 strategy unchanged: FLUX.2-klein reference-edit from Phase 30's two reference images
                (ref_face.png, ref_full.png) of the fictional performer "Asha"; same CHAR / SAME / STYLE text.
  * keyframes = a FEW fixed keyframes in ONE environment (full body + close-up). Every category clip starts from the
                same keyframe, so identity, costume, environment, light and framing are held constant.
  * clips     = FastWan2.2-TI2V-5B, Phase 30 prompt template; only the ACTION (and, for K-M, the CAMERA) text changes.
  * wording   = per category two wordings, W1 (plain) and W2 (descriptive), with the SAME seed (S1) -> wording effect.
  * repeat    = stage 2 re-runs the better wording with a second seed (S2) -> repeatability.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
P30, P31 = LAB / "phase-30", LAB / "phase-31"
OUT = P31 / "outputs"
REF_FULL, REF_FACE = str(P30 / "outputs/refs/ref_full.png"), str(P30 / "outputs/refs/ref_face.png")

sys.path.insert(0, str(P30))
from build_workloads import CHAR, SAME, STYLE, specs  # noqa: E402  (Phase 30 text reused verbatim)

S1, S2 = 31001, 31002
ENV, LIGHT = "sandstone palace courtyard with carved arches and marigold garlands", "warm golden-hour light"
END = "Cinematic Indian music video, smooth natural motion, consistent face and costume."  # Phase 30 suffix

KEYFRAMES = {
    "full": ("full body shot of her standing in the middle of the courtyard facing the camera, arms relaxed at her sides, "
             "plenty of open space around her", 704, 1280),
    "close": ("close-up portrait of her face and shoulders looking at the camera with a soft expression", 704, 1280),
    "full_land": ("wide full body shot of her standing in the middle of the courtyard facing the camera, arms relaxed at "
                  "her sides, plenty of open space around her", 1280, 704),
}

# (id, folder, name, keyframe, subject W1, subject W2, camera W1, camera W2). Camera "static camera" unless the
# category is a camera category; for K-M the SUBJECT text is fixed and the CAMERA text is the variable.
STATIC = "static camera"
VOCAB = [
    ("A", "walking", "walking", "full", "she walks toward the camera",
     "she walks slowly and gracefully toward the camera with a natural relaxed gait, arms swinging gently", STATIC, STATIC),
    ("B", "turning", "turning", "full", "she turns around",
     "she slowly turns her body in a graceful half circle and looks back over her shoulder at the camera", STATIC, STATIC),
    ("C", "arm", "arm / hand gestures", "full", "she raises both arms",
     "she performs graceful classical hand gestures, slowly raising both arms with flowing wrists and fingers", STATIC, STATIC),
    ("D", "sway", "body sway", "full", "she sways to the music",
     "she gently sways her upper body from side to side in rhythm, soft relaxed shoulders, a calm smile", STATIC, STATIC),
    ("E", "spinning", "spinning", "full", "she spins",
     "she performs one slow graceful spin in place, the skirt flaring softly", STATIC, STATIC),
    ("F", "full-body", "full-body performance", "full", "she performs to the music",
     "expressive full-body stage performance, she steps forward, bends and rises rhythmically with open arms", STATIC, STATIC),
    ("G", "dance-low", "dance - low intensity", "full", "she dances",
     "she performs a slow graceful traditional Indian dance with elegant hand gestures and small steps", STATIC, STATIC),
    ("H", "dance-medium", "dance - medium intensity", "full", "she dances energetically",
     "expressive choreographed dance performance with rhythmic steps and sweeping arm movements", STATIC, STATIC),
    ("I", "dance-high", "fast / high-energy movement", "full", "fast energetic dance",
     "powerful rapid choreographed dance with quick footwork and sharp arm movements", STATIC, STATIC),
    ("J", "leap", "leap / jump", "full", "she jumps",
     "she performs a small graceful dance leap into the air and lands softly", STATIC, STATIC),
    ("K", "camera-push", "camera push-in", "full", "she stands still and smiles softly", None,
     "slow push-in", "the camera slowly dollies forward toward her face, cinematic push-in"),
    ("L", "camera-track", "camera tracking", "full", "she walks slowly to the left", None,
     "tracking shot following her", "smooth lateral tracking shot, the camera moves sideways with her"),
    ("M", "camera-orbit", "camera orbit", "full", "she stands still in a graceful pose", None,
     "camera orbits around her", "slow cinematic arc around her, the background rotating behind her"),
    ("N", "close-up", "close-up performance", "close", "she sings toward the camera",
     "close-up, she sings expressively toward the camera with clear lip movement, then smiles warmly", "static close-up",
     "static close-up"),
]


def clip_prompt(action: str, camera: str, env: str = ENV, light: str = LIGHT) -> str:
    return f"{CHAR}. {action}. Setting: {env}, {light}. Camera: {camera}. {END}"


def kf_job(key: str) -> dict:
    scene, w, h = KEYFRAMES[key]
    return {"shot_id": f"kf_{key}", "kind": "klein_keyframe", "out": str(OUT / f"keyframes/{key}.png"),
            "refs": [REF_FULL, REF_FACE], "width": w, "height": h, "seed": 31100 + list(KEYFRAMES).index(key),
            "expected_seconds": 90, "prompt": f"{SAME} {scene.capitalize()}, in a {ENV}, {LIGHT}. {STYLE}"}


def clip_job(sid: str, folder: str, kf: str, action: str, camera: str, seed: int, meta: dict) -> dict:
    w, h = KEYFRAMES[kf][1:]
    return {"shot_id": sid, "kind": "fastwan_clip", "out": str(OUT / folder / f"{sid}.mp4"),
            "image": str(OUT / f"keyframes/{kf}.png"), "width": w, "height": h, "frames": 77, "seed": seed,
            "expected_seconds": 225, "prompt": clip_prompt(action, camera),
            "meta": {"action": action, "camera": camera, "keyframe": kf, **meta}}


def matrix() -> list[dict]:
    """Stage 1: every category x {W1, W2}, seed S1."""
    out = []
    for mid, folder, name, kf, a1, a2, c1, c2 in VOCAB:
        camera_cat = a2 is None
        for w in (1, 2):
            action = a1 if (camera_cat or w == 1) else a2
            camera = (c1 if w == 1 else c2) if camera_cat else c1
            out.append(clip_job(f"{mid}{w}_s1", folder, kf, action, camera, S1,
                                {"motion_id": mid, "motion": name, "wording": f"W{w}", "stage": "matrix"}))
    return out


def baseline() -> list[dict]:
    """Phase 30 reproduction: song shot s01 (I Will Rise, bar 1), identical prompt/seed/settings."""
    s = specs()[0]
    scene = f"{s['framing'].capitalize()} of her {s['pose']}, in a {s['env']}, {s['light']}."
    kf = {"shot_id": "base_kf_s01", "kind": "klein_keyframe", "out": str(OUT / "baseline/kf_s01.png"),
          "refs": [REF_FULL, REF_FACE], "width": 704, "height": 1280, "seed": 8001, "expected_seconds": 90,
          "prompt": f"{SAME} {scene} {STYLE}"}
    clip = {"shot_id": "base_clip_s01", "kind": "fastwan_clip", "out": str(OUT / "baseline/clip_s01.mp4"),
            "image": kf["out"], "width": 704, "height": 1280, "frames": 77, "seed": 9001, "expected_seconds": 225,
            "prompt": (f"{CHAR}. {s['action']}. Setting: {s['env']}, {s['light']}. Camera: {s['camera']}. {END}"),
            "meta": {"motion": "baseline (Phase 30 s01)", "stage": "baseline"}}
    return [kf, clip]


def composition() -> list[dict]:
    """Stage 2a: motion composition and camera-vs-subject, seed S1 (comparable with the matrix clips)."""
    a_turn = VOCAB[1][5]  # B W2 subject text
    a_sway = VOCAB[3][5]  # D W2 subject text
    rows = [
        ("X1", "composition", "she slowly turns her body while making graceful flowing arm movements", STATIC,
         {"motion": "composition: 2 concepts (turn + arms)", "level": "simple"}),
        ("X2", "composition", "she gently sways side to side, then raises both arms gracefully above her head and smiles",
         STATIC, {"motion": "composition: 3 concepts (sway + arms + expression)", "level": "medium"}),
        ("X3", "composition", "fast energetic dance with spinning, jumping and complex choreography",
         "camera orbits around her with a dramatic zoom", {"motion": "composition: overloaded (5+ concepts)", "level": "overloaded"}),
        ("Y1", "camera-vs-subject", a_turn, "slow push-in", {"motion": "turning (B W2) + camera push-in", "pair": "B2_s1"}),
        ("Y2", "camera-vs-subject", a_sway, "slow push-in", {"motion": "sway (D W2) + camera push-in", "pair": "D2_s1"}),
    ]
    return [clip_job(f"{sid}_s1", folder, "full", action, camera, S1, {"motion_id": sid, "stage": "composition", **meta})
            for sid, folder, action, camera, meta in rows]


def followup() -> list[dict]:
    """Stage 3: the EXPLICIT push-in sentence (worked in K2 with a still subject) combined with subject motion."""
    rows = [("Y3", "camera-vs-subject", VOCAB[1][5], VOCAB[10][7], {"motion": "turning (B W2) + explicit push-in (K W2)", "pair": "B2_s1"})]
    return [clip_job(f"{sid}_s1", folder, "full", action, camera, S1, {"motion_id": sid, "stage": "composition", **meta})
            for sid, folder, action, camera, meta in rows]


# Stage 2b repeat test: the better stage-1 wording of each candidate, second seed S2, same keyframe.
# (stage-1 id whose action/camera is repeated)
REPEATS = ["A1", "B1", "C1", "E2", "F2", "K2", "I2", "L1"]
# Close-up retest: both stage-1 close-ups contained "toward the camera" and both raised a hand at the lens.
N3 = ("close-up, she sings expressively with clear lip movement, then smiles warmly, her hands out of frame", "static close-up")


def repeats(matrix_shots: list[dict]) -> list[dict]:
    by = {s["shot_id"].split("_")[0]: s for s in matrix_shots}
    out = []
    for rid in REPEATS:
        m = by[rid]["meta"]
        out.append(clip_job(f"{rid}_s2", Path(by[rid]["out"]).parent.name, m["keyframe"], m["action"], m["camera"], S2,
                            {**{k: m[k] for k in ("motion_id", "motion", "wording")}, "stage": "repeat", "repeat_of": f"{rid}_s1"}))
    for seed, tag in ((S1, "s1"), (S2, "s2")):
        out.append(clip_job(f"N3_{tag}", "close-up", "close", N3[0], N3[1], seed,
                            {"motion_id": "N", "motion": "close-up performance", "wording": "W3", "stage": "repeat"}))
    return out


# 30-second montage (I Will Rise, Phase 29 bar plan 22.72-53.90 s, 10 bars of 3.12 s). Candidate motions only, each
# in a NEW scene (also tests whether the vocabulary generalises beyond the test courtyard).
# (bar, motion id used, framing, pose for the keyframe, environment, light, action, camera)
MONTAGE = [
    (1, "K2", "full body shot", "standing calmly, hands softly together", "palace courtyard at dusk with marigold garlands and oil lamps",
     "warm golden dusk light", "she stands still and smiles softly", "the camera slowly dollies forward toward her face, cinematic push-in"),
    (2, "A1", "full body shot", "standing at the far end, facing the camera", "long colonnade of carved sandstone arches",
     "warm low sunset light", "she walks toward the camera", STATIC),
    (3, "C1", "full body shot", "standing with arms relaxed", "rooftop terrace with a misty old city behind",
     "golden hour light", "she raises both arms", STATIC),
    (4, "B1", "full body shot", "standing facing the camera", "marble hall with tall pillars", "soft window light",
     "she turns around", STATIC),
    (5, "N3", "close-up portrait", "looking at the camera with a soft expression", "temple steps lit by many small oil lamps at night",
     "warm firelight", N3[0], N3[1]),
    (6, "E2", "full body shot", "standing with arms relaxed", "rooftop terrace at sunrise", "warm golden backlight",
     "she performs one slow graceful spin in place, the skirt flaring softly", STATIC),
    (7, "F2", "full body shot", "standing tall", "festival courtyard with hanging marigolds and string lights at night",
     "warm string-light glow", "expressive full-body stage performance, she steps forward, bends and rises rhythmically with open arms", STATIC),
    (8, "C1", "full body shot", "standing with arms relaxed", "open field of tall golden grass", "sunrise light",
     "she raises both arms", STATIC),
    (9, "E1", "full body shot", "standing facing the camera", "lotus pond terrace at dawn", "soft pink dawn light", "she spins", STATIC),
    (10, "A2", "full body shot", "standing at the far side of the rooftop", "palace rooftop at night with fireworks in the sky",
     "night light with firework glow", "she walks slowly and gracefully toward the camera with a natural relaxed gait, arms swinging gently", STATIC),
]
LANDSCAPE_BARS = [6, 7, 8, 9, 10]  # 16:9 comparison: the chorus half, same scenes and motions


def montage(orientation: str) -> tuple[list[dict], list[dict]]:
    land = orientation == "landscape"
    w, h = (1280, 704) if land else (704, 1280)
    folder, tag = ("montage_16x9", "l") if land else ("montage", "p")
    kfs, clips = [], []
    for bar, mid, framing, pose, env, light, action, camera in MONTAGE:
        if land and bar not in LANDSCAPE_BARS:
            continue
        fr = ("wide " + framing) if land and framing.startswith("full") else framing
        kf = {"shot_id": f"mkf_{tag}{bar:02d}", "kind": "klein_keyframe", "out": str(OUT / f"{folder}/keyframes/bar{bar:02d}.png"),
              "refs": [REF_FULL, REF_FACE], "width": w, "height": h, "seed": 31200 + bar + (50 if land else 0), "expected_seconds": 90,
              "prompt": f"{SAME} {fr.capitalize()} of her {pose}, centred in the frame, in a {env}, {light}. {STYLE}"}
        kfs.append(kf)
        clips.append({"shot_id": f"m{tag}_{bar:02d}", "kind": "fastwan_clip", "out": str(OUT / f"{folder}/clips/clip{bar:02d}_p31.mp4"),
                      "image": kf["out"], "width": w, "height": h, "frames": 77, "seed": 31300 + bar, "expected_seconds": 225,
                      "prompt": clip_prompt(action, camera, env, light),
                      "meta": {"motion_id": mid, "motion": f"montage bar {bar} ({mid})", "action": action, "camera": camera,
                               "stage": f"montage-{orientation}", "bar": bar}})
    return kfs, clips


def wl(name: str, shots: list[dict], state: str) -> dict:
    return {"name": name, "state_dir": str(P31 / state), "timeout_factor": 2.5, "max_attempts": 2, "shots": shots}


def main() -> None:
    files = {
        "baseline.json": wl("Phase 30 baseline reproduction (s01)", baseline(), "metrics/baseline_state"),
        "keyframes.json": wl("Phase 31 fixed keyframes", [kf_job(k) for k in KEYFRAMES], "metrics/kf_state"),
        "matrix.json": wl("Phase 31 stage 1: 14 categories x 2 wordings, seed S1", matrix(), "metrics/clip_state"),
        "composition.json": wl("Phase 31 stage 2a: composition + camera-vs-subject, seed S1", composition(),
                               "metrics/clip_state"),
        "repeats.json": wl("Phase 31 stage 2b: repeat best wordings with seed S2 + close-up retest", repeats(matrix()),
                           "metrics/clip_state"),
    }
    pk, pc = montage("portrait")
    lk, lc = montage("landscape")
    files["montage_keyframes.json"] = wl("Phase 31 montage keyframes (10 x 9:16, 5 x 16:9)", pk + lk, "metrics/kf_state")
    files["followup.json"] = wl("Phase 31 stage 3: explicit camera sentence + subject motion", followup(), "metrics/clip_state")
    files["montage_clips.json"] = wl("Phase 31 montage clips (10 x 9:16, 5 x 16:9)", pc + lc, "metrics/montage_state")
    (P31 / "jobs").mkdir(exist_ok=True)
    for f, w in files.items():
        (P31 / "jobs" / f).write_text(json.dumps(w, indent=1, ensure_ascii=False), encoding="utf-8")
    print({f: len(w["shots"]) for f, w in files.items()})


if __name__ == "__main__":
    main()
