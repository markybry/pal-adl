@echo off
echo Starting CQC ADL Dashboard...
echo.

cd /d "%~dp0"
set "ENV_FILE=.env"

REM Activate virtual environment if it exists
if exist "..\..\..\.venv\Scripts\activate.bat" (
    call "..\..\..\.venv\Scripts\activate.bat"
)

REM Run Streamlit
python -m streamlit run src/dashboard_v2.py

pause
