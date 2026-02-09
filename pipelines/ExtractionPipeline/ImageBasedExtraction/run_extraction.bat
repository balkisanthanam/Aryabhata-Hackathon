@echo off
REM Quick start script for Image-Based Extraction Pipeline

echo ============================================
echo Image-Based Question Extraction Pipeline
echo ============================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

REM Check for flush-only mode
if "%~1"=="--flush" (
    if "%~2"=="" (
        echo Flushing entire output directory...
        python -c "import shutil; from pathlib import Path; p = Path('output/ImageBasedExtraction'); shutil.rmtree(p) if p.exists() else print('Nothing to flush'); print('Flushed: ' + str(p))"
        echo.
        echo Done!
        pause
        exit /b 0
    ) else (
        echo Flushing specific directory: %~2
        python -c "import shutil; from pathlib import Path; p = Path('%~2'); shutil.rmtree(p) if p.exists() else print('Nothing to flush'); print('Flushed: ' + str(p))"
        echo.
        echo Done!
        pause
        exit /b 0
    )
)

REM Check if input file provided
if "%~1"=="" (
    echo Usage: run_extraction.bat ^<path_to_pdf^> [output_folder] [--flush]
    echo        run_extraction.bat --flush [directory]
    echo.
    echo Examples:
    echo   run_extraction.bat input\sample.pdf
    echo   run_extraction.bat input\sample.pdf output\my_extraction
    echo   run_extraction.bat input\sample.pdf output\my_extraction --flush
    echo.
    echo   run_extraction.bat --flush                              (flush default output)
    echo   run_extraction.bat --flush output\specific_run          (flush specific directory)
    echo.
    echo Options:
    echo   --flush    Delete all intermediate results before running (clean start)
    echo.
    pause
    exit /b 1
)

REM Set input and output
set INPUT_PDF=%~1
set OUTPUT_DIR=
set FLUSH_FLAG=

REM Check for flush flag and set output directory
if "%~2"=="--flush" (
    set FLUSH_FLAG=--flush
) else if "%~3"=="--flush" (
    set OUTPUT_DIR=%~2
    set FLUSH_FLAG=--flush
) else if not "%~2"=="" (
    set OUTPUT_DIR=%~2
)

REM Check if input file exists
if not exist "%INPUT_PDF%" (
    echo ERROR: Input file not found: %INPUT_PDF%
    pause
    exit /b 1
)

echo Input PDF: %INPUT_PDF%
if not "%OUTPUT_DIR%"=="" (
    echo Output Directory: %OUTPUT_DIR%
    echo Flush Mode: %FLUSH_FLAG%
    python main_extraction_pipeline.py --input "%INPUT_PDF%" --output "%OUTPUT_DIR%" %FLUSH_FLAG%
) else (
    echo Output Directory: [default from config]
    if not "%FLUSH_FLAG%"=="" echo Flush Mode: Enabled
    python main_extraction_pipeline.py --input "%INPUT_PDF%" %FLUSH_FLAG%
)

echo.
echo ============================================
echo Extraction Complete!
echo ============================================
pause
