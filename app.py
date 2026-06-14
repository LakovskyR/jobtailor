from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from html import escape
from copy import deepcopy
from datetime import date
from io import BytesIO
from pathlib import Path

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parent
APP_STATE_PATH = ROOT / "config" / "app-state.json"
LIBRARY_PATH = ROOT / "config" / "experience-library.yaml"
PROMPTS = ROOT / "prompts"
PY_SRC = ROOT / "src" / "python"
if str(PY_SRC) not in sys.path:
    sys.path.insert(0, str(PY_SRC))

import ingest_profile  # noqa: E402
import ats_scorer  # noqa: E402
import parse_offer  # noqa: E402
from llm import complete  # noqa: E402
from i18n import t, DEFAULT_LANG  # noqa: E402

JOBTAILOR_ISSUES_URL = "https://github.com/LakovskyR/jobtailor/issues"
JOBTAILOR_COFFEE_URL = "https://buymeacoffee.com/lakovskyr"


MODEL_PRESETS = {
    "Groq (free key)": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "help": "Free. Get a key in two minutes and paste it below.",
        "key_url": "https://console.groq.com/keys",
    },
    "OpenAI (your key)": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "help": "Use your OpenAI API key.",
        "key_url": "https://platform.openai.com/api-keys",
    },
    "Groq - free": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "help": "Use a Groq key with their OpenAI-compatible endpoint.",
        "key_url": "https://console.groq.com/keys",
    },
    "OpenRouter - free": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.1-8b-instruct:free",
        "help": "Use an OpenRouter key and a free model.",
        "key_url": "https://openrouter.ai/keys",
    },
    "Custom (base URL + model)": {
        "base_url": "",
        "model": "",
        "help": "Use any OpenAI-compatible provider.",
        "key_url": "",
    },
}


