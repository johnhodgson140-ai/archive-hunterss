@echo off
setlocal enabledelayedexpansion

echo ========================================
echo  Archive Hunter GitHub Commit Helper
echo ========================================

git --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git is not installed or not available in PATH.
    pause
    exit /b 1
)

echo.
if exist .git (
    echo Git repository already initialized.
) else (
    echo Initializing Git repository...
    git init
)

echo.
echo Adding files to git staging area...
git add .

echo.
set /p COMMIT_MSG=Enter commit message [Initial Archive Hunter commit]:
if "%COMMIT_MSG%"=="" set COMMIT_MSG=Initial Archive Hunter commit

git commit -m "%COMMIT_MSG%"
if %errorlevel% neq 0 (
    echo [ERROR] Commit failed. Please resolve any issues and try again.
    pause
    exit /b 1
)

echo.
set /p REMOTE_URL=Enter GitHub remote URL to add (leave blank to skip):
if not "%REMOTE_URL%"=="" (
    git remote add origin %REMOTE_URL%
    git push -u origin main
)

echo.
echo Done.
pause
