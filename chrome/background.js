// Voice Live - background service worker (Chrome MV3).
// Offre sempre un ricevitore per browser.runtime.sendMessage del content script
// quando il popup e' chiuso (evita "Receiving end does not exist").
chrome.runtime.onMessage.addListener((msg) => {
  // nessuna risposta richiesta: i messaggi verso il popup sono informativi
});