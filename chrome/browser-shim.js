// Voice Live - shim di compatibilita' browser.* (promise) su chrome.* (MV3).
// Caricato PRIMA di popup.js e di content/youtube-live.js.
(function () {
  if (typeof globalThis.browser !== "undefined" && globalThis.browser.runtime) return;
  const c = chrome;

  // chrome.runtime.sendMessage non ha errori utili qui: i messaggi del content
  // script verso il popup sono informativi (status/now/voices) e possono
  // arrivare a popup chiuso -> risolviamo sempre, senza rejection rumoriose.
  const sendRuntime = (msg) =>
    new Promise((resolve) => {
      c.runtime.sendMessage(msg, () => { void c.runtime.lastError; resolve(); });
    });

  // tabs.sendMessage: il popup gestisce gia' gli errori con .catch().
  const sendTab = (id, msg) =>
    new Promise((resolve, reject) => {
      c.tabs.sendMessage(id, msg, (resp) => {
        const err = c.runtime.lastError;
        if (err) reject(new Error(err.message));
        else resolve(resp);
      });
    });

  const storageGet = (defaults) =>
    new Promise((resolve) => c.storage.local.get(defaults, resolve));
  const storageSet = (items) =>
    new Promise((resolve) => c.storage.local.set(items, resolve));
  const storageRemove = (keys) =>
    new Promise((resolve) => c.storage.local.remove(keys, resolve));

  globalThis.browser = {
    storage: {
      local: { get: storageGet, set: storageSet, remove: storageRemove },
    },
    runtime: {
      getURL: (p) => c.runtime.getURL(p),
      sendMessage: sendRuntime,
      onMessage: {
        addListener: (cb) => c.runtime.onMessage.addListener(cb),
      },
    },
    tabs: {
      query: (q) => new Promise((resolve) => c.tabs.query(q, resolve)),
      sendMessage: sendTab,
    },
  };
})();