import re

import pytest

from app.storage.filenames import ALLOWED_EXTENSIONS, safe_audio_filename

SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(mp3|wav|flac|ogg|opus|aac)$")


def name(raw, job_id="tunora-abc", media_type="audio/mpeg"):
    return safe_audio_filename(raw, job_id=job_id, media_type=media_type)


def test_a_normal_tunora_filename_is_unchanged():
    assert name("tunora-abc.mp3") == "tunora-abc.mp3"
    assert name("tunora-8f0e1c2a-1111-2222-3333-444455556666.wav", media_type="audio/wav") == (
        "tunora-8f0e1c2a-1111-2222-3333-444455556666.wav"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "../../secret.mp3",
        "..\\..\\secret.mp3",
        "a/b/c/song.mp3",
        "C:\\Windows\\win.ini.mp3",
        "/etc/passwd.mp3",
        "\\\\server\\share\\x.mp3",
        "song\r\nSet-Cookie: x=1.mp3",
        "song\rinjected.mp3",
        "song\ninjected.mp3",
        'song"; filename="evil.exe.mp3',
        "..mp3",
        "....mp3",
        ".mp3",
        "song\x00.mp3",
        "sóng ✓ 歌.mp3",
        "a" * 500 + ".mp3",
        "",
        None,
        123,
    ],
)
def test_unsafe_names_become_safe_deterministic_names(raw):
    result = name(raw)
    assert SAFE.match(result), result
    assert len(result) <= 110
    assert "/" not in result and "\\" not in result and ".." not in result
    assert not re.search(r"[\x00-\x1f\x7f\"';:]", result)
    assert name(raw) == result  # deterministic


def test_traversal_keeps_only_the_basename():
    assert name("../../secret.mp3") == "secret.mp3"
    assert name("..\\..\\secret.mp3") == "secret.mp3"


def test_empty_or_unusable_falls_back_to_the_job_id():
    assert name("") == "tunora-tunora-abc.mp3"
    assert name(None, job_id="job-1") == "tunora-job-1.mp3"
    assert name("...", job_id="job-1") == "tunora-job-1.mp3"
    assert name("___", job_id="job-1") == "tunora-job-1.mp3"


def test_a_disallowed_extension_is_replaced_from_the_media_type():
    assert name("song.exe", media_type="audio/wav") == "song.exe.wav"
    assert name("song.html", media_type="audio/flac") == "song.html.flac"
    assert name("song.mp3.exe", media_type="audio/mpeg") == "song.mp3.exe.mp3"
    assert name("noextension", media_type="audio/ogg") == "noextension.ogg"


def test_extension_is_lowercased_and_always_allowed():
    assert name("SONG.MP3") == "SONG.mp3"
    for raw in ("a.mp3", "b.WAV", "c.exe", "d", "e.svg"):
        assert "." + name(raw).rsplit(".", 1)[1] in ALLOWED_EXTENSIONS


def test_an_unusual_job_id_cannot_smuggle_characters_into_the_fallback():
    result = name("", job_id="../../x\r\ny")
    assert SAFE.match(result), result
