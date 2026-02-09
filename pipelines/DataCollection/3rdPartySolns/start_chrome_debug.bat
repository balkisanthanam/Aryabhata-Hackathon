@echo off
echo Starting Chrome in Debug Mode for PDF Download...
echo.

REM Check if URL argument is provided
if "%~1"=="" (
    echo ERROR: Please provide a website URL as an argument.
    echo Usage: start_chrome_debug.bat ^<website_url^>
    echo Example: start_chrome_debug.bat https://allen.in/jee-main/previous-year-papers
    echo.
    pause
    exit /b 1
)

set TARGET_URL=%~1
echo Target Website: %TARGET_URL%
echo.

echo Closing existing Chrome processes...
taskkill /f /im chrome.exe 2>nul
timeout /t 2 /nobreak >nul

echo.
echo Starting Chrome with remote debugging enabled...
echo.
echo IMPORTANT: After Chrome opens, navigate to:
echo %TARGET_URL%
echo.
echo Then login with your credentials if required.
echo.
echo Once logged in, you can run the Python script:
echo python DownloadSolutions.py "%TARGET_URL%"
echo.

REM Create debug directory if it doesn't exist
if not exist "C:\ChromeDebug" mkdir "C:\ChromeDebug"

REM Start Chrome in debug mode with the target URL
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\ChromeDebug" --disable-web-security --disable-features=VizDisplayCompositor "%TARGET_URL%"

echo.
echo Chrome has been started in debug mode and navigated to the target website.
echo Please login if required, then run the Python script with:
echo python DownloadSolutions.py "%TARGET_URL%"
echo.
pause
