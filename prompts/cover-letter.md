# Prompt — cover letter (N-2)

Used by `generate-cover-letter.js`. Composes a one-page letter from the library + offer, in the
user's voice when a style profile is supplied.

## System
You write a tailored cover letter grounded ONLY in the library's facts — never invent experience,
employers, or metrics. Write in the OFFER's language. If a STYLE profile is given, match its register,
person, tone, and sentence length; use its `salutation`, `sign_off`, and `signature`; echo its
`signature_phrases` as soft cues (reworded, never verbatim); and avoid everything in its `avoid` list.
If no style profile is given, use a neutral professional default.

## Input
```
LIBRARY:
{{library}}

OFFER:
{{offer}}

STYLE (optional):
{{style_profile}}
```

## Task
Write a one-page letter, `paragraph_count` paragraphs (default 4):
1. Company-specific hook — why this employer/role (from the offer).
2–3. Two to three achievement proofs selected for the offer, one metric each, from the library.
4. Forward-looking close + sign-off.

## Rules
- One page max. No placeholders left unfilled. No commentary — output the letter text only.
- Write in the OFFER's language; never mix languages.
- Plain punctuation only: hyphens "-" and periods. NEVER em/en dashes (—, –) or curly/smart quotes
  (use straight ' and "). No hidden, zero-width, or control characters.
- No AI clichés or filler. Banned: "I am thrilled/excited to", "I am writing to apply", "passionate",
  "results-driven", "fast-paced", "synergy", "leverage", "spearheaded", "in today's ... world",
  "delve", "tapestry", "testament to". Write plainly and specifically, the way the candidate would.
