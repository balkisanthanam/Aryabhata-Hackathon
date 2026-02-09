@echo off
REM Quick test script for Stage 2 Solver Engine
REM Usage: run_test.bat [questions]
REM Example: run_test.bat "12.4,12.7"

setlocal

REM Change to script directory
cd /d "%~dp0"

REM Check if GOOGLE_API_KEY is set
if "%GOOGLE_API_KEY%"=="" (
    echo ERROR: GOOGLE_API_KEY environment variable not set
    echo Please set it with: set GOOGLE_API_KEY=your_api_key
    exit /b 1
)

REM Default questions if not provided
set QUESTIONS=%1
if "%QUESTIONS%"=="" set QUESTIONS="12.4,12.7"

echo ============================================================
echo Stage 2 Solver Engine - Test Run
echo ============================================================
echo Questions: %QUESTIONS%
echo ============================================================

python main.py --questions %QUESTIONS%

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Test failed with error code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

echo.
echo Test completed successfully!
pause
