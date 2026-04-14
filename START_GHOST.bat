@echo off
echo ==========================================
echo   GHOST3D Tesla Drive Mode Controller
echo ==========================================
echo.
echo Starting Ghost Mode UI...
echo Open http://localhost:9090 in your browser
echo.
cd /d "%~dp0"
python tools/ghost_ui.py -p COM5
pause
