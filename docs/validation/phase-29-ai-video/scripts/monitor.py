"""Measurement helper for the Phase 29 lab (not production code).

Samples, every 0.5 s on a background thread:
  * device VRAM used (nvidia-smi; whole GPU, includes the desktop's share)
  * this process's RSS and the system's available RAM (psutil)
and records torch's own peak allocation. Writes one JSON record per measured block.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import psutil

LOG = Path(__file__).resolve().parents[1] / "logs" / "measurements.jsonl"


def gpu_used_mib() -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=10).stdout
    return int(out.strip().splitlines()[0])


class Sampler:
    def __init__(self, interval: float = 0.5) -> None:
        self.interval = interval
        self.peak_gpu = 0
        self.peak_rss = 0
        self.min_avail = 1 << 62
        self._stop = threading.Event()
        self._proc = psutil.Process()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.peak_gpu = max(self.peak_gpu, gpu_used_mib())
            except Exception:
                pass
            self.peak_rss = max(self.peak_rss, self._proc.memory_info().rss)
            self.min_avail = min(self.min_avail, psutil.virtual_memory().available)
            self._stop.wait(self.interval)

    def start(self) -> "Sampler":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()


@contextmanager
def measure(name: str, **extra):
    import torch

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    record = {"name": name, "gpu_before_mib": gpu_used_mib(),
              "ram_avail_before_gb": round(psutil.virtual_memory().available / 2**30, 2), **extra}
    sampler = Sampler().start()
    started = time.perf_counter()
    status = "ok"
    try:
        yield record
    except BaseException as exc:
        status = f"error: {exc.__class__.__name__}: {str(exc)[:500]}"
        raise
    finally:
        sampler.stop()
        record.update({
            "status": status,
            "seconds": round(time.perf_counter() - started, 1),
            "gpu_peak_mib_nvsmi": sampler.peak_gpu,
            "torch_peak_alloc_mib": round(torch.cuda.max_memory_allocated() / 2**20) if torch.cuda.is_available() else None,
            "torch_peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20) if torch.cuda.is_available() else None,
            "proc_peak_rss_gb": round(sampler.peak_rss / 2**30, 2),
            "sys_min_avail_ram_gb": round(sampler.min_avail / 2**30, 2),
            "gpu_after_mib": gpu_used_mib(),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        print("MEASURE", json.dumps(record, ensure_ascii=False), flush=True)
