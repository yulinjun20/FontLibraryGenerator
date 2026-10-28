@echo off
cd /d "%~dp0"
py -3 "%~dp0Bake-TtfToUfl-Gui.py"
if errorlevel 1 (
  echo.
  echo Failed. Try: py -3 -m pip install uharfbuzz freetype-py fonttools pillow
  pause
)
