@echo off
cd /d %~dp0
call .venv\Scripts\activate.bat
for /f "tokens=1,2 delims==" %%a in (.env) do set %%a=%%b
python bot.py
pause