def T(key: str, **kwargs: object) -> str:
    return t(key, st.session_state.get("ui_lang", DEFAULT_LANG), **kwargs)


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

        :root {
            --bg-main: #0f1714;
            --bg-accent: #d67a31;
            --bg-accent-alt: #79a88f;
            --text-main: #f4efe7;
            --text-muted: #c7c0b4;
            --border-soft: rgba(244, 239, 231, 0.09);
            --shadow-strong: 0 24px 60px rgba(0, 0, 0, 0.34);
        }

        html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }

        .stApp {
            background:
                radial-gradient(circle at 12% 12%, rgba(214, 122, 49, 0.18), transparent 30%),
                radial-gradient(circle at 86% 10%, rgba(121, 168, 143, 0.16), transparent 28%),
                linear-gradient(180deg, #09100d 0%, #0f1714 48%, #131b17 100%);
            color: var(--text-main);
        }

        .block-container { max-width: 1180px; padding-top: 1.4rem; padding-bottom: 2.5rem; }

        h1, h2, h3, h4, h5, h6 { font-family: 'Space Grotesk', sans-serif; color: var(--text-main); }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(20, 31, 27, 0.98), rgba(11, 17, 15, 0.98)) !important;
            border-right: 1px solid rgba(255, 255, 255, 0.06);
        }

        [data-testid="stMetric"],
        div[data-testid="stExpander"],
        div[data-testid="stForm"],
        div[data-testid="stFileUploader"] section {
            background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015));
            border: 1px solid var(--border-soft);
            border-radius: 20px;
            box-shadow: 0 14px 30px rgba(0, 0, 0, 0.18);
        }

        [data-testid="baseButton-primary"] {
            background: linear-gradient(135deg, #cb6b29 0%, #e79a4e 100%) !important;
            border: none !important;
            border-radius: 14px !important;
            color: #1c130c !important;
            font-weight: 700 !important;
        }
        [data-testid="baseButton-primary"]:hover { filter: brightness(1.08); transform: translateY(-1px); }
        [data-testid="baseButton-secondary"] { border-radius: 14px !important; border-color: rgba(244, 239, 231, 0.16) !important; }

        .jt-card {
            background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015));
            border: 1px solid var(--border-soft);
            border-radius: 22px;
            padding: 1rem 1.1rem;
            box-shadow: var(--shadow-strong);
        }
        .jt-chip {
            display: inline-flex; align-items: center; margin: 0.2rem 0.3rem 0.2rem 0;
            padding: 0.38rem 0.7rem; border-radius: 999px; font-size: 0.78rem; font-weight: 700;
            letter-spacing: 0.05em; text-transform: uppercase; border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .jt-chip-match { color: #dff6e8; background: rgba(121, 168, 143, 0.22); border-color: rgba(121, 168, 143, 0.44); }
        .jt-chip-missing { color: #ffe1d1; background: rgba(214, 122, 49, 0.2); border-color: rgba(214, 122, 49, 0.46); }
        .jt-footer { margin-top: 2.4rem; padding-top: 1rem; border-top: 1px solid var(--border-soft); color: var(--text-muted); }
        </style>
        """,
        unsafe_allow_html=True,
    )


def read_upload_text(uploaded) -> str:
    data = uploaded.getvalue()
    suffix = Path(uploaded.name).suffix.lower()
    if suffix == ".pdf":
        import pdfplumber

        with pdfplumber.open(BytesIO(data)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
    if suffix == ".docx":
        from docx import Document

        doc = Document(BytesIO(data))
        return "\n".join(par.text for par in doc.paragraphs).strip()
    return data.decode("utf-8", errors="replace").strip()


def load_settings() -> dict:
    for name in ["settings.yaml", "settings.example.yaml"]:
        path = ROOT / "config" / name
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def load_app_state() -> dict:
    if not APP_STATE_PATH.exists():
        return {}
    try:
        return json.loads(APP_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_app_state(state: dict) -> None:
    APP_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_persisted_library() -> dict | None:
    if not LIBRARY_PATH.exists():
        return None
    try:
        return yaml.safe_load(LIBRARY_PATH.read_text(encoding="utf-8")) or None
    except Exception:  # noqa: BLE001
        return None


def save_library(library: dict) -> None:
    LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_PATH.write_text(yaml.safe_dump(library, allow_unicode=True, sort_keys=False), encoding="utf-8")


def remember_env(values: dict[str, str]) -> None:
    env_path = ROOT / ".env"
    existing: dict[str, str] = {}
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            if raw.strip() and not raw.strip().startswith("#") and "=" in raw:
                key, value = raw.split("=", 1)
                existing[key.strip()] = value.strip()
    existing.update({key: value for key, value in values.items() if value})
    lines = [f"{key}={value}" for key, value in existing.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def choose_output_folder(initial: Path) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(initialdir=str(initial), title=T("dialog_title"))
        root.destroy()
        return Path(selected) if selected else None
    except Exception as exc:  # noqa: BLE001
        st.info(T("dialog_unavailable", error=exc))
        return None


def open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def get_output_root(settings: dict, state: dict) -> Path:
    default_output = ROOT / settings.get("output", {}).get("cv_dir", "output/cv")
    saved = state.get("output_folder")
    if saved:
        return Path(saved)
    selected = choose_output_folder(default_output)
    output_root = selected or default_output
    state["output_folder"] = str(output_root)
    save_app_state(state)
    return output_root


def language_toggle(state: dict) -> str:
    labels = {"fr": "Français", "en": "English"}
    current = st.session_state.get("ui_lang", DEFAULT_LANG)
    choice = st.radio(
        "lang", list(labels), index=list(labels).index(current),
        format_func=lambda c: labels[c], horizontal=True, label_visibility="collapsed",
    )
    st.session_state["ui_lang"] = choice
    if state.get("ui_lang") != choice:
        state["ui_lang"] = choice
        save_app_state(state)
    return choice


def configure_provider() -> None:
    st.subheader(T("step_model"))
    label = st.selectbox("Provider", list(MODEL_PRESETS), help=T("provider_help"))
    preset = MODEL_PRESETS[label]
    key_link = f" [{T('get_key')}]({preset['key_url']})" if preset["key_url"] else ""
    st.caption(f"{preset['help']}{key_link}")
    api_key = st.text_input(T("api_key"), type="password", help=T("api_key_help"))
    base_url = preset["base_url"]
    model = preset["model"]
    if label == "Custom (base URL + model)":
        base_url = st.text_input(T("base_url"), value="", placeholder="https://api.example.com/v1")
        model = st.text_input(T("model"), value="", placeholder="provider/model-name")
    else:
        st.text_input(T("base_url"), value=base_url, disabled=True)
        st.text_input(T("model"), value=model, disabled=True)
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_BASE_URL"] = base_url
        os.environ["OPENAI_MODEL"] = model
    else:
        def _env(name: str) -> str:
            env_path = ROOT / ".env"
            if env_path.exists():
                for raw in env_path.read_text(encoding="utf-8").splitlines():
                    line = raw.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == name:
                            return v.strip().strip('"').strip("'")
            return ""
        remembered = _env("OPENAI_API_KEY")
        default_key = _env("DEFAULT_GROQ_API_KEY")
        if remembered:
            os.environ["OPENAI_API_KEY"] = remembered
            os.environ["OPENAI_BASE_URL"] = _env("OPENAI_BASE_URL") or base_url
            os.environ["OPENAI_MODEL"] = _env("OPENAI_MODEL") or model
        elif default_key:
            os.environ["OPENAI_API_KEY"] = default_key
            os.environ["OPENAI_BASE_URL"] = "https://api.groq.com/openai/v1"
            os.environ["OPENAI_MODEL"] = "llama-3.3-70b-versatile"
            st.caption(T("using_default_key"))
        else:
            os.environ["OPENAI_BASE_URL"] = base_url
            os.environ["OPENAI_MODEL"] = model
    c1, c2 = st.columns(2)
    with c1:
        if st.checkbox(T("remember")) and api_key:
            remember_env({"OPENAI_API_KEY": api_key, "OPENAI_BASE_URL": base_url, "OPENAI_MODEL": model})
            st.success(T("saved_env"))
    with c2:
        if st.button(T("test_connection")):
            try:
                complete("You are a connectivity test.", "Reply with the single word: OK")
                st.success(T("connection_ok"))
            except Exception as exc:  # noqa: BLE001
                st.error(T("connection_failed", error=exc))


def parse_offer_input(url: str, pasted_text: str) -> dict | None:
    if pasted_text.strip():
        return parse_offer.extract_fields(pasted_text.strip())
    if url.strip():
        result = parse_offer.parse_url(url.strip())
        if result.get("fallback_message"):
            st.warning(result["fallback_message"])
        return result
    return None


def resolve_library(cv_upload) -> dict | None:
    if cv_upload is not None:
        fid = f"{cv_upload.name}:{getattr(cv_upload, 'size', '')}"
        if st.session_state.get("cv_fid") != fid:
            with st.spinner(T("generating")):
                lib = ingest_profile.draft_library(read_upload_text(cv_upload), targeting={})
            st.session_state["cv_fid"] = fid
            st.session_state["library"] = lib
        return st.session_state.get("library")
    if "library" in st.session_state:
        return st.session_state["library"]
    persisted = load_persisted_library()
    if persisted:
        st.session_state["library"] = persisted
        return persisted
    return None


def answers_path(output_root: Path) -> Path:
    return Path(output_root) / "strength-answers.md"


def load_saved_answers(output_root: Path) -> dict[str, str]:
    p = answers_path(output_root)
    if not p.exists():
        return {}
    data: dict[str, str] = {}
    question = None
    buf: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if question is not None:
                data[question] = "\n".join(buf).strip()
            question = line[3:].strip()
            buf = []
        elif question is not None:
            buf.append(line)
    if question is not None:
        data[question] = "\n".join(buf).strip()
    return {k: v for k, v in data.items() if v}


def save_answers(output_root: Path, qa: dict[str, str]) -> None:
    merged = load_saved_answers(output_root)
    merged.update({q: a.strip() for q, a in qa.items() if a.strip()})
    p = answers_path(output_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n\n".join(f"## {q}\n{a}" for q, a in merged.items()), encoding="utf-8")


def ask_strength_questions(library: dict, offer: dict | None) -> list[str]:
    prompt = (PROMPTS / "strength-interview.md").read_text(encoding="utf-8").replace(
        "{{library}}", yaml.safe_dump(library, allow_unicode=True)
    )
    if offer:
        terms = ", ".join((offer.get("must_have") or []) + (offer.get("keywords") or []))
        if terms:
            prompt += f"\n\nTARGET OFFER keywords (favour questions that surface evidence for these): {terms}"
    system = prompt.split("## System", 1)[1].split("## Input", 1)[0].strip()
    try:
        raw = complete(system, prompt)
        questions = json.loads(parse_offer.strip_fences(raw))
        return [str(item) for item in questions if str(item).strip()][:3]
    except Exception as exc:  # noqa: BLE001
        st.info(T("strength_unavailable", error=exc))
        return []


def render_strength_sidebar(library: dict, offer: dict | None, output_root: Path) -> list[str]:
    saved = load_saved_answers(output_root)
    with st.sidebar:
        st.subheader(T("strength"))
        if st.button(T("get_questions")):
            st.session_state["strength_questions"] = ask_strength_questions(library, offer)
        new_answers: dict[str, str] = {}
        for index, question in enumerate(st.session_state.get("strength_questions", []), start=1):
            if question in saved:
                continue  # already answered in a previous session — don't ask again
            answer = st.text_area(question, key=f"sa_{index}", height=80)
            if answer.strip():
                new_answers[question] = answer.strip()
        if new_answers:
            save_answers(output_root, new_answers)
            saved.update(new_answers)
    return list(saved.values())


def merge_strength_answers(library: dict, answers: list[str], lang: str) -> dict:
    merged = deepcopy(library)
    cleaned = [answer.strip() for answer in answers if answer.strip()]
    if not cleaned:
        return merged
    roles = merged.setdefault("roles", [])
    if not roles:
        roles.append({"company": "", "title": {lang: "Additional strengths"}, "start": "", "end": "", "achievements": []})
    achievements = roles[0].setdefault("achievements", [])
    for answer in cleaned:
        achievements.append({"text": {lang: answer}, "tags": ["strength-interview"]})
    return merged


def edit_profile(library: dict) -> dict:
    edited = deepcopy(library)
    person = edited.setdefault("person", {})
    st.subheader(T("review_cv"))
    c1, c2 = st.columns(2)
    with c1:
        person["name"] = st.text_input(T("name"), value=str(person.get("name") or ""))
        person["location"] = st.text_input(T("location"), value=str(person.get("location") or ""))
    with c2:
        headline = person.get("headline") or {}
        if not isinstance(headline, dict):
            headline = {"en": str(headline)}
        headline["en"] = st.text_input(T("headline"), value=str(headline.get("en") or next(iter(headline.values()), "")))
        person["headline"] = headline
        person["email"] = st.text_input(T("email"), value=str(person.get("email") or ""))

    skills = edited.setdefault("skills", {})
    skills["technical"] = [item.strip() for item in st.text_area(
        T("skills_tech"), value=", ".join(skills.get("technical") or []), height=80,
    ).split(",") if item.strip()]
    skills["business"] = [item.strip() for item in st.text_area(
        T("skills_biz"), value=", ".join(skills.get("business") or []), height=80,
    ).split(",") if item.strip()]

    roles = edited.setdefault("roles", [])
    for role_index, role in enumerate(roles):
        with st.expander(T("role_n", n=role_index + 1, company=role.get("company") or T("company")), expanded=role_index == 0):
            role["company"] = st.text_input(T("company"), value=str(role.get("company") or ""), key=f"role_company_{role_index}")
            title = role.get("title") or {}
            if not isinstance(title, dict):
                title = {"en": str(title)}
            title["en"] = st.text_input(T("title"), value=str(title.get("en") or next(iter(title.values()), "")), key=f"role_title_{role_index}")
            role["title"] = title
            role["start"] = st.text_input(T("start"), value=str(role.get("start") or ""), key=f"role_start_{role_index}")
            role["end"] = st.text_input(T("end"), value=str(role.get("end") or ""), key=f"role_end_{role_index}")
            achievements = role.setdefault("achievements", [])
            for ach_index, achievement in enumerate(achievements):
                text = achievement.get("text") or {}
                if not isinstance(text, dict):
                    text = {"en": str(text)}
                text["en"] = st.text_area(
                    T("achievement_n", n=ach_index + 1),
                    value=str(text.get("en") or next(iter(text.values()), "")),
                    key=f"ach_{role_index}_{ach_index}", height=80,
                )
                achievement["text"] = text
    return edited


def _free_target(path: Path) -> Path:
    # Never overwrite: if a file for this company+day already exists (or it's open/locked in Word),
    # save the next numbered variant (-2, -3, ...).
    if not path.exists():
        return path
    for i in range(2, 1000):
        candidate = path.parent / f"{path.stem}-{i}{path.suffix}"
        if not candidate.exists():
            return candidate
    return path


def offer_stem(offer: dict) -> str:
    return safe_name(offer.get("company") or offer.get("title") or "jobtailor", "jobtailor", maxlen=40)


def safe_name(value: str, fallback: str, maxlen: int = 60) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    cleaned = cleaned[:maxlen].strip("-")
    return cleaned or fallback


def run_node(script: str, args: list[str], env: dict) -> None:
    proc = subprocess.run(
        ["node", str(ROOT / "src" / "node" / script), *args],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip() or f"exited {proc.returncode}"
        raise RuntimeError(f"{script}: {detail}")


def offer_output_dir(output_root: Path, offer: dict) -> Path:
    return output_root / date.today().isoformat() / offer_stem(offer)


def generate_outputs(library: dict, style: dict | None, offer: dict, output_root: Path) -> tuple[Path, Path]:
    lang = offer.get("language") or "en"
    stem = offer_stem(offer)
    output_dir = offer_output_dir(output_root, offer)
    output_dir.mkdir(parents=True, exist_ok=True)
    cv_path = _free_target(output_dir / f"CV-{stem}-{lang}.docx")
    letter_path = _free_target(output_dir / f"cover-letter-{stem}-{lang}.docx")
    env = os.environ.copy()
    env["JOBTAILOR_LIBRARY_JSON"] = json.dumps(library, ensure_ascii=False)
    if style:
        env["JOBTAILOR_STYLE_JSON"] = json.dumps(style, ensure_ascii=False)
    with tempfile.TemporaryDirectory() as tmp:
        offer_path = Path(tmp) / "offer.json"
        offer_path.write_text(json.dumps(offer, ensure_ascii=False), encoding="utf-8")
        run_node("generate-cv.js", ["--lang", lang, "--offer", str(offer_path), "--out", str(cv_path)], env)
        run_node("generate-cover-letter.js", ["--lang", lang, "--offer", str(offer_path), "--out", str(letter_path)], env)
    return cv_path, letter_path


def render_ats_panel(cv_path: Path, offer: dict) -> None:
    # ATS keywords must be SHORT terms, not full requirement sentences. Keep concise, deduped, capped.
    seen: set[str] = set()
    keywords: list[str] = []
    for kw in (offer.get("must_have") or []) + (offer.get("keywords") or []):
        kw = str(kw).strip()
        if kw and 1 <= len(kw.split()) <= 4 and kw.lower() not in seen:
            seen.add(kw.lower())
            keywords.append(kw)
        if len(keywords) >= 25:
            break
    result = ats_scorer.score(ats_scorer.read_cv_text(str(cv_path)), keywords)
    st.subheader(T("ats_match"))
    st.metric(T("match"), f"{result['coverage'] * 100:.0f}%")
    matched = "".join(f'<span class="jt-chip jt-chip-match">{escape(str(item))}</span>' for item in result["present"])
    missing = "".join(f'<span class="jt-chip jt-chip-missing">{escape(str(item))}</span>' for item in result["missing"])
    st.markdown(f"<div class='jt-card'><strong>{T('matched')}</strong><br>{matched or T('none_yet')}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='jt-card'><strong>{T('missing')}</strong><br>{missing or T('none')}</div>", unsafe_allow_html=True)


def render_footer() -> None:
    st.markdown(
        "<div class='jt-footer'>"
        f"<a href='{JOBTAILOR_ISSUES_URL}' style='color:var(--text-muted);margin-right:1.5rem;text-decoration:none'>{escape(T('suggest'))}</a>"
        f"<a href='{JOBTAILOR_COFFEE_URL}' style='color:var(--text-muted);text-decoration:none'>Buy me a coffee</a>"
        "</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="jobtailor", layout="wide")
    apply_theme()
    state = load_app_state()
    if "ui_lang" not in st.session_state:
        st.session_state["ui_lang"] = state.get("ui_lang", DEFAULT_LANG)
    settings = load_settings()

    st.title("jobtailor")
    st.caption(T("tagline"))

    with st.sidebar:
        language_toggle(state)
        output_root = get_output_root(settings, state)
        st.caption(T("output_folder", path=output_root))
        if st.button(T("change_folder")):
            selected = choose_output_folder(output_root)
            if selected:
                state["output_folder"] = str(selected)
                save_app_state(state)
                st.rerun()
        _coffee_svg = (
            "<svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='#FFDD00' "
            "stroke-width='2' stroke-linecap='round' stroke-linejoin='round' style='flex:none'>"
            "<path d='M17 8h1a4 4 0 0 1 0 8h-1'/>"
            "<path d='M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4Z'/>"
            "<line x1='6' y1='1' x2='6' y2='4'/><line x1='10' y1='1' x2='10' y2='4'/><line x1='14' y1='1' x2='14' y2='4'/>"
            "</svg>"
        )
        _mail_svg = (
            "<svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='#8FC4A6' "
            "stroke-width='2' stroke-linecap='round' stroke-linejoin='round' style='flex:none'>"
            "<rect x='3' y='5' width='18' height='14' rx='2'/><path d='m3 7 9 6 9-6'/>"
            "</svg>"
        )
        _lnk = "display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--text-main);font-size:1.02rem"
        st.markdown(
            "<div style='margin-top:1.6rem;display:flex;flex-direction:column;gap:0.9rem'>"
            f"<a href='{JOBTAILOR_COFFEE_URL}' style='{_lnk}'>{_coffee_svg}<span>Buy me a coffee</span></a>"
            f"<a href='{JOBTAILOR_ISSUES_URL}' style='{_lnk}'>{_mail_svg}<span>{escape(T('suggest'))}</span></a>"
            "</div>",
            unsafe_allow_html=True,
        )

    configure_provider()

    cv_upload = st.file_uploader(T("upload_cv"), type=["pdf", "docx", "txt", "md"])
    st.caption(T("docx_hint"))
    cl_upload = st.file_uploader(T("upload_cl"), type=["pdf", "docx", "txt", "md"])

    library = resolve_library(cv_upload)

    if cl_upload is not None:
        cl_fid = f"{cl_upload.name}:{getattr(cl_upload, 'size', '')}"
        if st.session_state.get("cl_fid") != cl_fid:
            st.session_state["style"] = ingest_profile.draft_style(read_upload_text(cl_upload))
            st.session_state["cl_fid"] = cl_fid
    style = st.session_state.get("style")

    if library is None:
        st.info(T("upload_prompt"))
        st.stop()

    # Editable review, then auto-persist the profile so a returning user skips re-uploading.
    library = edit_profile(library)
    st.session_state["library"] = library
    save_library(library)

    if style:
        st.subheader(T("review_style"))
        st.code(yaml.safe_dump(style, allow_unicode=True, sort_keys=False), language="yaml")

    st.subheader(T("offer"))
    st.caption(T("output_lang_note"))
    col_url, col_new = st.columns([4, 1])
    with col_url:
        offer_url = st.text_input(T("job_url"), key="offer_url")
    with col_new:
        st.write("")
        if st.button(T("new_offer")):
            for key in ["offer_url", "offer_text", "last_saved_dir", "last_cv", "last_letter", "strength_questions"]:
                st.session_state.pop(key, None)
            st.rerun()
    with st.expander(T("advanced")):
        firecrawl_key = st.text_input(T("firecrawl"), type="password", help=T("firecrawl_help"))
        if firecrawl_key:
            os.environ["FIRECRAWL_API_KEY"] = firecrawl_key
    offer_text = st.text_area(T("paste_offer"), height=200, key="offer_text")
    offer = parse_offer_input(offer_url, offer_text)
    if offer and (offer.get("company") or offer.get("title")):
        st.caption(f"{offer.get('company', '')} · {offer.get('title', '')}".strip(" ·"))

    answers = render_strength_sidebar(library, offer, output_root)

    if offer and st.button(T("generate"), type="primary"):
        final_library = merge_strength_answers(library, answers, offer.get("language") or "en")
        with st.spinner(T("generating")):
            try:
                cv_path, letter_path = generate_outputs(final_library, style, offer, output_root)
            except Exception as exc:  # noqa: BLE001
                st.error(T("gen_failed", error=exc))
                st.stop()
        st.session_state["last_saved_dir"] = str(cv_path.parent)
        st.session_state["last_cv"] = str(cv_path)
        st.session_state["last_letter"] = str(letter_path)
        state["last_saved_dir"] = str(cv_path.parent)
        save_app_state(state)
        st.success(T("saved_to", path=cv_path.parent))
        render_ats_panel(cv_path, offer)

    if st.session_state.get("last_saved_dir"):
        o1, o2, o3 = st.columns(3)
        with o1:
            if st.button(T("open_folder")):
                open_path(Path(st.session_state["last_saved_dir"]))
        with o2:
            if st.session_state.get("last_cv") and st.button(T("open_cv")):
                open_path(Path(st.session_state["last_cv"]))
        with o3:
            if st.session_state.get("last_letter") and st.button(T("open_letter")):
                open_path(Path(st.session_state["last_letter"]))



if __name__ == "__main__":
    main()
