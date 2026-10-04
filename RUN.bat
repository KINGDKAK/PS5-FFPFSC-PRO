@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title PS5 FFPFSC PRO v1.3.0
echo.
echo  PS5 FFPFSC PRO v1.3.0
echo  IMPORTANT: Extract the ZIP first. Do not run from inside the ZIP.
echo.
py -m pip install customtkinter pillow mkpfs==0.0.9 tkinterdnd2 py7zr rarfile cryptography pypresence
py PS5_FFPFSC_PRO_v1.3.0.py
if errorlevel 1 python PS5_FFPFSC_PRO_v1.3.0.py
pause
