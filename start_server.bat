@echo off
REM Double-click this instead of opening a terminal and typing "python app.py".
REM Prefers the Python install that has Playwright + Chromium set up (needed
REM for the auto-fill feature); falls back to plain "python" if that exact
REM install isn't present (e.g. on a different machine).
cd /d "%~dp0"
echo Starting Job Fetch Agent locally on http://localhost:8000 ...
echo Leave this window open while you use the hosted site's Auto-fill button.
echo Close this window (or press Ctrl+C) to stop the server.
echo.
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" app.py
) else (
    python app.py
)
echo.
echo Server stopped. Press any key to close this window.
pause >nul
