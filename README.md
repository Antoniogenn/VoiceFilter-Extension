# Voice Live — estensione Firefox + backend Python

Rileva **in tempo reale chi sta parlando** in un video YouTube: la popup mostra
le voci rilevate (`voce1`, `voce2`, ...) e per ognuna uno **slider 0–100%** per
attenuarla solo quando parla. L'identificazione è fatta da un **backend Python
locale** con ECAPA-TDNN: l'estensione gli manda l'audio via WebSocket e riceve
"chi parla adesso".

## Architettura

```
video → MediaElementSource → AudioWorkletNode → speakers (pass-through con
                                                    attenuazione per voce)
                                │
                   chunk da 512 campioni mono (Float32)
                                ▼
                    content script → WebSocket 127.0.0.1:8765/ws
                                │   {"type":"start"} / {"type":"audio","rate":16000}
                                │   frame binari Float32 LE
                                ▼
               backend FastAPI (backend/server.py)
                  ├── Silero VAD  → segmenta gli interventi
                  ├── ECAPA-TDNN  → embedding vocale per intervento
                  └── coseno vs catalogo voci (MATCH/NEW_MATCH/CONFIRM)
                                │
        {"type":"now","speaker":"voce1"}
        {"type":"voices","voices":[{name,count}]}
        {"type":"status","text":...}
```

Il lavoro di classificazione è interamente nel backend. Il worklet fa solo
**pass-through + invio audio** e applica il livello per-voce.

## Installazione (sviluppo)

1. Prepara l'ambiente Python (una volta sola) — crea un `.venv` con le
   dipendenze del backend (`numpy`, `fastapi`, `uvicorn`, `torch`,
   `torchaudio`, `silero-vad`, `speechbrain`, `websockets`) da `backend/requirements.txt`:
   - Linux/macOS: `./setup.sh`
   - Windows: `setup.bat`
2. Avvia il backend:
   - Linux/macOS: `.venv/bin/python backend/server.py`
   - Windows: `.venv\Scripts\python.exe backend\server.py`
   (al primo avvio scarica i modelli SpeechBrain/Silero).

### Estensione — due cartelle

- `firefox/` — Manifest V2, API nativa `browser.*`. Apri `about:debugging#/runtime/this-firefox` → **Carica componente aggiuntivo temporaneo** → seleziona `firefox/manifest.json`.
- `chrome/` — Manifest V3 con shim `browser.*`→`chrome.*` (`browser-shim.js`). Apri `chrome://extensions` → attiva **Modalità sviluppatore** → **Carica estensione non pacchettizzata** → seleziona la cartella `chrome/`.

Dopo il caricamento apri un **video YouTube** con più parlanti e clicca l'icona
dell'estensione.

## Uso dal popup

- **Backend (host:porta)**: indirizzo del backend (`host:porta`, default
  `127.0.0.1:8765`). Salvato in storage e applicato alla connessione
  WebSocket (`ws://HOST:PORTA/ws`); se cambiato a rilevamento attivo, la
  sessione si ricollega. Per indirizzi non locali servono i permessi
  corrispondenti nel `manifest.json` di ciascuna cartella.
- **Avvia rilevamento / Stop**: avvia/ferma l'audio verso il backend.
- **Controlli ogni (ms)**: frequenza del ricontrollo "chi parla adesso"
  (multipli di 32, default 64 ms).
- In basso appare **chi parla adesso** (puntino verde sulla riga della voce
  attiva).
- La lista **Voci rilevate** mostra le voci; per ognuna uno **slider 0–100%**:
  a 0% quella voce è muta in uscita. Clicca il nome per **rinominarla**.
- **Cancella voci salvate**: azzera il catalogo backend, i livelli e i nomi.

## Come funziona il backend

- **VAD**: Silero (streaming, finestre da 512 campioni). Un intervento si chiude
  dopo `SILENCE_END_S` (0.3 s) di silenzio; gli interventi oltre `LONG_UTT_S`
  (1.5 s) vengono classificati a pezzi.
- **Identità**: embedding medio ECAPA-TDNN sull'intervento, confronto coseno col
  catalogo delle voci note. `MATCH=0.35` → stessa voce (profilo aggiornato);
  altrimenti si apre un **candidato**, che diventa una nuova voce solo dopo
  `CONFIRM=2` interventi coerenti (`NEW_MATCH=0.30`), con anti-merge.
- **Sovrapposizioni**: oltre a top-1/top-2 vicine, se la voce dominante lascia
  un **residuo** che punta a un'altra voce nota la coppia viene marcata
  `overlap` anche nei mix sbilanciati (`RESIDUAL_MIN`, `RESIDUAL_NORM_MIN`).
- Le voci vengono nominate in ordine di scoperta: `voce1`, `voce2`, ...
- Soglie calibrate sul talk radiofonico reale "La Zanzara" (test video).

## Protocollo WebSocket

Client → server:
- `{"type":"start"}` — azzera la sessione
- `{"type":"audio","rate":16000}` — attiva la ricezione audio
- `{"type":"heartbeat","ms":64}` — cambia il ritempo del ricontrollo
- frame binari Float32 LE — l'audio vero e proprio
- `{"type":"stop"}` — ferma l'audio

Server → client: `{"type":"now","speaker"}`, `{"type":"voices","voices":[...]}`,
`{"type":"status","text"}`.

## Limiti (importanti)

- Serve il **backend in esecuzione** su `127.0.0.1:8765` (il primo avvio
  richiede qualche decina di secondi per i modelli).
- Il video deve stare riproducendosi (il worklet legge l'audio del `<video>`).
- Soglie calibrate su radio parlata reale; su audio molto sporco o voci
  sovrapposte possono formarsi voci residue (calibrabili in `backend/server.py`).

## Estendere

- `backend/server.py`: VAD, embedding, matching, soglie (`MATCH`, `NEW_MATCH`,
  `CONFIRM`, `SILENCE_END_S`, `LONG_UTT_S`).
- `firefox/worklet.js` e `chrome/worklet.js`: pass-through, invio chunk, livelli per-voce.
- `firefox/content/youtube-live.js` e `chrome/content/youtube-live.js`: connessione WS, messaggistica.
- `firefox/popup.html` + `popup.js` e `chrome/popup.html` + `popup.js`: UI
  (slider, rinomina, puntino verde, heartbeat). `chrome/` usa lo shim
  `browser-shim.js` per adattare `browser.*` a `chrome.*`.

I file condivisi (`popup.js`, `worklet.js`, `content/youtube-live.js`) sono
identici nelle due cartelle: se li modifichi, applicali a entrambe.