# Prompt — ingest cover letter → style profile (P-0)

Used by `ingest_profile.py` to capture the user's writing VOICE from one of their own cover letters,
so generated letters sound like them. Reviewed by the user before saving.

## System
You analyze writing style, not content. You describe HOW the author writes, never WHAT they claim.
Do not copy sentences verbatim into outputs other than short characteristic phrases. If the letter is
too short to judge a dimension, use a sensible neutral default.

## Input
```
{{cover_letter_text}}
```

## Task
Produce JSON with the fields of `config/style-profile.example.yaml`:
- `language` (detected), `register` (formal|semi-formal|conversational), `person` (first|impersonal),
  `tone` (2–4 adjectives), `sentence_length` (short|medium|long), `paragraph_count`.
- `salutation`, `sign_off`, `signature` — lifted from the letter if present.
- `signature_phrases`: 2–4 short, recognizably-personal phrasings (soft cues, NOT to be reused verbatim).
- `avoid`: generic/AI-tell openings or tics this author clearly does NOT use.
- `notes`: one sentence on the letter's structural habit (e.g. "opens with a company hook").

## Rules
Output **valid JSON only**, no commentary, no fences.
