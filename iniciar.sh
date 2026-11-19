#!/usr/bin/env bash
# Arranca la API y el visor en http://127.0.0.1:8000 (Linux / macOS)
set -e
cd "$(dirname "$0")"
[ -f .env ] || { echo "Falta .env: copie .env.example a .env y complete DATABASE_URL"; exit 1; }
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
python -m pip install -q -r backend/requirements.txt
echo "Visor en http://127.0.0.1:8000"
python -m uvicorn backend.app.main:app --port 8000
