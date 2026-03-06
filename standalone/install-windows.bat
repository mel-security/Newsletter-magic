@echo off
REM ══════════════════════════════════════════════════════════
REM  Standalone Newsletter Agent — Windows Installer
REM ══════════════════════════════════════════════════════════
REM  Installs: Python 3.12 (via winget), venv, pip packages
REM  Ollama must be installed manually from https://ollama.com
REM  Idempotent — safe to run multiple times.
REM ══════════════════════════════════════════════════════════

setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo ══════════════════════════════════════════════════════════
echo   Standalone Newsletter Agent — Windows Installer
echo ══════════════════════════════════════════════════════════
echo.

REM ── 1. Check/Install Python ────────────────────────────
echo [INFO] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Python not found. Attempting install via winget...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo [ERROR] Could not install Python automatically.
        echo         Please install Python 3.12+ from https://www.python.org/downloads/
        echo         Make sure to check "Add Python to PATH" during installation.
        pause
        exit /b 1
    )
    echo [OK] Python installed. You may need to restart this script.
    echo      Close this window, open a NEW terminal, and re-run install-windows.bat
    pause
    exit /b 0
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo [OK] Python %PYVER% found.

REM ── 2. Create virtual environment ──────────────────────
echo [INFO] Setting up virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)

call .venv\Scripts\activate.bat

REM ── 3. Install Python packages ─────────────────────────
echo [INFO] Installing Python packages...
pip install --upgrade pip -q
pip install -q httpx>=0.28.0 feedparser>=6.0.11 trafilatura>=2.0.0 pyyaml>=6.0.2 jinja2>=3.1.4 beautifulsoup4>=4.12.0
echo [OK] Python packages installed.

REM ── 4. Check Ollama ────────────────────────────────────
echo [INFO] Checking Ollama...
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Ollama not found.
    echo.
    echo   Please install Ollama manually:
    echo     1. Download from https://ollama.com/download/windows
    echo     2. Run the installer
    echo     3. Re-run this script
    echo.
    echo   Alternatively, use winget:
    echo     winget install -e --id Ollama.Ollama
    echo.
    pause
    exit /b 1
) else (
    echo [OK] Ollama found.
)

REM ── 5. Pull LLM models ────────────────────────────────
set "WRITER_MODEL=mistral"
set "REVIEWER_MODEL=deepseek-r1:7b"
echo [INFO] Pulling writer model: %WRITER_MODEL%...
ollama pull %WRITER_MODEL%
echo [OK] Writer model %WRITER_MODEL% ready.

echo [INFO] Pulling reviewer model: %REVIEWER_MODEL%...
ollama pull %REVIEWER_MODEL%
echo [OK] Reviewer model %REVIEWER_MODEL% ready.

REM ── 6. Config ──────────────────────────────────────────
if not exist "config\context.yml" (
    copy "config\context.yml.example" "config\context.yml" >nul
    echo [OK] Created config\context.yml from example. Edit it to customize.
) else (
    echo [OK] config\context.yml already exists.
)

if not exist "output" mkdir output

REM ── Done ───────────────────────────────────────────────
echo.
echo ══════════════════════════════════════════════════════════
echo   Installation Complete!
echo ══════════════════════════════════════════════════════════
echo.
echo   To run the newsletter agent:
echo.
echo     cd %SCRIPT_DIR%
echo     .venv\Scripts\activate.bat
echo     python run.py
echo.
echo   With custom LLMs:
echo.
echo     python run.py --llmwriter mistral --reviewer deepseek-r1:7b
echo.
echo   Output will be saved to: %SCRIPT_DIR%output\
echo.
echo   Edit config\context.yml to change topic ^& search queries.
echo.
pause
