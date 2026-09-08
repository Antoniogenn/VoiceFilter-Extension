// Voice Live - content script per YouTube
// Collega l'audio del video a un AudioWorkletNode (pass-through via backend):
//   1. cattura l'audio del <video> in chunk da 512 campioni mono
//   2. li manda al backend locale 127.0.0.1:8765 via WebSocket
//   3. riceve "now"/"voices" dal backend e li propaga a popup/worklet

const SAMPLE_RATE = 16000;
const DEFAULT_HOST = "127.0.0.1:8765";

function wsUrl(host) {
  const h = (host || DEFAULT_HOST).trim().replace(/^ws:\/\//i, "").replace(/\/ws$/, "");
  return `ws://${h}/ws`;
}

let audioCtx = null;
let source = null;
let node = null;
let workletReady = false;
let ws = null;
let wsOK = false;
let wsStarted = false;  // il "start" (reset sessione) si manda solo al primo open
let currentHost = DEFAULT_HOST;
let active = false;
let lastVoices = null;   // ultima lista voci ricevuta dal backend
let lastNow = null;      // ultimo speaker emesso dal backend

function getVideo() {
  return document.querySelector("video");
}

function setActive(v) {
  active = v;
  browser.storage.local.set({ vlActive: v });
}

function status(text) {
  browser.runtime.sendMessage({ type: "status", text });
}

function setNow(speaker) {
  lastNow = speaker;
  browser.runtime.sendMessage({ type: "now", speaker });
  if (node) node.port.postMessage({ type: "now", speaker });
}

function ensureWS() {
  const url = wsUrl(currentHost);
  while (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    if (ws.url === url) return true;
    try { ws.close(); } catch (e) {}
    ws = null;
    wsStarted = false;
    lastVoices = null;
    lastNow = null;
  }
  try {
    ws = new WebSocket(url);
    wsOK = false;
    ws.onopen = () => {
      wsOK = true;
      if (!wsStarted) {
        wsStarted = true;
        ws.send(JSON.stringify({ type: "start" }));
        // sessione backend fresca: allinea subito la UI alla collezione vuota
        browser.runtime.sendMessage({ type: "voices", voices: [] });
        browser.runtime.sendMessage({ type: "now", speaker: null });
        status("backend: collegato");
      }
      ws.send(JSON.stringify({ type: "audio", rate: SAMPLE_RATE }));
    };
    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.type === "now") setNow(msg.speaker);
      else if (msg.type === "overlap") {
        browser.runtime.sendMessage({ type: "overlap", speakers: msg.speakers });
        if (node) node.port.postMessage({ type: "overlap", speakers: msg.speakers });
      } else if (msg.type === "voices") {
        lastVoices = msg.voices;
        browser.runtime.sendMessage({ type: "voices", voices: msg.voices });
      } else if (msg.type === "status") status(msg.text);
    };
    ws.onclose = () => { if (wsOK) status("backend: disconnesso (riavvia il server)"); wsOK = false; };
    ws.onerror = () => status(`backend: non raggiungibile su ${url} — avvia il backend`);
    return true;
  } catch (err) {
    status("backend: errore WS " + err.message);
    return false;
  }
}

async function ensureContext() {
  const video = getVideo();
  if (!video) { status("Nessun video"); return false; }
  try {
    if (!audioCtx) {
      audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
      source = audioCtx.createMediaElementSource(video);
    }
    if (audioCtx.state === "suspended") await audioCtx.resume();
    if (!workletReady) {
      const url = browser.runtime.getURL("worklet.js");
      await audioCtx.audioWorklet.addModule(url);
      workletReady = true;
    }
    if (!node) {
      node = new AudioWorkletNode(audioCtx, "voice-live-processor", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [2],
      });
      source.connect(node);
      node.connect(audioCtx.destination);
      node.port.onmessage = (e) => {
        if (e.data.type === "audio") {
          if (ws && ws.readyState === WebSocket.OPEN) ws.send(e.data.samples);
        } else if (e.data.type === "status") {
          console.log("[voice-live]", e.data.text);
          status(e.data.text);
        }
      };
      status("Graph collegato");
    }
    return true;
  } catch (err) {
    console.error("voice-live ensureContext:", err);
    status("Errore: " + err.message);
    return false;
  }
}

function startF() {
  ensureContext().then(ok => {
    if (!ok) { status("Nessun video trovato"); return; }
    if (!ensureWS()) return;
    // riavvio dopo uno stop: il WS è ancora aperto, quindi ri-attiva l'audio
    // sul backend (che altrimenti era rimasto con audio_on=False dallo stop).
    // NON si rimanda "start": azzererebbe il catalogo delle voci rilevate.
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "audio", rate: SAMPLE_RATE }));
    setActive(true);
    node.port.postMessage({ type: "start" });
    status("Rilevamento attivo");
  });
}

function stopF() {
  setActive(false);
  if (node) node.port.postMessage({ type: "stop" });
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop" }));
  setNow("— nessuno —");
}

browser.runtime.onMessage.addListener((msg) => {
  if (msg.type === "start") startF();
  if (msg.type === "stop") stopF();
  if (msg.type === "get-voices") {
    if (lastVoices) browser.runtime.sendMessage({ type: "voices", voices: lastVoices });
    if (lastNow) browser.runtime.sendMessage({ type: "now", speaker: lastNow });
    browser.runtime.sendMessage({ type: "state", active });
  }
  if (msg.type === "set-level") {
    if (node) node.port.postMessage({ type: "set-level", name: msg.name, level: msg.level });
  }
  if (msg.type === "set-weight") {
    if (node) node.port.postMessage({ type: "set-weight", weight: msg.weight });
  }
  if (msg.type === "set-heartbeat") {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "heartbeat", ms: msg.ms }));
    }
  }
  if (msg.type === "set-host") {
    currentHost = (msg.host || DEFAULT_HOST).trim();
    browser.storage.local.set({ wsHost: currentHost });
    wsStarted = false;
    lastVoices = null;
    lastNow = null;
    if (ws) { try { ws.onclose = null; ws.close(); } catch (e) {} ws = null; }
    status(`backend -> ${currentHost}`);
    if (active) startF();
  }
  if (msg.type === "pin" || msg.type === "unpin") {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: msg.type, name: msg.name }));
    }
  }
  if (msg.type === "clear-voices") {
    lastVoices = null;
    lastNow = null;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "start" }));
    browser.runtime.sendMessage({ type: "voices", voices: [] });
    browser.runtime.sendMessage({ type: "now", speaker: "— nessuno —" });
    status("Backend: catalogo voci azzerato");
  }
});

browser.storage.local.get({ wsHost: DEFAULT_HOST }).then(({ wsHost }) => {
  currentHost = (wsHost || DEFAULT_HOST).trim();
});