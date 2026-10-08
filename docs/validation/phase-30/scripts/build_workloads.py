"""Phase 30: build shot specs and controller workloads (lab only). Deterministic: re-running yields identical files."""
from __future__ import annotations

import json
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
P30 = LAB / "phase-30"
OUT = P30 / "outputs"

CHAR = ("an original fictional dancer named Asha, a woman in her mid-twenties with warm brown skin, long black hair in a "
        "single braid woven with small white jasmine flowers, a small red bindi, gold jhumka earrings, wearing a deep teal "
        "and gold silk lehenga with a mirror-work choli and a flowing mustard-saffron dupatta, gold bangles on both wrists")
SAME = ("The woman from the reference images: keep exactly the same face, the same skin tone, the same black braid with "
        "jasmine flowers, the same teal and gold lehenga with mirror-work choli, the same mustard-saffron dupatta and the "
        "same gold jewellery.")
STYLE = "Photorealistic cinematic Indian music-video still, sharp focus on her face."

# Shots 1-10: the real song plan (Phase 29, I Will Rise, one shot per bar).
SONG = [
    ("medium shot", "eyes closed, hands in a soft mudra, swaying gently", "sandstone palace courtyard at dusk with marigold garlands and oil lamps", "warm golden dusk light", "she sways gently and slowly opens her eyes, small graceful hand movements", "slow push-in"),
    ("full body shot", "walking forward with the dupatta trailing", "long colonnade of carved sandstone arches", "warm low sunset light", "she walks forward gracefully, the dupatta trailing in the breeze", "slow tracking shot"),
    ("close-up portrait", "looking over her shoulder and smiling softly", "blurred palace interior with lanterns", "soft lantern light", "she turns her head toward the camera and smiles softly, earrings swaying", "static close-up"),
    ("full body shot", "in a classical dance pose", "palace courtyard with a reflecting pool", "dusk light", "she performs slow classical dance steps with expressive arm movements", "slow orbit around her"),
    ("medium shot", "raising both arms toward the sky", "rooftop terrace with a misty old city behind", "golden hour light", "she lifts both arms upward with rising energy, bangles catching the light", "slow tilt up"),
    ("full body shot from a low angle", "mid-spin with the skirt flaring", "rooftop terrace at sunrise", "warm golden backlight", "she spins energetically, the lehenga flaring out and the dupatta flying", "wide shot"),
    ("full body shot", "dancing joyfully with arms out", "festival courtyard with hanging marigolds and string lights at night", "warm string-light glow", "she dances with rhythmic footwork and sweeping arm movements", "handheld follow shot"),
    ("medium shot", "laughing with arms open wide", "temple steps lit by hundreds of small oil lamps at night", "warm firelight", "she opens her arms wide and leans back joyfully, flower petals falling around her", "slow push-in"),
    ("full body wide shot", "about to leap", "open field of tall golden grass", "sunrise light", "she performs a graceful leap and lands softly, dupatta flowing", "wide shot"),
    ("full body shot", "in a triumphant pose with one arm raised", "palace rooftop at night with fireworks in the sky", "night light with firework glow", "she finishes a spin and strikes a triumphant pose with one arm raised high", "slow pull-back"),
]
# Shots 11-20: motion categories A-J.
MOTION = [
    ("A walking", "full body shot", "walking toward the camera", "village lane with whitewashed walls", "soft morning light", "she walks steadily toward the camera, arms relaxed, natural gait", "slow dolly back"),
    ("B turning", "full body shot", "standing with her back half turned", "marble hall with tall pillars", "soft window light", "she turns around 180 degrees to face the camera", "static camera"),
    ("C arm movement", "medium shot", "arms extended gracefully", "garden pavilion", "dappled afternoon light", "she performs flowing arm movements, her hands tracing slow circles in the air", "static camera"),
    ("D dance", "full body shot", "in a classical dance stance", "stage with a dark backdrop", "theatrical spotlight", "she performs a classical Indian dance sequence with rhythmic stamping footwork and hand gestures", "static wide camera"),
    ("E spinning", "full body shot", "beginning a spin", "large empty courtyard", "bright overcast light", "she spins in place rapidly, the skirt flaring out in a full circle", "static camera"),
    ("F full-body", "full body shot", "standing tall", "riverside ghat steps", "golden evening light", "she bends low and rises in one sweeping full-body dance movement", "static camera"),
    ("G fast movement", "full body shot", "mid-step in an energetic dance", "festival street with colorful flags", "bright daylight", "she dances fast with quick energetic steps and sharp arm movements", "handheld camera"),
    ("H leap/jump", "full body wide shot", "crouched, ready to jump", "sand dunes", "sunset light", "she leaps high into the air with legs extended and lands softly", "static wide camera"),
    ("I camera movement", "full body shot", "holding a still dance pose", "mirrored hall with chandeliers", "warm chandelier light", "she holds the pose while the camera orbits slowly around her", "orbiting camera"),
    ("J close-up face", "close-up portrait", "singing expressively", "dark studio background", "soft key light", "close-up, she sings expressively with clear lip and eyebrow movement, then smiles", "static close-up"),
]
# Shots 21-50: systematic variation.
ENVS = ["lotus pond at dawn", "busy spice market", "royal throne room with gold pillars", "misty tea plantation hills",
        "beach at sunset with gentle waves", "modern rooftop with city skyline at night", "candle-lit haveli corridor",
        "monsoon rain on a stone terrace", "desert fort ramparts", "flower-filled wedding mandap"]
FRAMES = ["close-up portrait", "medium shot", "full body shot", "wide shot", "low-angle full body shot", "high-angle medium shot"]
LIGHTS = ["soft morning light", "harsh midday sun", "golden hour backlight", "blue hour twilight", "neon and warm practical lights at night"]
POSES = ["smiling at the camera", "in a graceful dance pose with one hand raised", "looking into the distance", "mid-step in a dance",
         "kneeling with hands in a mudra", "twirling the dupatta"]
