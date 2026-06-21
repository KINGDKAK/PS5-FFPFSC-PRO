@echo off
title Build PS5 FFPFSC PRO v1.3.0
echo ============================================================
echo  PS5 FFPFSC PRO v1.3.0 - EXE Builder
echo ============================================================
echo.
echo Installing / updating dependencies...
py -m pip install customtkinter pillow pyinstaller mkpfs tkinterdnd2 py7zr rarfile
echo.

echo Cleaning previous build...
rmdir /s /q build 2>nul
rmdir /s /q dist  2>nul

echo.
echo Running syntax check...
py -m py_compile PS5_FFPFSC_PRO_v1.3.0.py
if errorlevel 1 (
  echo [FAIL] Syntax check failed on PS5_FFPFSC_PRO_v1.3.0.py
  pause
  exit /b 1
)
py -m py_compile backend\cli.py
if errorlevel 1 (
  echo [FAIL] Syntax check failed on backend\cli.py
  pause
  exit /b 1
)
echo Syntax OK.

echo.
echo Building EXE...
py -m PyInstaller PS5_FFPFSC_PRO_v1.3.0.spec
if errorlevel 1 (
  echo [FAIL] PyInstaller build failed.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  Build complete!
echo  Output: dist\PS5_FFPFSC_PRO.exe
echo ============================================================
pause
