# Contributing to jobtailor

Thanks for your interest! jobtailor is a small, practical tool — contributions that keep it simple,
deterministic where possible, and privacy-first are very welcome.

## Setup
```bash
npm install
pip install -r requirements.txt
pip install pytest
cp config/experience-library.example.yaml config/experience-library.yaml   # gitignored
cp .env.example .env                                                        # add OPENAI_API_KEY
pytest -q
```

## The one rule that matters: never commit personal data
The engine is person-agnostic. Real profiles, CVs, exports, and outputs are **gitignored**
(`config/*.yaml` except `*.example.yaml`, `private/`, `output/`, `*.pdf/.docx/.zip/.csv`). Test and
develop against `config/experience-library.example.yaml` and `jobs/sample-offer.json` only.

## Picking work
The roadmap lives in [`CODEX_BUILD.md`](CODEX_BUILD.md) and in the GitHub issues (tasks `P-1…P-5`,
`N-1`, `N-2`). Each task is self-contained with success criteria. Comment on an issue to claim it.

## Conventions
- Deterministic code (parsing, scoring, rendering, IO) over LLM calls; the OpenAI API is used only to
  rank and rephrase a user's real achievements — never to invent experience.
- Add a test under `tests/` for any deterministic logic you add. CI runs `pytest`.
- Keep the public/private split intact.
