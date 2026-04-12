@echo off
title Genorova AI — Drug Discovery Platform
color 1F

echo.
echo  ================================================================
echo   GENOROVA AI v1.0 — Drug Discovery Platform
echo   Developer: Pushp Dwivedi ^| pushpdwivedi911@gmail.com
echo  ================================================================
echo.
echo  Starting API server...
echo  API will be available at: http://localhost:8000
echo  Interactive docs at:      http://localhost:8000/docs
echo  HTML Report at:           http://localhost:8000/report
echo.
echo  Press Ctrl+C to stop the server.
echo  ================================================================
echo.

cd /d "%~dp0"
"C:/Program Files/Python314/python.exe" -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

echo.
echo  Server stopped.
pause
