@echo off
cd /d "%~dp0"
echo Starting Drone Finder server...
echo Open http://127.0.0.1:8000 in your browser once it's running.
echo Press Ctrl+C to stop.
echo.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
