@echo off
cd /d "%~dp0"
python -m pip install --target vendor -r requirements-runtime.txt
if errorlevel 1 exit /b 1
python -m pip install --target build-libs -r requirements-build.txt
if errorlevel 1 exit /b 1
echo Pronto. Execute python build.py para gerar o launcher portatil.
