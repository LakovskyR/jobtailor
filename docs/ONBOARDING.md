# Onboarding — from your documents to a structured profile

jobtailor runs entirely off a structured profile (`config/experience-library.yaml`) plus an optional
voice profile (`config/style-profile.yaml`). Power users can hand-write those YAMLs — but most people
shouldn't have to. **Onboarding builds them automatically from documents the user already has.**

This does **not** change the engine. The engine stays person-agnostic; onboarding just fills its
inputs. The same `ingest_profile` module powers both a CLI wizard (now) and a web form (later).

## Flow

```
Intake form        →  target roles, locations, contract type, languages   ──┐
Upload CV (req.)   →  extract roles, achievements, skills, education       ──┤→ experience-library.yaml
Upload CL (opt.)   →  extract voice: register, tone, phrasing, sign-off    ──┘→ style-profile.yaml
        │
        ▼
   REVIEW & EDIT  ── the user confirms/corrects the extracted profile  (mandatory gate)
        │
        ▼
   existing engine:  parse offer → tailor CV + cover letter → ATS score
```

## What gets extracted

| Source | → Output file | Fields |
|---|---|---|
| **CV** (PDF/DOCX/text) | `config/experience-library.yaml` | person/contact, roles (company, title, dates), achievements **with metrics + tags**, hard + soft skills, education, certifications, languages |
| **Cover letter** (optional) | `config/style-profile.yaml` | register, person, tone, sentence length, salutation, sign-off, signature phrases, anti-patterns |
| **Intake form** | `targeting:` block of the library | titles, locations, seniority, keyword boosts |

Both output files follow the committed `*.example.yaml` schemas and are **gitignored** — the user's
real profile never enters the repo.

## Two non-negotiables

1. **Human-in-the-loop review.** LLM extraction from a CV PDF *will* mis-parse (multi-column layouts,
   tables). `ingest_profile` must present the drafted library for confirmation/edit **before** writing.
   The engine's core rule is *never invent experience* — extraction only proposes; the user approves.
2. **Privacy.** Uploaded CV/CL are the user's own PII. They are read in place or copied only into the
   gitignored `private/` directory, processed via the user's own `OPENAI_API_KEY`, and never written
   to a committed path or logged.

## Surfaces

- **v1 — CLI wizard (build first):** `python src/python/ingest_profile.py --cv mycv.pdf --cl mycl.pdf`
  → asks the intake questions → drafts the YAMLs → opens them for review → saves.
- **v2 — web form (later):** a thin Streamlit/web layer wrapping the same module, for a polished demo.

See `CODEX_BUILD.md` task **P-0** for the build spec.
