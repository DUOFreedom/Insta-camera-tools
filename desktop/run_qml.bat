@echo off
chcp 936 >nul
rem 从源码直接启动 QML 版（PySide6），不带控制台窗口
rem 经典版（PyQt5 的 run.bat / gui.py）已删除，现在只有这一套界面。
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
