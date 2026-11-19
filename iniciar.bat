@echo off
rem Arranca la API y el visor en http://127.0.0.1:8000 (Windows)
cd /d "%~dp0"
if not exist .env (
    echo Falta el archivo .env: copie .env.example como .env y escriba la conexion a PostgreSQL.
    pause
    exit /b 1
)

rem Si el entorno virtual ya existe se usa directamente. Si no, se busca Python
rem (primero el lanzador "py", porque "python" puede ser el atajo de la Microsoft Store).
if not exist .venv\Scripts\python.exe (
    set PY=
    py -3 --version >nul 2>nul && set PY=py -3
    if not defined PY python --version >nul 2>nul && set PY=python
    if not defined PY (
        echo No se encontro Python. Instalelo desde https://www.python.org/downloads/ marcando "Add python.exe to PATH".
        pause
        exit /b 1
    )
    %PY% -m venv .venv
)

.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt
echo Visor en http://127.0.0.1:8000
start "" cmd /c "timeout /t 4 >nul & start http://127.0.0.1:8000"
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000
pause
