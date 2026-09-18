@echo off
chcp 65001 >nul
cd /d %~dp0
set PY=server\venv\Scripts\python.exe

echo [1/3] Installing PyInstaller...
%PY% -m pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple --disable-pip-version-check -q
if errorlevel 1 (echo Install failed & pause & exit /b 1)

echo [2/3] Collecting OCR models (bundled into exe, no first-run download)...
%PY% -c "import shutil, pathlib, rapidocr; src = pathlib.Path(rapidocr.__file__).parent / 'models'; dst = pathlib.Path('models/rapidocr'); shutil.rmtree(dst, ignore_errors=True); shutil.copytree(src, dst); print('models:', len(list(dst.glob('*'))), 'files')"
if errorlevel 1 (echo Model collection failed & pause & exit /b 1)

echo [3/4] Building onedir bundle...
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed --name LitManager ^
  --paths server ^
  --collect-all onnxruntime ^
  --collect-all rapidocr ^
  --add-data "models/rapidocr;rapidocr/models" ^

  --add-data "web;web" ^
  start.py
if errorlevel 1 (echo Build failed, start.bat still works & pause & exit /b 1)

echo [4/4] Compiling one-click installer (setup.exe)...
set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "%ISCC%" (
    "%ISCC%" installer.iss
    if errorlevel 1 (echo Setup compile failed & pause & exit /b 1)
) else (
    echo Inno Setup not found - skipping setup.exe (install via setup.bat instead)
)

echo.
echo Done: dist\LitManager\LitManager.exe
echo One-click installer: dist\LitManager-Setup.exe
echo User data: F:\papers\data (or %%USERPROFILE%%\.lit-manager\data)
pause
