@echo off
cd /d "%~dp0"
python flo_downloader.py
if errorlevel 1 (
  py flo_downloader.py
  if errorlevel 1 (
    echo.
    echo Non riesco ad avviare il programma. Controlla che Python sia installato
    echo con la casella "Add python.exe to PATH" spuntata.
    pause
  )
)