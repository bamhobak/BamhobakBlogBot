@echo off
echo === Naver Blog Bot - Install ===
echo.

python --version
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo.
echo Installing packages from wheels folder...
python -m pip install --no-index --find-links="%~dp0wheels" -r "%~dp0requirements.txt"

echo.
echo === Install Complete! Run run.vbs to start. ===
pause
