@echo off
setlocal
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 "%~dp0tools\launch.py" --watch
) else (
    python "%~dp0tools\launch.py" --watch
)
set "sunder_exit=%errorlevel%"
echo.
pause
exit /b %sunder_exit%
