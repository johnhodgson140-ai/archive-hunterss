@echo off
echo ========================================
echo  Archive Hunter - PC Setup Script
echo ========================================
echo.

:: Check Python
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. 
    echo Please install Python from python.org first.
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit
)
echo [OK] Python found

:: Check Git
git --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git not found.
    echo Please install Git from git-scm.com first.
    pause
    exit
)
echo [OK] Git found

:: Use current project folder
echo.
echo Using current folder: %CD%

:: Create virtual environment
echo Creating virtual environment...
python -m venv .venv
echo [OK] Virtual environment created

:: Activate and install dependencies
echo Installing dependencies...
call .venv\Scripts\activate.bat
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo [OK] Dependencies installed

:: Create .env file
echo.
echo Creating .env file...
(
echo TELEGRAM_BOT_TOKEN=paste_your_token_here
echo SUPABASE_URL=https://gitgeuvlwkympazczcgi.supabase.co
echo SUPABASE_KEY=paste_your_supabase_key_here
echo ANTHROPIC_API_KEY=paste_your_claude_key_here
) > .env

:: Create run script
(
echo @echo off
echo cd /d %%~dp0
echo call venv\Scripts\activate.bat
echo set /p TELEGRAM_BOT_TOKEN=
echo python bot.py
echo pause
) > run_bot.bat

:: Actually create a proper run script that reads .env
(
echo @echo off
echo cd /d %%~dp0
echo call venv\Scripts\activate.bat
echo for /f "tokens=1,2 delims==" %%%%a in ^(.env^) do set %%%%a=%%%%b
echo python bot.py
echo pause
) > run_bot.bat

echo.
echo ========================================
echo  Setup complete!
echo ========================================
echo.
echo Next steps:
echo 1. Open the .env file and paste your API keys
echo 2. Make sure bot.py is in this folder  
echo 3. Double-click run_bot.bat to start the bot
echo.
pause
