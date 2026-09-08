// Voice Live - AudioWorkletProcessor
// Versione backend: niente analisi nel browser (che falliva: 0 o 113 voci spurie).
//   - fa il pass-through dell'audio del video (con gain per il muting per-voce)
//   - estrae chunk monocanale da 512 campioni (32 ms a 16 kHz) e li manda al
//     content script -> backend 127.0.0.1:8765 via WebSocket per la diarizzazione.

const CHUNK = 512;   // campioni per chunk inviato al backend (atteso da Silero)

class VoiceLiveProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.active = false;
    this.buf = new Float32Array(CHUNK);
    this.used = 0;
    this.gain = 1.0;        // gain applicato al pass-through (istantaneo)
    this.smooth = 1.0;
    this.speaker = null;
    this.overlap = null;    // voci sovrapposte (audio a volume pieno)
    this.levels = {};       // nome voce -> livello (0..1), default 1.0

    this.port.onmessage = (e) => {
      const d = e.data;
      switch (d.type) {
        case "start":
          this.active = true;
          this.port.postMessage({ type: "status", text: "Rilevamento attivo" });
          break;
        case "stop":
          this.active = false;
          this.speaker = null;
          this.overlap = null;
          this.port.postMessage({ type: "now", speaker: "— nessuno —" });
          break;
        case "set-level": {
          const v = Number(d.level);
          this.levels[d.name] = Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : 1;
          this.port.postMessage({ type: "status", text: `livello ${d.name} -> ${Math.round(this.levels[d.name] * 100)}%` });
          break;
        }
        case "set-weight":
          // slider di compatibilità: agisce come attenuazione master (0..2)
          this.smooth = Math.max(0, Math.min(2, Number(d.weight) || 1));
          break;
        case "now":
          this.speaker = d.speaker;
          this.overlap = null;
          this.port.postMessage({ type: "status", text: `now ${d.speaker}` });
          break;
        case "overlap":
          this.speaker = null;
          this.overlap = d.speakers || [];
          this.port.postMessage({ type: "status", text: `overlap: ${this.overlap.join(" + ")}` });
          break;
      }
    };
  }

  _emitAudio() {
    // copia i campioni monocanale accumulati e li passa al thread principale
    const out = new Float32Array(this.used);
    out.set(this.buf.subarray(0, this.used));
    this.port.postMessage({ type: "audio", samples: out.buffer }, [out.buffer]);
    this.used = 0;
  }

  process(inputs, outputs) {
    const ch = inputs[0] && inputs[0][0];

    // pass-through con gain lisciato (livello per voce).
    // In sovrapposizione (due voci insieme nel mix) non e' possibile isolare
    // una singola voce: si applica il livello piu' basso tra quelli delle voci
    // presenti, cosi' una voce da attenuare resta attenuata anche se il mix
    // contiene un'altra voce.
    let level;
    if (this.overlap) {
      level = 1.0;
      for (const s of this.overlap) {
        if (this.levels[s] != null) level = Math.min(level, this.levels[s]);
      }
    } else {
      level = (this.speaker && this.levels[this.speaker] != null) ? this.levels[this.speaker] : 1.0;
    }
    const target = level * this.smooth;
    if (this.speaker && this.levels[this.speaker] != null && !this.overlap) {
      // voce rilevata: attenuazione istantanea
      this.gain = target;
    } else {
      // nessuna voce rilevata: ripristino morbido del volume (come prima)
      this.gain += (target - this.gain) * 0.12;
    }
    const g = this.gain;
    const outs = outputs[0];
    for (let j = 0; j < outs.length; j++) {
      const out = outs[j];
      const src = inputs[0] && inputs[0][j] ? inputs[0][j] : ch;
      if (!src) continue;
      if (g === 1.0) out.set(src);
      else for (let i = 0; i < out.length; i++) out[i] = src[i] * g;
    }

    // invio a chunk da CHUNK campioni (downmix dei canali)
    if (this.active && ch) {
      for (let i = 0; i < ch.length; i++) {
        this.buf[this.used++] = ch[i];
        if (this.used >= CHUNK) this._emitAudio();
      }
    }
    return true;
  }
}

registerProcessor("voice-live-processor", VoiceLiveProcessor);