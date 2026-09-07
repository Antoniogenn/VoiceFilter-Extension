#!/usr/bin/env bash
# Voice Live - setup dell'ambiente Python.
# Crea un virtualenv nella cartella e installa tutte le dipendenze.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "creo il virtualenv..."
  python3 -m venv .venv
fi

echo "installo le dipendenze (può richiedere minuti)..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r backend/requirements.txt

echo ""
echo "Pronto. Per avviare il backend:"
echo "  .venv/bin/python backend/server.py"