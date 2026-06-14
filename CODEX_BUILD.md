# Codex build plan — jobtailor

The scaffold (structure, configs, interfaces, the ATS scorer, and the sample offer source) is done.
Hand these tasks to Codex one at a time. Each is self-contained and has clear success criteria.
Keep the public/private split: never read or commit anything under `private/`, `config/*.yaml`
(non-example), or `output/`. The engine reads the library only through the loader that falls back to
the `.example.yaml`.

---

## P-0 — `ingest_profile.py` (onboarding: documents → profile)  **[BUILD FIRST, after P-3]**
Turn a new user's existing documents into the structured inputs the engine reads, so they never
hand-author YAML. CLI wizard first; a web form can wrap the same module later. See `docs/ONBOARDING.md`.

Inputs:
- `--cv <path>` (required): PDF/DOCX/text CV. Extract text (pdfminer.six / python-docx / plain).
- `--cl <path>` (optional): a cover letter, used ONLY for style extraction.
- interactive intake prompts (or `--targeting <yaml>`): target titles, locations, contract types, languages.

Steps:
1. Extract CV text → LLM (P-3 shim) → draft `experience-library.yaml` matching
   `config/experience-library.example.yaml` (person, roles+achievements with metrics+tags,
   skills.technical/business, education, certifications, languages, and the `targeting:` block from intake).
2. If `--cl` given → LLM → `style-profile.yaml` matching `config/style-profile.example.yaml`.
3. **REVIEW GATE (mandatory):** print the drafted library as readable YAML and require explicit
   confirmation (or open `$EDITOR`) before writing. The engine must never invent experience —
   extraction proposes, the user approves.
4. Write `config/experience-library.yaml` + `config/style-profile.yaml` (both gitignored).
   Never overwrite an existing `config/*.yaml` without `--force`.

Privacy: uploaded files are the user's own PII — read in place or copy ONLY into the gitignored
`private/` dir; never under a committed path; never log their content.

**Done when:** `python src/python/ingest_profile.py --cv tests/fixtures/sample-cv.txt` produces a
valid `experience-library.yaml` that validates against the example schema, after a review prompt.

## P-1 — `parse_offer.py` (URL/text → structured JSON)
Implement `fetch_text` (requests + BeautifulSoup, strip to readable text) and `extract_fields`
(detect language; pull title, company, must_have, nice_to_have, keywords). Do a deterministic
keyword/section pass first; optionally refine with the LLM provider from `.env`. Output must match the
schema in the module docstring and validate against `jobs/sample-offer.json`.
**Done when:** `python src/python/parse_offer.py --text "<paste an offer>"` prints valid JSON.

## N-1 — `generate-cv.js` (tailored CV .docx)
Implement `rankAchievements` and docx rendering with `docx`. Rank achievements per role by overlap
with `offer.must_have + offer.keywords`, keep `settings.cv.achievements_per_role`, render the sections
from `settings.cv.sections` in the chosen language (use `pickLang`), keep to `max_pages`. Never invent
experience — only select and rephrase from the library.
**Done when:** `node src/node/generate-cv.js --lang en --offer jobs/sample-offer.json --out output/cv/CV_EN.docx` writes a valid 1–2 page docx, and `ats_scorer.py` on it scores ≥ 0.7 against the sample offer.

## N-2 — `generate-cover-letter.js`
Compose a tailored letter from `library + offer + optional style-profile` (intro hook tied to the
company, 2–3 achievement proofs selected for the offer, close). Language follows the offer. If
`config/style-profile.yaml` exists, honor its register/person/tone/sentence_length, use its
`salutation`/`sign_off`/`signature`, lean on `signature_phrases` as soft cues (never verbatim), and
steer clear of everything in `avoid`; otherwise fall back to a neutral professional default. Output to
`output/cover-letters/`. Provider from `.env`.
**Done when:** produces a coherent one-page letter grounded only in library facts, and — when a style
profile is present — visibly matches its register and sign-off.

## P-2 — `bilingual_audit.py`
Diff two language CV texts (or two library renders): report roles/claims present in one language but
missing in the other, and metric mismatches.
**Done when:** prints a clear diff; exit 1 if inconsistencies found.

## P-3 — OpenAI shim (`src/python/llm.py` + `src/node/llm.js`)
One thin function `complete(system, user) -> str` that calls the OpenAI API using `OPENAI_API_KEY` /
`OPENAI_MODEL` from `.env`. Used by P-1, N-1, N-2. Keep it a single seam so a provider can be swapped
later, but ship OpenAI only.

## P-4 — `find_offers.py` ranking + real source (France Travail)
Implement `rank` (score offers vs library `targeting`: title match, `keywords_boost`, location) and add
a real adapter under `src/python/sources/`. Keep the `sample` source working. NO LinkedIn scraping.

