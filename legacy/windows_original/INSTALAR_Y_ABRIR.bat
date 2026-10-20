@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ========================================
echo       MOORTY VOICE - INSTALADOR
echo          YOUTUBE + TIKTOK
echo ========================================
echo.
echo Buscando Python 3.13 (recomendado para pygame)...
py -3.13 --version >nul 2>&1
if errorlevel 1 goto no313
set "PYTHON_CMD=py -3.13"
goto install
:no313
echo No se encontro Python 3.13 mediante el lanzador py.
echo Instala Python 3.13 de 64 bits desde python.org y marca "Add python.exe to PATH".
echo Despues vuelve a ejecutar este archivo.
pause
exit /b 1
:install
echo Usando:
%PYTHON_CMD% --version
%PYTHON_CMD% -m pip --version
if errorlevel 1 goto piperror
echo.
echo Instalando dependencias con Python 3.13...
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto installerror
echo.
echo Abriendo Moorty Voice...
%PYTHON_CMD% moorty_voice.py
if errorlevel 1 pause
exit /b 0
:piperror
echo.
echo Python 3.13 no tiene pip disponible. Ejecuta: py -3.13 -m ensurepip --upgrade
pause
exit /b 1
:installerror
echo.
echo No se pudieron instalar las dependencias.
echo Este instalador usa Python 3.13 para evitar que pygame intente compilarse con Python 3.15.
echo Si vuelve a aparecer CERTIFICATE_VERIFY_FAILED, revisa la fecha y hora de Windows, proxy/antivirus HTTPS y certificados de Python.
echo No se recomienda desactivar la verificacion SSL.
pause
exit /b 1
