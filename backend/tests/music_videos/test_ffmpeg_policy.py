"""Tunora's FFmpeg policy (Phase 23): LGPL-only, with the capabilities the renderer needs."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.music_videos import ffmpeg as policy
from app.music_videos.errors import FFmpegPolicyError

LGPL_CONFIG = "configuration: --enable-version3 --enable-libass --enable-libopenh264 --enable-shared"
FILTERS = "\n".join(f" .. {n}  V->V  x" for n in policy.REQUIRED_FILTERS)
ENCODERS = " V....D libopenh264  OpenH264\n A....D aac  AAC"


def _fake_bin(tmp_path: Path) -> Path:
    for name in ("ffmpeg", "ffprobe"):
        (tmp_path / f"{name}{policy._EXE}").write_bytes(b"")
    return tmp_path


def _runner(config=LGPL_CONFIG, filters=FILTERS, encoders=ENCODERS):
    def run(args):
        if "-version" in args:
            return f"ffmpeg version test\nbuilt with gcc\n{config}\n"
        return filters if "-filters" in args else encoders
    return run


def test_an_lgpl_build_with_the_required_features_is_accepted(tmp_path):
    tools = policy.inspect(_fake_bin(tmp_path), _runner())
    assert tools.configuration == LGPL_CONFIG and tools.version == "ffmpeg version test"


@pytest.mark.parametrize("flag", ["--enable-gpl", "--enable-nonfree"])
def test_gpl_or_nonfree_builds_are_rejected(tmp_path, flag):
    with pytest.raises(FFmpegPolicyError, match="GPL/non-free"):
        policy.inspect(_fake_bin(tmp_path), _runner(config=f"{LGPL_CONFIG} {flag} --enable-libx264"))


@pytest.mark.parametrize("filters, encoders, missing", [
    (FILTERS.replace(" ass ", " xss "), ENCODERS, "filter ass"),
    (FILTERS, ENCODERS.replace("libopenh264", "libx264"), "encoder libopenh264"),
    (FILTERS, ENCODERS.replace(" aac ", " aac_mf "), "encoder aac"),
])
def test_builds_missing_a_required_feature_are_rejected(tmp_path, filters, encoders, missing):
    with pytest.raises(FFmpegPolicyError, match=missing):
        policy.inspect(_fake_bin(tmp_path), _runner(filters=filters, encoders=encoders))


def test_a_build_whose_configuration_cannot_be_read_is_rejected(tmp_path):
    with pytest.raises(FFmpegPolicyError, match="could not be verified"):
        policy.inspect(_fake_bin(tmp_path), lambda args: "ffmpeg version ???\n")


def test_missing_binaries_are_rejected(tmp_path):
    with pytest.raises(FFmpegPolicyError, match="not found"):
        policy.inspect(tmp_path, _runner())


def test_resolve_reports_every_rejected_candidate_and_never_downloads(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNORA_FFMPEG_DIR", str(_fake_bin(tmp_path)))
    monkeypatch.setattr(policy, "DEFAULT_DIR", tmp_path / "absent")
    monkeypatch.setattr(policy.shutil, "which", lambda name: None)
    with pytest.raises(FFmpegPolicyError, match="No approved FFmpeg found") as exc:
        policy.resolve(_runner(config=f"{LGPL_CONFIG} --enable-gpl"))
    assert "GPL/non-free" in str(exc.value) and "absent" in str(exc.value)


def test_the_configured_directory_is_preferred(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNORA_FFMPEG_DIR", str(_fake_bin(tmp_path)))
    assert policy.resolve(_runner()).ffmpeg.parent == tmp_path


# -- the real binaries on this machine --------------------------------------------------------


def test_the_installed_approved_build_really_is_lgpl_only(approved_tools):
    flags = approved_tools.configuration.split()
    assert "--enable-gpl" not in flags and "--enable-nonfree" not in flags
    assert "--enable-libass" in flags and "--enable-libopenh264" in flags


def test_a_real_gpl_ffmpeg_on_path_is_rejected():
    on_path = shutil.which("ffmpeg")
    if not on_path:
        pytest.skip("no ffmpeg on PATH")
    try:
        tools = policy.inspect(Path(on_path).parent)
    except FFmpegPolicyError as exc:
        assert "GPL" in str(exc) or "missing" in str(exc)
    else:
        pytest.skip(f"the ffmpeg on PATH is itself an approved build: {tools.version}")
