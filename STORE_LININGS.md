# Voice Live — testi per gli store

Testi pronti per le schede del **Chrome Web Store** e **Mozilla AMO**.
Due versioni: inglese (riproducibile per l'approvazione) e italiano (traduzione).

Nota: riempi i campi generici (nome, versione, link) dove indicato. Tutti i testi
devono essere coerenti col comportamento reale: i modelli girano **sul tuo
computer**, niente è inviato a server terzi.

---

## Chrome Web Store

### Nome (Name)
`Voice Live — Real-time speaker detection`

### Sommario (Summary)
Rileva chi sta parlando in un video YouTube e abbassa le voci indesiderate.
Detects who is speaking in a YouTube video and lowers unwanted voices in real time.

### Descrizione (Description)

**English:**

Voice Live detects—in real time—which speaker is talking in a YouTube video
and lets you lower each detected voice individually. Perfect for radio talk
shows, interviews and podcasts with multiple speakers.

How it works:
- The extension captures the video audio privately, on your machine.
- Speech is analysed by a local Python backend (Silero VAD + ECAPA-TDNN) on
  your computer. Your audio never leaves your device or LAN.
- Each detected voice appears in the popup with its own volume slider:
  set a voice to 0% to make it silent whenever it speaks, or to 100% for full
  volume.
- The green dot highlights who is speaking right now; overlaps are shown as
  "voice1 + voice2".
- Click a voice name to rename it; a master pass-through volume and the
  "check every N ms" refresh rate are fully adjustable.

Requirements:
- The Python backend must run locally on your computer (instruction provided).
- YouTube must be playing a video with audio.

Privacy:
- All processing happens locally on your machine.
- No audio, video or biometric data is sent to any Cloud service.
- Only a connection to your own local backend (default ws://127.0.0.1:8765) is
  used; the host and port can be changed in the popup.

**Italiano:**

Voice Live rileva in tempo reale chi sta parlando in un video YouTube e ti
consente di abbassare le singole voci rilevate. Ideale per talk radiofonici,
interviste e podcast con più parlanti.

Come funziona:
- L'estensione cattura l'audio del video in modo privato, sul tuo computer.
- L'audio viene analizzato da un backend Python locale (Silero VAD +
  ECAPA-TDNN) sulla tua macchina. I tuoi dati non lasciano mai il dispositivo
  o la tua rete locale.
- Ogni voce rilevata appare nel popup con uno slider del volume: porta una
  voce a 0% per silenziarla ogni volta che parla, o al 100% per il volume
  pieno.
- Il puntino verde evidenzia chi parla in questo momento; le sovrapposizioni
  sono mostrate come "voce1 + voce2".
- Clicca sul nome di una voce per rinominarla; volume pass-through e frequenza
  "controlla ogni (ms)" sono regolabili.

Requisiti:
- Il backend Python deve girare in locale sul tuo computer (istruzioni fornite).
- YouTube deve riprodurre un video con audio.

Privacy:
- Ogni elaborazione avviene in locale sulla tua macchina.
- Nessun audio, video o dato biometrico viene inviato a servizi Cloud.
- Viene usata solo una connessione verso il tuo backend locale (default
  ws://127.0.0.1:8765); host e porta sono modificabili dal popup.

### Categorie / Categorie
Production, Productivity

### Screenshot (1280×800 o 640×400)
Da generare: 1) popup aperto con la lista voci; 2) estensione attiva su un video
YouTube; 3) popup con voci rinumerate.

---

## Politica sulla privacy

**English version (for the Privacy Policy page — serve un URL pubblico):**

"Voice Live processes audio exclusively on your own computer. The extension
captures the audio of the YouTube video and sends it through a WebSocket
connection to a local Python backend that you run yourself (default
ws://127.0.0.1:8765). Speech is analysed locally with open-source models
(Silero VAD and ECAPA-TDNN). The extension does not collect, transmit or store
any personal data on third-party servers. No audio, no biometric data and no
voice recordings are sent over the Internet. You can stop or delete all
detected data at any time from the extension popup."

**Versione italiana (per il modulo Risposta Privacy del Web Store):**

"Voice Live elabora l'audio esclusivamente sul tuo computer. L'estensione
rileva l'audio del video di YouTube e lo invia tramite una connessione
WebSocket a un backend Python locale che gestisci tu (default
ws://127.0.0.1:8765). Il parlato viene analizzato in locale con modelli open
source (Silero VAD ed ECAPA-TDNN). L'estensione non raccoglie, trasmette o
salva dati personali su server di terze parti. Nessun audio, dato biometrico o
registrazione vocale viene inviato via Internet. Puoi interrompere o eliminare
tutti i dati rilevati in qualsiasi momento dal popup dell'estensione."

---

## Firefox AMO

### Nome
`Voice Live`

### Sommario / Summary
Rileva in tempo reale chi parla in un video YouTube e regola il volume per
voce. Real-time speaker detection for YouTube videos.

### Descrizione (Description)

**English:**

Voice Live detects—in real time—which speaker is talking in a YouTube video
and lets you lower each detected voice individually. Ideal for radio talk
shows, interviews and podcasts with multiple speakers.

The extension sends the video audio to a local Python backend on your machine
(Silero VAD + ECAPA-TDNN): nothing leaves your computer. Detected voices appear
in the popup with a slider each; the green dot shows who is speaking now,
overlaps are shown as "voice1 + voice2", and you can rename voices and tune the
refresh rate (32–256 ms).

Note for reviewers: the WebSocket connection to ws://127.0.0.1 is intentional
and local-only; on Firefox you must enable
`network.websocket.allowInsecureFromHTTPS` in about:config before use. All
permissions are limited to YouTube and the local backend.

**Italiano:**

Voice Live rileva in tempo reale chi sta parlando in un video YouTube e ti
consente di abbassare le singole voci rilevate. Ideale per talk radiofonici,
interviste e podcast con più parlanti.

L'estensione invia l'audio del video a un backend Python locale sulla tua
macchina (Silero VAD + ECAPA-TDNN): nulla esce dal tuo computer. Le voci
rilevate appaiono nel popup ognuna con il proprio slider; il puntino verde
mostra chi parla ora, le sovrapposizioni sono indicate come "voce1 + voce2" e
puoi rinominare le voci e regolare la frequenza di controllo (32–256 ms).

Nota per i revisori: la connessione WebSocket a ws://127.0.0.1 è intenzionale e
locale; su Firefox va abilitato `network.websocket.allowInsecureFromHTTPS` in
about:config prima dell'uso. I permessi sono limitati a YouTube e al backend
locale.

### Categorie / Categorie
Video, Productivity

### Campo "Come viene usato / User experience"
Da inserire (per il sondaggio obbligatorio AMO):

"L'utente apre il popup, preme 'Avvia rilevamento' e vede la lista delle voci
rilevate con lo stato corrente. Regola il volume di ogni voce con gli slider.
Tutte le elaborazioni avvengono in locale, su un backend Python avviato
dall'utente."

### Nota tecnica aggiuntiva (per la scheda di revisione)

"AVVISO DELLA REVISIONE — Configurazione manuale richiesta: questo componente
usa una WebSocket verso localhost (127.0.0.1). Firefox, di default, blocca le
connessioni ws:// insicure da pagine HTTPS. Per l'uso è necessario impostare
`network.websocket.allowInsecureFromHTTPS = true` in about:config. Questo è un
requisito documentato del componente aggiuntivo."