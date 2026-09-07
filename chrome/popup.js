const startBtn = document.getElementById("start");
const stopBtn = document.getElementById("stop");
const weightInput = document.getElementById("weight");
const nowEl = document.getElementById("now");
const voicesEl = document.getElementById("voices");
const heartbeatSel = document.getElementById("heartbeat");
const hostInput = document.getElementById("host");
const logEl = document.getElementById("log");

let detectedVoices = new Map();   // nome -> conteggio, mai rimossi
let levels = new Map();           // nome -> livello (0..1), default 1.0
let current = null;               // voce rilevata al momento (nome backend)
let displayNames = new Map();     // nome backend -> nome personalizzato
const rows = new Map();           // nome backend -> { dot, lbl }

function displayName(n) {
  return displayNames.get(n) || n;
}

function renderVoices() {
  const names = [...detectedVoices.keys()];
  if (names.length === 0) {
    voicesEl.textContent = "(nessuna voce ancora)";
    return;
  }
  voicesEl.innerHTML = "";
  for (const n of names) {
    const level = levels.has(n) ? levels.get(n) : 1.0;
    const row = document.createElement("div");
    row.className = "voice-row";
    const dot = document.createElement("span");
    dot.className = "dot";
    const lbl = document.createElement("span");
    lbl.className = "lbl";
    lbl.textContent = displayName(n);
    lbl.title = "Clicca per rinominare";
    lbl.onclick = (e) => {
      e.stopPropagation();
      const input = document.createElement("input");
      input.type = "text";
      input.className = "lbl-input";
      input.value = displayName(n);
      input.maxLength = 24;
      lbl.replaceWith(input);
      input.focus();
      const commit = (save) => {
        const v = input.value.trim();
        if (save && v) {
          displayNames.set(n, v);
          browser.storage.local.set({ displayNames: Object.fromEntries(displayNames) });
        }
        renderVoices();
      };
      input.onblur = () => commit(true);
      input.onkeydown = (ev) => {
        if (ev.key === "Enter") commit(true);
        if (ev.key === "Escape") commit(false);
      };
    };
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = 0;
    slider.max = 1;
    slider.step = 0.05;
    slider.value = level;
    slider.title = "Livello di questa voce (0 = muta solo questa)";
    const val = document.createElement("span");
    val.className = "val";
    val.textContent = Math.round(level * 100) + "%";
    slider.oninput = () => {
      const v = parseFloat(slider.value);
      levels.set(n, v);
      val.textContent = Math.round(v * 100) + "%";
      sendAll("set-level", { name: n, level: v });
      browser.storage.local.set({ levels: Object.fromEntries(levels) });
    };
    row.appendChild(dot);
    row.appendChild(lbl);
    row.appendChild(slider);
    row.appendChild(val);
    rows.set(n, { dot, lbl });
    voicesEl.appendChild(row);
  }
  markCurrent();
}

function markCurrent() {
  if (current === "— nessuno —" || !current) {
    for (const { dot } of rows.values()) dot.classList.remove("on");
    return;
  }
  for (const [n, { dot, lbl }] of rows) {
    if (n === current) {
      dot.classList.add("on");
      lbl.textContent = `${displayName(n)} (${detectedVoices.get(n)}×)`;
    } else {
      dot.classList.remove("on");
    }
  }
}

function log(text) {
  const line = "[" + new Date().toLocaleTimeString() + "] " + text;
  console.log("[voice-live popup]", line);
  logEl.textContent += "\n" + line;
  logEl.scrollTop = logEl.scrollHeight;
}

function send(type, payload = {}) {
  browser.tabs.query({ active: true, currentWindow: true }).then(tabs => {
    if (tabs[0] && tabs[0].id != null) {
      browser.tabs.sendMessage(tabs[0].id, { type, ...payload }).catch(e => log("errore invio: " + e.message));
    } else {
      log("nessuna tab attiva");
    }
  });
}

function sendAll(type, payload = {}) {
  browser.tabs.query({}).then(tabs => {
    for (const t of tabs) {
      if (t.id == null) continue;
      browser.tabs.sendMessage(t.id, { type, ...payload }).catch(() => {});
    }
  });
}

startBtn.onclick = () => { send("start"); startBtn.disabled = true; stopBtn.disabled = false; };
stopBtn.onclick = () => { send("stop"); startBtn.disabled = false; stopBtn.disabled = true; };
document.getElementById("clear").onclick = () => {
  detectedVoices.clear();
  current = null;
  browser.storage.local.remove(["levels", "displayNames"]);
  browser.storage.local.set({ levels: {}, displayNames: {} });
  sendAll("clear-voices");
  renderVoices();
  nowEl.textContent = "— nessuno —";
  log("Voci salvate cancellate");
};
weightInput.oninput = () => send("set-weight", { weight: parseFloat(weightInput.value) });
hostInput.onchange = () => {
  const v = hostInput.value.trim().replace(/^ws:\/\//, "").replace(/\/ws$/, "");
  hostInput.value = v;
  browser.storage.local.set({ wsHost: v });
  sendAll("set-host", { host: v });
  log(`backend -> ${v}`);
};
heartbeatSel.onchange = () => {
  const ms = parseInt(heartbeatSel.value, 10) || 64;
  send("set-heartbeat", { ms });
  log(`controlli ogni ${ms} ms`);
};

browser.runtime.onMessage.addListener((msg) => {
  if (msg.type === "status") log(msg.text || "");
  if (msg.type === "now") { nowEl.textContent = msg.speaker ? (displayNames.get(msg.speaker) || msg.speaker) : "— nessuno —"; current = msg.speaker || null; markCurrent(); }
  if (msg.type === "overlap") {
    current = null;
    for (const { dot } of rows.values()) dot.classList.remove("on");
    for (const n of (msg.speakers || [])) {
      const row = rows.get(n);
      if (row) row.dot.classList.add("on");
    }
    nowEl.textContent = (msg.speakers || []).map(n => displayNames.get(n) || n).join(" + ");
  }
  if (msg.type === "voices") {
    const list = msg.voices || [];
    const names = new Set(list.map(v => v.name));
    for (const n of [...detectedVoices.keys()]) {
      if (!names.has(n)) detectedVoices.delete(n);
    }
    for (const v of list) detectedVoices.set(v.name, v.count || 1);
    renderVoices();
  }
  if (msg.type === "state") {
    startBtn.disabled = msg.active;
    stopBtn.disabled = !msg.active;
  }
});

browser.storage.local.get({ displayNames: {}, levels: {}, vlActive: false, wsHost: "127.0.0.1:8765" }).then(({ displayNames: savedNames, levels: savedLevels, vlActive, wsHost }) => {
  if (savedNames) for (const [k, v] of Object.entries(savedNames)) displayNames.set(k, v);
  if (savedLevels) {
    for (const [k, v] of Object.entries(savedLevels)) levels.set(k, v);
    for (const [k, v] of Object.entries(savedLevels)) sendAll("set-level", { name: k, level: v });
  }
  if (wsHost) hostInput.value = wsHost;
  startBtn.disabled = vlActive;
  stopBtn.disabled = !vlActive;
});

browser.tabs.query({ active: true, currentWindow: true }).then(tabs => {
  if (tabs[0] && tabs[0].id != null) {
    browser.tabs.sendMessage(tabs[0].id, { type: "get-voices" }).catch(() => {});
  }
});
