@echo off
REM Exam Paper Downloader - Run Script
REM 
REM This batch file sets up environment variables and runs the exam paper downloader
REM 
REM Usage: 
REM 1. Edit the database credentials below
REM 2. Double-click this file or run from command prompt

echo ========================================
echo Exam Paper Downloader
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.7 or higher
    pause
    exit /b 1
)

echo Python found: 
python --version
echo.

REM Check if required packages are installed
echo Checking dependencies...
pip show selenium >nul 2>&1
if errorlevel 1 (
    echo Installing required packages...
    pip install -r requirements.txt
)
echo Dependencies OK
echo.

REM Create JEEMain directory if it doesn't exist
if not exist "JEEMain" (
    echo Creating download directory: JEEMain
    mkdir JEEMain
)

echo Starting download process...
echo Press Ctrl+C to interrupt
echo.

REM Run the Python script
python download_exam_papers.py

echo.
echo ========================================
echo Script execution completed
echo ========================================
pause
