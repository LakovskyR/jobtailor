#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

if command -v npm >/dev/null 2>&1 && [ ! -d node_modules ]; then
  npm install
fi

open_browser() {
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://localhost:8501 >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then
    open http://localhost:8501 >/dev/null 2>&1 &
  fi
}

if command -v uv >/dev/null 2>&1; then
  open_browser
  exec uv run --with-requirements requirements.txt streamlit run app.py
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
open_browser
exec streamlit run app.py