PRIMARY adapter — **France Travail** (`sources/france_travail.py`), best for the FR market, free:
- OAuth2 `client_credentials`. Env: `FRANCE_TRAVAIL_CLIENT_ID` / `FRANCE_TRAVAIL_CLIENT_SECRET`
  (add both to `.env.example`).
- Token endpoint + "Offres d'emploi v2" search endpoint + the required scope per francetravail.io —
  **VERIFY the exact URLs/scope against the live docs at https://francetravail.io** before coding;
  do not hardcode stale values. Handle token expiry/refresh.
- Map each result to the SAME offer dict the `sample` source emits; respect `find_offers.max_results`.
- Add `"france_travail"` as an option in settings `find_offers.enabled_sources`.

ALTERNATIVE (document now, build later) — **Adzuna**: multi-country REST API, simple `app_id`/`app_key`,
useful for testing outside France. Create `sources/adzuna.py` as a STUB only: a docstring describing the
endpoint, the env var names (`ADZUNA_APP_ID` / `ADZUNA_APP_KEY`), a link to https://developer.adzuna.com,
and a `NotImplementedError`. Leave the implementation for a later sprint.

**Done when:** `python src/python/find_offers.py` returns a ranked list from `sample`, and the France
Travail adapter returns live ranked offers when its keys are set.

## P-5 — prompts/
Write the LLM prompt templates used by the tailor/letter steps into `prompts/` (tailor-cv.md,
cover-letter.md, parse-offer.md). De-personalized; reference the library by field, not by name.

## Tests
Add `tests/` with: a parse_offer fixture, an ats_scorer unit test (already deterministic), and a
generate-cv smoke test against `experience-library.example.yaml` + `jobs/sample-offer.json`.

---

## UI-1 — `app.py` (Streamlit) — the friendly surface for non-technical users
A single-screen web UI over the existing engine so a non-technical job seeker never touches the CLI.
Hostable on Streamlit Community Cloud / HF Spaces; also runs locally. Add `streamlit` to requirements.txt.
Refactor the module cores into importable functions if needed, keeping the existing CLIs working.

Flow on one page:
1. **Profile** — upload CV (PDF/DOCX) + optional cover letter → call `ingest_profile` to draft the
   library + style profile → show them in editable fields. The review gate becomes a "Looks right?"
   confirm. Hosted: keep in session. Local: offer to save to `config/*.yaml` (with consent).
