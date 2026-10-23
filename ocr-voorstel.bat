@echo off
rem Leest commando%s van nieuwe schermafbeeldingen (Windows-OCR) en maakt een voorstel.
cd /d "%~dp0"
python build.py --ocr
pause
