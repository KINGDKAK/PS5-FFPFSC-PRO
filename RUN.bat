@echo off
title PS5 FFPFSC PRO v1.2.2
echo.
echo  PS5 FFPFSC PRO v1.2.2
echo  IMPORTANT: Extract the ZIP first. Do not run from inside the ZIP.
echo.
py -m pip install customtkinter pillow mkpfs tkinterdnd2 py7zr rarfile
py PS5_FFPFSC_PRO_v1.2.2.py
if errorlevel 1 python PS5_FFPFSC_PRO_v1.2.2.py
pause
