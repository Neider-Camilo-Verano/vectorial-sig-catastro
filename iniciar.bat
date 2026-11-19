@echo off
rem Arranca la API y el visor en http://127.0.0.1:8000 (Windows)
cd /d "%~dp0"
if not exist .env goto sin_env
if exist .venv\Scripts\python.exe goto hay_entorno

rem No hay entorno virtual: se busca Python. Se prueba primero el lanzador "py",
rem porque "python" puede ser el atajo de la Microsoft Store y no ejecutar nada.
set PY=
py -3 --version >nul 2>nul
if not errorlevel 1 set PY=py -3
if defined PY goto crear_entorno
python --version >nul 2>nul
if not errorlevel 1 set PY=python
if defined PY goto crear_entorno
goto sin_python

:crear_entorno
%PY% -m venv .venv

:hay_entorno
.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt
echo Visor en http://127.0.0.1:8000
start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:8000"
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000
pause
goto :eof

:sin_env
echo Falta el archivo .env: copie .env.example como .env y escriba la conexion a PostgreSQL.
pause
exit /b 1

:sin_python
echo No se encontro Python. Instalelo desde https://www.python.org/downloads/ marcando "Add python.exe to PATH".
pause
exit /b 1
