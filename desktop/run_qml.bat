@echo off
chcp 936 >nul
rem 从源码直接启动 QML 版（PySide6），不带控制台窗口
rem 与 run.bat 的区别：run.bat 启动 PyQt5 版 gui.py。
setlocal
cd /d "%~dp0"
python -c "import PySide6" 2>nul
if errorlevel 1 (
  echo [错误] 未安装 PySide6，请先执行: pip install -r requirements.txt
  pause
  exit /b 1
)
start "" pythonw main.py
endlocal
