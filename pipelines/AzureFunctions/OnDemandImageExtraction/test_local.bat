@echo off
REM Local testing script for OnDemand Image Extraction Function

echo ========================================
echo OnDemand Image Extraction - Local Test
echo ========================================
echo.

REM Check if virtual environment is activated
if not defined VIRTUAL_ENV (
    echo Virtual environment not activated!
    echo Please run: .venv\Scripts\activate.bat
    echo.
    pause
    exit /b 1
)

echo Virtual environment: %VIRTUAL_ENV%
echo.

REM Check if Azure Functions is running
echo Checking if Azure Function is running...
curl -s http://localhost:7071/ >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Azure Function is not running!
    echo Please start it in another terminal with: func start
    echo.
    pause
    exit /b 1
)

echo Azure Function is running!
echo.
echo Running test script...
echo.

python test_local.py

echo.
pause
