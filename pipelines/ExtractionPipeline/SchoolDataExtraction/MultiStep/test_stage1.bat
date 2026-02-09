@echo off
REM Test Stage 1 - Question Extraction
REM Run from the MultiStep directory

echo ============================================================
echo Stage 1 Test: Question Extraction
echo ============================================================

REM Test 1: keph203.pdf - Questions 10.5, 10.15 (figure on same page, figure spill-over)
echo.
echo Test 1: keph203.pdf (Physics - Mechanical Properties)
echo Expected: Questions with figures, some on next page
python main.py --stage 1 --pdf "Input/keph203.pdf" --subject "Physics"

REM Uncomment below for additional tests:

REM Test 2: keph202.pdf - Question 9.15 (table transcription)
REM echo.
REM echo Test 2: keph202.pdf (Physics - Thermodynamics)
REM echo Expected: Questions with tables transcribed as Markdown
REM python main.py --stage 1 --pdf "Input/keph202.pdf" --subject "Physics"

REM Test 3: keph102.pdf - Questions 2.17, 2.18 (multi-part questions)
REM echo.
REM echo Test 3: keph102.pdf (Physics - Units & Measurements)
REM echo Expected: Multi-part questions properly structured
REM python main.py --stage 1 --pdf "Input/keph102.pdf" --subject "Physics"

REM Test with specific page range
REM echo.
REM echo Test 4: Specific page range
REM python main.py --stage 1 --pdf "Input/keph203.pdf" --pages "20-25" --subject "Physics"

echo.
echo ============================================================
echo Test Complete! Check Output folder for results.
echo ============================================================
pause
