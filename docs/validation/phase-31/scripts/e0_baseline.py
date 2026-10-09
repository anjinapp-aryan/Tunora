"""Phase 31 E0: hardware/software baseline -> phase-31/hardware/hardware-baseline.json (lab only).
Copy of phase-30/e0_baseline.py plus a check that every Phase 30 model snapshot is present on disk."""
import json, platform, subprocess, sys, time, shutil
from pathlib import Path
import psutil, torch, diffusers, transformers, accelerate

def smi(q):
    return subprocess.run(["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip()

gpu = dict(zip(["name","memory_total_mib","memory_used_mib","memory_free_mib","driver","compute_cap","utilization_pct","temperature_c","power_w"],
               [x.strip() for x in smi("name,memory.total,memory.used,memory.free,driver_version,compute_cap,utilization.gpu,temperature.gpu,power.draw").split(",")]))
cpu_pct = psutil.cpu_percent(interval=3)
vm = psutil.virtual_memory()
disks = {d: round(shutil.disk_usage(d).free / 2**30, 2) for d in ("C:\\", "D:\\", "I:\\")}
models = {
    "z_image_turbo": {"repo": "Tongyi-MAI/Z-Image-Turbo", "revision": "f332072aa78be7aecdf3ee76d5c247082da564a6", "local": "models/z-image-turbo-bf16"},
    "wan22_ti2v_5b": {"repo": "Wan-AI/Wan2.2-TI2V-5B-Diffusers", "revision": "b8fff7315c768468a5333511427288870b2e9635", "used": "text_encoder, vae"},
    "fastwan22_ti2v_5b": {"repo": "FastVideo/FastWan2.2-TI2V-5B-FullAttn-Diffusers", "revision": "3e187042a324f6f5fb68fd22110a78725253de8f", "used": "transformer"},
    "flux2_klein_4b": {"repo": "black-forest-labs/FLUX.2-klein-4B", "revision": "e7b7dc27f91deacad38e78976d1f2b499d76a294", "used": "transformer, vae, tokenizer (Phase 30 candidate)"},
}
out = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "os": platform.platform(), "python": sys.version.split()[0],
       "cpu": platform.processor(), "cpu_count_logical": psutil.cpu_count(), "cpu_util_baseline_pct_3s": cpu_pct,
       "ram_total_gb": round(vm.total / 2**30, 2), "ram_available_gb": round(vm.available / 2**30, 2),
       "gpu": gpu, "disk_free_gb": disks,
       "torch": torch.__version__, "torch_cuda": torch.version.cuda, "cuda_available": torch.cuda.is_available(),
       "device_capability": list(torch.cuda.get_device_capability(0)), "diffusers": diffusers.__version__,
       "transformers": transformers.__version__, "accelerate": accelerate.__version__, "models": models,
       "ace_step_listening_8001": any(c.laddr and c.laddr.port == 8001 and c.status == "LISTEN" for c in psutil.net_connections("tcp"))}
sys.path.insert(0, str(Path(__file__).resolve().parent))
import shot_worker  # noqa: E402  (model paths used by the Phase 30/31 worker)
out["model_snapshots_present"] = {name: Path(str(getattr(shot_worker, name))).exists() for name in ("KLEIN", "ZIMAGE", "WAN", "FASTWAN")}
FF = str(Path("I:/Tunora/backend/tools/ffmpeg/bin/ffmpeg.exe"))
out["ffmpeg"] = subprocess.run([FF, "-hide_banner", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
out["ffmpeg_gpl"] = "--enable-gpl" in subprocess.run([FF, "-hide_banner", "-buildconf"], capture_output=True, text=True).stdout
Path(__file__).with_name("hardware").mkdir(exist_ok=True)
Path(__file__).with_name("hardware").joinpath("hardware-baseline.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
