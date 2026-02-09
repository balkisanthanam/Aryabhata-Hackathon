@echo off
REM JSON-Based Extraction Evaluation Batch Script
REM Usage: run_evaluation.bat <test_directory> [model_directory]

setlocal

REM Check if test directory is provided
if "%~1"=="" (
    echo Error: Test directory not provided
    echo.
    echo Usage: run_evaluation.bat ^<test_directory^> [model_directory]
    echo.
    echo Example: run_evaluation.bat output\JEEMain\backup\Run1
    echo.
    exit /b 1
)

set TEST_DIR=%~1

REM Set model directory (use provided or default)
if "%~2"=="" (
    set MODEL_DIR=output\JEEMain\backup\ModelRun
) else (
    set MODEL_DIR=%~2
)

echo ================================================================================
echo JSON-BASED EXTRACTION EVALUATION
echo ================================================================================
echo.
echo Test Directory:  %TEST_DIR%
echo Model Directory: %MODEL_DIR%
echo.
echo Starting evaluation...
echo.

REM Run the evaluation
python evaluate_extraction.py --test-dir "%TEST_DIR%" --model-dir "%MODEL_DIR%"

REM Check if evaluation succeeded
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================================================
    echo Evaluation completed successfully!
    echo ================================================================================
    echo.
    echo Check the test directory for evaluation reports:
    echo   - evaluation_*_YYYYMMDD_HHMMSS.txt  ^(human-readable^)
    echo   - evaluation_*_YYYYMMDD_HHMMSS.json ^(machine-readable^)
    echo.
) else (
    echo.
    echo ================================================================================
    echo Evaluation failed with error code: %ERRORLEVEL%
    echo ================================================================================
    echo.
)

endlocal
exit /b %ERRORLEVEL%