2. **Provider** — radio: "I have an OpenAI key" (text input, session-only, never written server-side)
   OR "Use a free model" (default → server's `OPENAI_BASE_URL`/key, e.g. Groq). Inject the chosen
   key/base/model into the env the shim reads, per request.
3. **Offer** — a URL field AND a text area. Try `parse_offer` on the URL; if the fetch fails or looks
   like a login wall (LinkedIn/Indeed often do), show "couldn't read that page — paste the description
   below" and use the text area. Pasted text is the guaranteed path.
4. **Generate** — run generate-cv + generate-cover-letter + ats_scorer. Show the ATS score + gap list
   prominently. Provide **Download** buttons for both .docx; in LOCAL mode also accept an output-folder
   path (default `settings.output` dirs), the way worksearch2 saved files.
5. Show a short privacy note: uploads and keys stay in the session; nothing is committed.

**Done when:** `streamlit run app.py` walks upload → provider → paste offer text → tailored CV +
cover letter + ATS score + downloads, working with a FREE model and no OpenAI key.

---

## Round 2 — UX & generation quality (requested 2026-06-14)

### P-1b — LinkedIn/Indeed URL ingestion (port worksearch2's proven pattern)
worksearch2 parsed pasted job URLs reliably; copy that approach into parse_offer.py:
- Multi-strategy fetch, pick the best result by content length + metadata: (a) **basic** =
  requests + BeautifulSoup (default, free); (b) optional **Firecrawl** (FIRECRAWL_API_KEY) for
  JS-heavy/blocked pages — only used if the key is set. Try basic first.
- LinkedIn public pages: read `og:title`/`og:description` meta + these selectors in order:
  `.description__text`, `.show-more-less-html__markup`, `div.description`, `article`, `main`,
  `.job-description`, `#job-description`; else the longest `<div>` text.
- Parse LinkedIn title formats into company/role: `"{company} hiring {role}"`,
  `"{company} is hiring {role}"`, `"{company} recrute {role}"`; also split on " | ", " - ", " @ ".
- Repair mojibake on fetched text (â€™→', Ã©→é, …) before parsing.
- ALWAYS graceful: if no text is extracted, return a clear "couldn't read that page — paste the
  description text instead" signal the UI can show. Pasted text stays the guaranteed path.
- Add `FIRECRAWL_API_KEY=` (optional) to .env.example.

### N-3 — Generation quality hardening (generate-cv.js + generate-cover-letter.js)
Add `src/node/sanitize.js` exporting `clean(text)`, run on ALL generated text before writing .docx:
- Strip zero-width / non-printing chars: U+200B–U+200D, U+FEFF, U+00AD, U+2060, and C0/C1 controls.
- Replace em/en dashes (—, –) with " - "; curly quotes (' ' " " ‚ „) with straight ' and ";
  ellipsis … with "..."; collapse repeated whitespace.
- Output language must equal `offer.language` (already wired via `lang`) — never mix languages.
The anti-cliché wording is enforced by the updated prompts/. Add a `clean()` unit test.

### UI-1 (expanded) — make every choice intuitive
In addition to the base UI-1 flow:
- **Model choice:** a dropdown of presets — "OpenAI (your key)", "Groq – free", "OpenRouter – free",
  "Custom (base URL + model)" — that sets OPENAI_BASE_URL/OPENAI_MODEL, with a help tooltip per option.
- **Uploads:** labelled drag-drop for "Your CV" (required) and "A past cover letter (optional, for
  style)"; show the parsed result inline for the review gate.
- **Strength interview:** after extraction, call the LLM with `prompts/strength-interview.md` to get
  2-3 follow-up questions; collect answers and merge into the library before generating. Skippable.
- **Output folder:** a folder-path input (default `settings.output` dirs) so the user picks where files
  save, like worksearch2 did; Download buttons as fallback (and the only option when hosted).

### DIST-1 — one-click launch (no terminal expertise required)
A non-technical user should run the app by double-clicking after downloading the repo ZIP:
- Add `run.bat` (Windows), `run.command` (macOS), `run.sh` (Linux) that ensure a venv +
  `pip install -r requirements.txt` on first run, then `streamlit run app.py` and open the browser.
- Prefer bootstrapping via **uv** when present (`uv run streamlit run app.py` handles Python + deps
  fast); fall back to stdlib `venv` otherwise.
- Do NOT build a PyInstaller single-exe — Streamlit bundling is unreliable.
- README "Getting started (no terminal)" (Gemini's task): install Python (one link) → GitHub green
  "Code" → Download ZIP → unzip → double-click run.bat.

---

## Round 3 — final UX: auto-save, theme, bilingual (locked via mockup 2026-06-14)

### Output handling — REPLACES the Download buttons in UI-1
- On FIRST launch, prompt for an output folder via a native OS dialog (`tkinter.filedialog.askdirectory`,
  launched from the local process). Persist the choice to a gitignored local state file
  (`config/app-state.json`) so it is remembered; show it with a "Change folder" button.
- Auto-save BOTH .docx into `<folder>/<YYYY-MM-DD>/<Company-Role>/` (slugified), like worksearch2's
  date-foldered outputs; use the runtime date. NO download buttons.
- After generating, show "Saved to <path>" + an "Open folder" button (`os.startfile` on Windows,
  `open` on macOS, `xdg-open` on Linux).

### Provider + keys — Step 1, explicit
- Step 1 "AI model": provider dropdown (OpenAI / Groq-free / OpenRouter-free / Custom) + a single
  API-key field whose meaning follows the provider + a "get a free key" link for the free options.
  Optional "remember on this computer" → write to `.env` (gitignored); else session-only.
- Firecrawl key: OPTIONAL, inside an `st.expander("Advanced")` by the job step. Not required.

### Visual theme — reuse the bet project's look (dark, warm accents)
Inject via `st.markdown(<style>, unsafe_allow_html=True)` AND ship `.streamlit/config.toml`.
- Fonts: Space Grotesk (headings) + IBM Plex Sans (body), from Google Fonts.
- CSS vars (from bet): `--bg-main:#0f1714; --bg-accent:#d67a31; --bg-accent-alt:#79a88f;
  --text-main:#f4efe7; --text-muted:#c7c0b4; --border-soft:rgba(244,239,231,0.09);`
- `.stApp` background:
  `radial-gradient(circle at 12% 12%, rgba(214,122,49,0.18), transparent 30%),
   radial-gradient(circle at 86% 10%, rgba(121,168,143,0.16), transparent 28%),
   linear-gradient(180deg,#09100d 0%,#0f1714 48%,#131b17 100%);`
- Cards/metrics: translucent white gradient, `1px var(--border-soft)`, border-radius 20-22px, soft shadow.
- Pills: border-radius 999px, uppercase letter-spaced, coral-tinted. Primary button = coral accent,
  rounded, hover lightens. Matched chips = sage/green; missing chips = coral/red.
- `.streamlit/config.toml`: `[theme] base="dark" primaryColor="#d67a31" backgroundColor="#0f1714"
  secondaryBackgroundColor="#15231d" textColor="#f4efe7"`.

### Bilingual UI — English / French, DEFAULT FRENCH
- Language toggle (FR | EN) in the header; default `"fr"`. Persist in session + `app-state.json`.
- Put ALL interface strings in `src/python/i18n.py` as `STRINGS = {"fr": {...}, "en": {...}}`; wrap every
  label/button/help via a `t(key)` helper.
- IMPORTANT: this is the UI CHROME language only. The generated CV/cover-letter language still follows
  the OFFER (unchanged) — keep them independent, and say so in a one-line UI note.
