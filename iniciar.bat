@echo off
cd /d "%~dp0"
python ponto.py
if errorlevel 1 pause
