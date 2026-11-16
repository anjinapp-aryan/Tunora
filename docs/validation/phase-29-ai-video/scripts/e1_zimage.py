"""E1/E4 keyframes: Z-Image-Turbo (Apache-2.0) via Diffusers ZImagePipeline, official settings
(bf16, 9 steps, guidance 0) + the officially documented enable_model_cpu_offload().

Usage: python e1_zimage.py <jobs.json> <out_dir> [--model <path-or-repo>] [--save-bf16 <dir>]
jobs.json: [{"name": ..., "prompt": ..., "width": 704, "height": 1280, "seed": 1}, ...]
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import torch
from diffusers import ZImagePipeline

from monitor import measure

REPO = "Tongyi-MAI/Z-Image-Turbo"
REV = "f332072aa78be7aecdf3ee76d5c247082da564a6"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs")
    ap.add_argument("out")
    ap.add_argument("--model", default=REPO)
    ap.add_argument("--save-bf16", default=None)
    args = ap.parse_args()
    jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    kw = {"revision": REV} if args.model == REPO else {}
    with measure("zimage_load", model=args.model):
        pipe = ZImagePipeline.from_pretrained(args.model, torch_dtype=torch.bfloat16, **kw)
    if args.save_bf16:
        with measure("zimage_save_bf16", target=args.save_bf16):
            pipe.save_pretrained(args.save_bf16, safe_serialization=True, max_shard_size="5GB")
    with measure("zimage_offload_setup"):
        pipe.enable_model_cpu_offload()

    for job in jobs:
        path = out / f"{job['name']}.png"
        with measure("zimage_generate", image=job["name"], width=job["width"], height=job["height"], seed=job["seed"]) as rec:
            image = pipe(prompt=job["prompt"], height=job["height"], width=job["width"],
                         num_inference_steps=9, guidance_scale=0.0,
                         generator=torch.Generator("cuda").manual_seed(job["seed"])).images[0]
            image.save(path)
            rec["bytes"] = os.path.getsize(path)
            rec["size"] = list(image.size)


if __name__ == "__main__":
    main()
