@echo off
chcp 936 >nul
rem 打包 QML 版（PySide6 + onedir），需要预装 pyinstaller 与 PySide6
rem 经典版（PyQt5 的 build.bat / InstaAceImporter.exe）已删除。
rem 本脚本出 PySide6 onedir 目录 dist\InstaAceQml\InstaAceQml.exe。
setlocal
cd /d "%~dp0"
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
  echo [错误] 未安装 PyInstaller，请先执行: pip install pyinstaller
  exit /b 1
)
python -c "import PySide6" 2>nul
if errorlevel 1 (
  echo [错误] 未安装 PySide6，请先执行: pip install -r requirements.txt
  exit /b 1
)
python -m PyInstaller --noconfirm InstaAceQml.spec
echo EXITCODE=%ERRORLEVEL%
endlocal
