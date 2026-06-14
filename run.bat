@echo off
setlocal
cd /d "%~dp0"

where npm >nul 2>nul
if %errorlevel%==0 (
  if not exist node_modules (
    npm install
  )
)

where uv >nul 2>nul
if %errorlevel%==0 (
  start "" "http://localhost:8501"
  uv run --with-requirements requirements.txt streamlit run app.py
  exit /b %errorlevel%
)

if not exist .venv (
  py -m venv .venv 2>nul || python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
start "" "http://localhost:8501"
streamlit run app.py