ACTIONS = ["she sways and smiles", "she dances slowly with flowing arms", "she turns her head and looks at the camera",
           "she steps forward in a dance step", "she twirls slowly", "she raises her hands gracefully"]
CAMS = ["slow push-in", "static camera", "slow pan", "slow orbit", "slow tilt up"]


def specs() -> list[dict]:
    out = []
    for i, (fr, pose, env, light, action, cam) in enumerate(SONG, 1):
        out.append({"n": i, "group": "song", "framing": fr, "pose": pose, "env": env, "light": light, "action": action, "camera": cam, "frames": 77})
    for j, (cat, fr, pose, env, light, action, cam) in enumerate(MOTION, 11):
        out.append({"n": j, "group": "motion", "category": cat, "framing": fr, "pose": pose, "env": env, "light": light, "action": action, "camera": cam, "frames": 77})
    for k in range(30):
        n = 21 + k
        out.append({"n": n, "group": "variation", "framing": FRAMES[k % len(FRAMES)], "pose": POSES[(k * 5) % len(POSES)],
                    "env": ENVS[k % len(ENVS)], "light": LIGHTS[(k * 3) % len(LIGHTS)], "action": ACTIONS[(k * 7) % len(ACTIONS)],
                    "camera": CAMS[(k * 2) % len(CAMS)], "frames": 121 if 31 <= n <= 35 else 77})
    return out


def main() -> None:
    S = specs()
    ref_full, ref_face = str(OUT / "refs/ref_full.png"), str(OUT / "refs/ref_face.png")
    refs = [
        {"shot_id": "ref_face", "kind": "klein_keyframe", "out": ref_face, "width": 1024, "height": 1024, "seed": 7002, "expected_seconds": 90,
         "prompt": f"Head and shoulders portrait, front view, of {CHAR}, neutral friendly expression, plain light grey studio background, even soft lighting. Character reference, photorealistic."},
        # Derived FROM ref_face (reference edit) so both references show the same person.
        {"shot_id": "ref_full", "kind": "klein_keyframe", "out": ref_full, "refs": [ref_face], "width": 704, "height": 1280, "seed": 7001, "expected_seconds": 90,
         "prompt": f"{SAME} Full body front view of her standing straight facing the camera, arms relaxed, single braid over her shoulder, plain light grey studio background, even soft lighting. Character reference sheet, photorealistic."},
    ]
    kf_klein, kf_z, clips = [], [], []
    for s in S:
        sid = f"s{s['n']:02d}"
        scene = f"{s['framing'].capitalize()} of her {s['pose']}, in a {s['env']}, {s['light']}."
        kf_klein.append({"shot_id": f"kf_{sid}", "kind": "klein_keyframe", "out": str(OUT / f"keyframes_klein/{sid}.png"),
                         "refs": [ref_full, ref_face], "width": 704, "height": 1280, "seed": 8000 + s["n"], "expected_seconds": 90,
                         "prompt": f"{SAME} {scene} {STYLE}", "spec": s})
        if s["n"] <= 10:
            kf_z.append({"shot_id": f"kfz_{sid}", "kind": "zimage_keyframe", "out": str(OUT / f"keyframes_zimage/{sid}.png"),
                         "width": 704, "height": 1280, "seed": 8000 + s["n"], "expected_seconds": 60,
                         "prompt": f"{s['framing'].capitalize()} of {CHAR}, {s['pose']}, in a {s['env']}, {s['light']}. {STYLE}", "spec": s})
        clips.append({"shot_id": f"clip_{sid}", "kind": "fastwan_clip", "out": str(OUT / f"clips/{sid}.mp4"),
                      "image": str(OUT / f"keyframes_klein/{sid}.png"), "width": 704, "height": 1280, "frames": s["frames"],
                      "seed": 9000 + s["n"], "expected_seconds": 225 if s["frames"] == 77 else 460,
                      "prompt": (f"{CHAR}. {s['action']}. Setting: {s['env']}, {s['light']}. Camera: {s['camera']}. "
                                 "Cinematic Indian music video, smooth natural motion, consistent face and costume."), "spec": s})
    (P30 / "jobs").mkdir(exist_ok=True)
    (P30 / "jobs/shot_specs.json").write_text(json.dumps(S, indent=1), encoding="utf-8")

    def wl(name, shots, state):
        return {"name": name, "state_dir": str(P30 / state), "timeout_factor": 2.5, "max_attempts": 2, "shots": shots}

    files = {
        "identity_refs.json": wl("identity references (klein)", refs, "identity/refs_state"),
        "identity_kf_klein_10.json": wl("klein keyframes 1-10", kf_klein[:10], "identity/klein_state"),
        "identity_kf_klein_20.json": wl("klein keyframes 1-20", kf_klein[:20], "identity/klein_state"),
        "identity_kf_klein_30.json": wl("klein keyframes 1-30", kf_klein[:30], "identity/klein_state"),
        "identity_kf_klein_50.json": wl("klein keyframes 1-50", kf_klein[:50], "identity/klein_state"),
        "identity_kf_zimage_10.json": wl("z-image text-only keyframes 1-10", kf_z, "identity/zimage_state"),
        "soak_clips_50.json": wl("soak: 50 FastWan clips from klein keyframes", clips, "soak/state"),
    }
    for f, w in files.items():
        (P30 / "jobs" / f).write_text(json.dumps(w, indent=1, ensure_ascii=False), encoding="utf-8")
    print({f: len(w["shots"]) for f, w in files.items()})


if __name__ == "__main__":
    main()
