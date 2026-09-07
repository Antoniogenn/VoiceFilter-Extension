@echo off
rem Voice Live - setup dell'ambiente Python (Windows)
rem Crea un virtualenv nella cartella e installa tutte le dipendenze.
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv" (
  echo creo il virtualenv...
  python -m venv .venv
  if errorlevel 1 goto :error
)

echo installo le dipendenze (puo' richiedere minuti)...
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :error

echo installo torch CPU da download.pytorch.org (Windows)...
.venv\Scripts\python.exe -m pip install torch==2.13.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto :torch_error

rem il resto viene da PyPI normale (numpy/fastapi/silero/speechbrain sono gia'
rem qui, ma requirements.txt e' la fonte di verita', quindi reinstalliamo tutto)
echo installo le dipendenze da requirements.txt...
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 goto :error

echo.
echo Pronto. Per avviare il backend:
echo   .venv\Scripts\python.exe backend\server.py
goto :eof

:torch_error
echo.
echo ATTENZIONE: l'installazione di torch/torchaudio da download.pytorch.org e' fallita.
echo Se hai gia' torch a tensore con CUDA, puoi proseguire installando solo il resto:
echo   .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
goto :error

:error
echo.
echo Installazione interrotta. Verifica che Python sia installato e nel PATH
echo (python --version) e riprova.
exit /b 1