@echo off
chcp 936 >nul
rem 从源码直接运行 GUI
setlocal
cd /d "%~dp0"
start "" python gui.py
endlocal
