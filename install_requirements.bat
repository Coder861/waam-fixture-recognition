@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo WAAM fixture recognition - environment setup
echo ==============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found.
    echo Install Python and enable "Add Python to PATH".
    pause
    exit /b 1
)

if not exist "requirements.txt" (
    echo ERROR: requirements.txt was not found in:
    echo %CD%
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment ".venv" ...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: The virtual environment could not be created.
        pause
        exit /b 1
    )
) else (
    echo Existing virtual environment ".venv" will be used.
)

echo.
echo Updating pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: pip could not be updated.
    pause
    exit /b 1
)

echo.
echo Installing required packages ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Package installation failed.
    pause
    exit /b 1
)

echo.
echo Installation completed successfully.
echo Python environment:
".venv\Scripts\python.exe" --version
echo.
pause
exit /b 0
