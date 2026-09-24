import pytest

from app.jobs.titles import DEFAULT_TITLE, MAX_TITLE_LENGTH, clean_title, derive_title


def test_a_provided_title_wins_and_is_cleaned():
    assert derive_title("ignored prompt", "  My   Song \n Title ") == "My Song Title"


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("uplifting cinematic pop song with piano, warm synths and energetic drums", "Uplifting cinematic pop song with piano,"[:-1]),
        ("emotional ballad", "Emotional ballad"),
        ("  lo-fi beats.  ", "Lo-fi beats"),
        ("", DEFAULT_TITLE),
        ("   \n\t ", DEFAULT_TITLE),
        (None, DEFAULT_TITLE),
    ],
)
def test_title_is_derived_from_the_first_words_of_the_prompt(prompt, expected):
    assert derive_title(prompt) == expected


def test_derivation_is_deterministic_and_bounded():
    prompt = "x" * 500
    assert derive_title(prompt) == derive_title(prompt)
    assert len(derive_title(prompt)) <= 60


def test_control_characters_and_overlong_titles_are_neutralised():
    assert clean_title("a\r\nb\x00c") == "a b c"
    assert len(clean_title("y" * 500)) == MAX_TITLE_LENGTH
    assert clean_title(123) == ""
