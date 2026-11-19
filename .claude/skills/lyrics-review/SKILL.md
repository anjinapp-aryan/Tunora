---
name: lyrics-review
description: Review or revise song lyrics for an ACE-Step generation in Tunora — structure tags, singability, rhyme and prosody, length for the duration, and pronunciation risks, including Kannada, Hindi, Tamil and Telugu lyrics (aksharas, script, romanization). Use when the user asks to review, fix, tighten or check lyrics before generating, or when lyrics come out mis-sung.
argument-hint: "[lyrics text, a file, or a song/version id] [language] [duration]"
---

Lyrics to review: `$ARGUMENTS`. Adapted (CC0) from bitwize-music-studio/claude-ai-music-skills
(`lyric-reviewer`, `lyric-writer`, `pronunciation-specialist`, `voice-checker`), rewritten for ACE-Step
1.5 and Tunora. The record of what was adopted, and why, is `docs/MUSIC-SKILLS-ADOPTION.md`.

## 1. Run the deterministic check first (do not re-derive what it measures)

Tunora's checker is the source of truth for counts and structure: `backend/app/lyrics_check/checker.py`.
- API (backend running): `POST /api/lyrics/check` `{"lyrics": "...", "language": "kn", "duration_seconds": 120}`.
- Offline: `cd backend && uv run python -c "from app.lyrics_check import check_lyrics; r = check_lyrics(open('f.txt', encoding='utf-8').read(), 'kn', duration_seconds=120); print(r.status, [(f.code, f.line, f.message) for f in r.findings])"` (set `PYTHONIOENCODING=utf-8` on Windows).

It reports: tags (unbalanced, stacked, inline, empty sections, none at all), length for the duration,
per-line units (syllables / **aksharas** / characters) and outliers within a section, script versus
language, romanized Indic lyrics, languages that are not in ACE-Step's trained list (Kannada `kn` is
not), digits, acronyms, English homographs, archaic Kannada letters (ಱ, ೞ) and explicit words.

## 2. Then review what a program can't (craft checklist)

1. **Structure** — ACE-Step reads tags as its "temporal script" (`ACE-Step-1.5/docs/en/Tutorial.md`). Use
   `[Intro] [Verse] [Pre-Chorus] [Chorus] [Bridge] [Outro]`, with at most one modifier (`[Chorus - anthemic]`).
   Style belongs in the description (caption), not in tags.
2. **Hook** — the chorus states the title or central image in its first or last line; it is repeated
   word for word each time (ACE-Step sings repeats more consistently than variations).
3. **Prosody** — stressed syllables land on strong beats; similar line lengths within a section (the
   checker's outliers are the place to start); no line the singer must rush.
4. **Rhyme** — consistent scheme per section; prefer near rhymes to forced word order; avoid the same
   rhyme sound in back-to-back sections.
5. **Imagery over abstraction** — concrete nouns and actions; cut stacked abstract nouns ("echoes of
   eternal dreams"), explained metaphors and cliché escalation (AI-written tells from `voice-checker`).
6. **Length** — about 2–4 sung syllables per second while singing; leave instrumental room for
   intros and breaks.

## 3. Indian-language lyrics

- Write in the language's own script unless the user wants romanized lyrics; the checker flags Latin-
  script lyrics under kn/hi/ta/te because the singer may then apply English spelling sounds.
- Count **aksharas**, not words: Kannada and Tamil words are long and agglutinative, so word counts mislead.
  `ಕನ್ನಡ` = 3, `ಬೆಂಗಳೂರು` = 4. The counts are orthographic: Hindi schwa deletion (`तमिल` written 3,
  sung "ta-mil") means sung syllables can be fewer.
- Kannada: modern letters only (ರ not ಱ, ಳ not ೞ); keep conjuncts intact; avoid English loanwords in
  Latin letters inside Kannada lines (one script per line).
- **ACE-Step does not list Kannada (`kn`) among its trained vocal languages** (`acestep/constants.py`);
  hi/ta/te are listed. Never promise Kannada pronunciation quality. Suggest a short test generation and
  human listening, and keep difficult words simple and common.

## 4. Pronunciation fixes (when a word comes out wrong)

Respell phonetically in the lyrics only (never in the stored title); write numbers as words in the song's
language; write acronyms as they should sound (`D. J.`, `Dee Jay`); for English homographs pick the
spelling that forces one reading (`reed`/`red`). Verify by listening — nothing in Tunora can confirm it.

## Output

A short findings list (checker findings first, then craft notes, each with its line number), then the
revised lyrics if the user asked for changes. Keep the user's language, meaning and voice; never translate
unless asked. Do not change a stored Version (Versions are immutable); revised lyrics go into Create or
Revise as a new Version.
