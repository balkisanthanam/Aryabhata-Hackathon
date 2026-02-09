@echo off
echo ============================================
echo JEE Question Tagging Pipeline
echo ============================================
echo.

REM Change to the script directory
cd /d "%~dp0"

REM Run the tagging script
python run_question_tagging.py

echo.
echo ============================================
echo Tagging complete. Press any key to exit.
pause > nul
