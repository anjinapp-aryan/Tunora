"""Phase 30 lab worker: generates exactly ONE shot output in its own process, then exits.

Kinds:
  zimage_keyframe  Z-Image-Turbo text-to-image (Phase 29 method, text-only identity)
  klein_keyframe   FLUX.2-klein-4B text-to-image or reference-image edit (multi-reference identity)
  fastwan_clip     FastWan2.2-TI2V-5B 3-step DMD image-to-video (Phase 29 configuration, reused from scripts/e2_wan.py)

Usage: python shot_worker.py <job.json>
job.json: {"shot_id", "kind", "out", "prompt", "width", "height", "seed", ["frames"], ["image"], ["refs"], ["inject"]}
Writes <out>.result.json. Exit 0 = worker believes it succeeded (the controller still validates).
`inject` (failure-injection, lab only): crash_after_load | exception | hang | missing_output | invalid_output | corrupt_mp4
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB / "scripts"))

T0 = time.perf_counter()
KLEIN = LAB / "hf-home/hub/models--black-forest-labs--FLUX.2-klein-4B/snapshots/e7b7dc27f91deacad38e78976d1f2b499d76a294"
ZIMAGE = LAB / "models/z-image-turbo-bf16"
WAN = LAB / "hf-home/hub/models--Wan-AI--Wan2.2-TI2V-5B-Diffusers/snapshots/b8fff7315c768468a5333511427288870b2e9635"
FASTWAN = LAB / "hf-home/hub/models--FastVideo--FastWan2.2-TI2V-5B-FullAttn-Diffusers/snapshots/3e187042a324f6f5fb68fd22110a78725253de8f/transformer"
DMD_SIGMAS = [1.0, 0.757, 0.522]


def main() -> int:
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(job["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    inject = job.get("inject")
    result = {"shot_id": job["shot_id"], "kind": job["kind"], "pid": os.getpid(), "inject": inject}

    if inject == "exception":
        raise RuntimeError("injected generation exception")
    if inject == "missing_output":
        return 0
    if inject == "invalid_output":
        out.write_bytes(b"this is not a video or image")
        return 0
    if inject == "hang":
        while True:
            time.sleep(60)

    import torch

    t_load = time.perf_counter()
    if job["kind"] == "zimage_keyframe":
        from diffusers import ZImagePipeline
        pipe = ZImagePipeline.from_pretrained(str(ZIMAGE), torch_dtype=torch.bfloat16)
        pipe.enable_model_cpu_offload()
    elif job["kind"] == "klein_keyframe":
        from diffusers import Flux2KleinPipeline
        pipe = Flux2KleinPipeline.from_pretrained(str(KLEIN), torch_dtype=torch.bfloat16)
        pipe.enable_model_cpu_offload()
    elif job["kind"] == "fastwan_clip":
        from diffusers import AutoencoderKLWan, WanImageToVideoPipeline, WanTransformer3DModel
        from e2_wan import NEG, FixedSigmaScheduler
        vae = AutoencoderKLWan.from_pretrained(str(WAN / "vae"), torch_dtype=torch.float32)
        transformer = WanTransformer3DModel.from_pretrained(str(FASTWAN), torch_dtype=torch.bfloat16)
        pipe = WanImageToVideoPipeline.from_pretrained(str(WAN), vae=vae, transformer=transformer, torch_dtype=torch.bfloat16)
        pipe.vae.enable_tiling()
        FixedSigmaScheduler.fixed_sigmas = DMD_SIGMAS
        pipe.scheduler = FixedSigmaScheduler.from_config(pipe.scheduler.config, stochastic_sampling=True, shift=1.0,
                                                         use_dynamic_shifting=False)
        pipe.text_encoder.to("cuda")
        with torch.no_grad():
            pe, ne = pipe.encode_prompt(prompt=job["prompt"], negative_prompt=NEG, do_classifier_free_guidance=True,
                                        max_sequence_length=512, device=torch.device("cuda"), dtype=torch.bfloat16)
        pipe.text_encoder = None
        import gc; gc.collect(); torch.cuda.empty_cache()
        pipe.enable_model_cpu_offload()
    else:
        raise ValueError(f"unknown kind {job['kind']}")
    result["load_seconds"] = round(time.perf_counter() - t_load, 1)

    if inject == "crash_after_load":
        os._exit(3)
    if inject == "hang_after_load":  # models resident in RAM/VRAM, process never returns (Phase 29 hang shape)
        x = torch.ones(1, device="cuda")
        while True:
            time.sleep(60)

    from PIL import Image
    t_gen = time.perf_counter()
    gen = torch.Generator("cpu").manual_seed(job["seed"])
    if job["kind"] == "zimage_keyframe":
        image = pipe(prompt=job["prompt"], height=job["height"], width=job["width"], num_inference_steps=9,
                     guidance_scale=0.0, generator=torch.Generator("cuda").manual_seed(job["seed"])).images[0]
        image.save(out)
    elif job["kind"] == "klein_keyframe":
        kw = {}
        if job.get("refs"):
            kw["image"] = [Image.open(p).convert("RGB") for p in job["refs"]]
        image = pipe(prompt=job["prompt"], height=job["height"], width=job["width"], num_inference_steps=4,
                     guidance_scale=1.0, generator=torch.Generator("cuda").manual_seed(job["seed"]), **kw).images[0]
        image.save(out)
    else:
        import numpy as np
        from e2_wan import write_video
        frames = pipe(prompt_embeds=pe, negative_prompt_embeds=ne, image=Image.open(job["image"]).convert("RGB").resize((job["width"], job["height"])),
                      height=job["height"], width=job["width"], num_frames=job["frames"], num_inference_steps=len(DMD_SIGMAS),
                      guidance_scale=1.0, output_type="np", generator=gen).frames[0]
        write_video(np.asarray(frames), out)
        if inject == "corrupt_mp4":
            data = out.read_bytes()
            out.write_bytes(data[: len(data) // 3])
    result["generate_seconds"] = round(time.perf_counter() - t_gen, 1)
    result["torch_peak_alloc_mib"] = round(torch.cuda.max_memory_allocated() / 2**20)
    result["torch_peak_reserved_mib"] = round(torch.cuda.max_memory_reserved() / 2**20)
    result["worker_total_seconds"] = round(time.perf_counter() - T0, 1)
    out.with_suffix(out.suffix + ".result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
