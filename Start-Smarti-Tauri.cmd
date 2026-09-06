@echo off
setlocal
title SmartiAI - Tauri Test

rem Resolve everything from this file so double-clicking works from any folder.
rem Install the locked frontend dependencies only when they are missing.
set "SMARTI_TAURI_INSTALL_OPTION="
if exist "%~dp0desktop\node_modules\.bin\tauri.cmd" if exist "%~dp0desktop\node_modules\.bin\vite.cmd" set "SMARTI_TAURI_INSTALL_OPTION=-SkipInstall"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_tauri_dev.ps1" %SMARTI_TAURI_INSTALL_OPTION%
set "SMARTI_TAURI_EXIT_CODE=%ERRORLEVEL%"

if not "%SMARTI_TAURI_EXIT_CODE%"=="0" (
    echo.
    echo SmartiAI Tauri could not start or exited with an error. See the output above.
    pause
)
exit /b %SMARTI_TAURI_EXIT_CODE%
