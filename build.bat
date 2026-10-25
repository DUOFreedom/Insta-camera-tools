@echo off
chcp 936 >nul
rem 打包为单文件 exe，需要预先安装 pyinstaller
rem 统一使用 .spec 配置，请勿额外添加 --add-data 参数
setlocal
cd /d "%~dp0"
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
  echo [错误] 未安装 PyInstaller，请先执行: pip install pyinstaller
  exit /b 1
)
python -m PyInstaller --noconfirm InstaAceImporter.spec
echo EXITCODE=%ERRORLEVEL%
endlocal
