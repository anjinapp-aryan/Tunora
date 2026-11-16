"""E2/E3/E8 clips: Wan2.2 TI2V-5B (Apache-2.0) via Diffusers, official README settings
(bf16 transformer/text encoder, fp32 VAE, 50 steps, guidance 5.0, 24 fps) plus documented
Diffusers memory options only (model CPU offload, VAE tiling).

Usage: python e2_wan.py <jobs.json> <out_dir> [--offload model|sequential|none] [--vae-tiling]
jobs.json: [{"name", "prompt", "width", "height", "frames", "seed", "steps"?, "guidance"?, "image"?}]
Frames are written with Tunora's approved LGPL FFmpeg (OpenH264), never imageio/libx264.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np
import torch
from diffusers import (AutoencoderKLWan, FlowMatchEulerDiscreteScheduler, WanImageToVideoPipeline, WanPipeline,
                       WanTransformer3DModel)
from diffusers.utils import load_image

from monitor import measure

REPO = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
REV = "b8fff7315c768468a5333511427288870b2e9635"
FFMPEG = r"I:\Tunora\backend\tools\ffmpeg\bin\ffmpeg.exe"
NEG = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，"
       "多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走")
FPS = 24


class FixedSigmaScheduler(FlowMatchEulerDiscreteScheduler):
    """Diffusers' own stochastic flow-matching step (x0-predict + re-noise == DMD sampling), pinned to the
    model card's published DMD timesteps, because the pipeline only passes num_inference_steps."""
    fixed_sigmas: list[float] = []

    def set_timesteps(self, num_inference_steps=None, device=None, **kw):
        return super().set_timesteps(sigmas=list(self.fixed_sigmas), device=device)


def write_video(frames: np.ndarray, path: Path) -> None:
    """frames: (T, H, W, 3) float in [0, 1] -> H.264 (OpenH264) MP4 via the approved FFmpeg."""
    t, h, w, _ = frames.shape
    data = (np.clip(frames, 0, 1) * 255).round().astype(np.uint8).tobytes()
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", str(FPS), "-i", "pipe:0", "-c:v", "libopenh264", "-b:v", "12M",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]
    subprocess.run(cmd, input=data, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs")
    ap.add_argument("out")
    ap.add_argument("--offload", default="model", choices=["model", "sequential", "none"])
    ap.add_argument("--vae-tiling", action="store_true")
    ap.add_argument("--model", default=REPO)
    ap.add_argument("--transformer", default=None, help="alternative transformer dir (e.g. FastWan DMD)")
    ap.add_argument("--dmd-sigmas", default=None, help="e.g. 1.0,0.757,0.522 -> stochastic flow-matching, no CFG")
    ap.add_argument("--precompute-embeds", action="store_true",
                    help="encode all prompts with the text encoder on GPU, then drop it (documented prompt_embeds API)")
    args = ap.parse_args()
    jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    kw = {"revision": REV} if args.model == REPO else {}
    needs_i2v = any(j.get("image") for j in jobs)

    with measure("wan_load", offload=args.offload, vae_tiling=args.vae_tiling, i2v=needs_i2v):
        vae = AutoencoderKLWan.from_pretrained(args.model, subfolder="vae", torch_dtype=torch.float32, **kw)
        cls = WanImageToVideoPipeline if needs_i2v else WanPipeline
        extra = {}
        if args.transformer:
            extra["transformer"] = WanTransformer3DModel.from_pretrained(args.transformer, torch_dtype=torch.bfloat16)
        pipe = cls.from_pretrained(args.model, vae=vae, torch_dtype=torch.bfloat16, **kw, **extra)
        if args.dmd_sigmas:
            FixedSigmaScheduler.fixed_sigmas = [float(x) for x in args.dmd_sigmas.split(",")]
            pipe.scheduler = FixedSigmaScheduler.from_config(pipe.scheduler.config, stochastic_sampling=True, shift=1.0,
                                                             use_dynamic_shifting=False)
        if args.vae_tiling:
            pipe.vae.enable_tiling()
    embeds = {}
    if args.precompute_embeds:
        with measure("wan_encode_prompts", jobs=len(jobs)):
            pipe.text_encoder.to("cuda")
            with torch.no_grad():
                for job in jobs:
                    pe, ne = pipe.encode_prompt(prompt=job["prompt"], negative_prompt=NEG, do_classifier_free_guidance=True,
                                                max_sequence_length=512, device=torch.device("cuda"), dtype=torch.bfloat16)
                    embeds[job["name"]] = (pe, ne)
            pipe.text_encoder = None
            import gc; gc.collect(); torch.cuda.empty_cache()
    with measure("wan_offload_setup", offload=args.offload):
        if args.offload == "model":
            pipe.enable_model_cpu_offload()
        elif args.offload == "sequential":
            pipe.enable_sequential_cpu_offload()
        else:
            pipe.to("cuda")

    for job in jobs:
        path = out / f"{job['name']}.mp4"
        text = ({"prompt_embeds": embeds[job["name"]][0], "negative_prompt_embeds": embeds[job["name"]][1]}
                if embeds else {"prompt": job["prompt"], "negative_prompt": NEG})
        params = dict(**text, height=job["height"], width=job["width"],
                      num_frames=job["frames"],
                      num_inference_steps=len(FixedSigmaScheduler.fixed_sigmas) if args.dmd_sigmas else job.get("steps", 50),
                      guidance_scale=1.0 if args.dmd_sigmas else job.get("guidance", 5.0), output_type="np",
                      generator=torch.Generator("cpu").manual_seed(job["seed"]))
        if job.get("image"):
            params["image"] = load_image(job["image"]).resize((job["width"], job["height"]))
        with measure("wan_generate", clip=job["name"], width=job["width"], height=job["height"],
                     frames=job["frames"], steps=params["num_inference_steps"], seed=job["seed"],
                     i2v=bool(job.get("image")), offload=args.offload, vae_tiling=args.vae_tiling,
                     precompute_embeds=args.precompute_embeds, transformer=args.transformer or "base",
                     dmd_sigmas=args.dmd_sigmas, guidance=params["guidance_scale"]) as rec:
            t0 = time.perf_counter()
            frames = pipe(**params).frames[0]
            rec["infer_seconds"] = round(time.perf_counter() - t0, 1)
            write_video(np.asarray(frames), path)
            rec["bytes"] = os.path.getsize(path)
            rec["seconds_of_video"] = round(job["frames"] / FPS, 3)


if __name__ == "__main__":
    main()
