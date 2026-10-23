@echo off
rem Dubbelklik: bouwt de site (map site\) en de offline-ZIP (map dist\).
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python build.py %*
echo.
echo Rapport: bouwrapport.md
pause
