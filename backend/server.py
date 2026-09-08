#!/usr/bin/env python3
"""Voice Live - backend di diarizzazione in streaming.

Riceve l'audio del video via WebSocket (Float32 PCM mono, rate concordato con
il messaggio `audio`), accumula gli interventi di parlato (VAD Silero) e per
ogni intervento calcola l'embedding vocale ECAPA-TDNN. L'embedding viene
confrontato (coseno) col catalogo delle voci note: combacia -> aggiorna la voce;
altrimenti si conferma un candidato su piu' interventi prima di crearne una
nuova. Se due voci note si sovrappongono (coppia riconosciuta via top-2 o
residuo della voce dominante) si emette `overlap` e si lasciano invariati i
profili (mai aggiornati con l'embedding di un mix).

Protocollo (testo JSON da client a server):
  {"type":"start"}                      azzera la sessione
  {"type":"audio","rate":16000}         attiva la modalita' audio
  {"type":"heartbeat","ms":64}          cambia il ritempo del ricontrollo
  frame binari raw Float32 LE           l'audio vero e proprio
  {"type":"stop"}                       ferma l'audio

Messaggi (server -> client):
  {"type":"now","speaker":"voce1"}      voce attiva (null = voce non identificata)
  {"type":"overlap","speakers":[...]}   due voci note sovrapposte nel mix
  {"type":"voices","voices":[{name,count}]}
  {"type":"status","text":"..."}
"""
import argparse
import asyncio
import json
import sys
import time

import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="Voice Live backend")
SR = 16000
SILERO_WIN = 512            # campioni che il VAD Silero processa ad ogni chiamata

# speech segmentation
MIN_UTT_S = 0.4             # intervento minimo per l'embedding
EMBED_MIN_S = 0.3           # sotto questa durata l'embedding e' troppo scarso
LONG_UTT_S = 1.2            # oltre questa durata si chiude e si classifica a pezzi
SILENCE_END_S = 0.25        # pausa che chiude un intervento
HEARTBEAT_S = 0.064          # ritempo del ricontrollo "chi parla adesso" (64 ms)
RING_S = 0.5              # finestra di audio vocale usata dal heartbeat

# docking (calibrato su video con musica: coseni piu' bassi, voci slide/perse)
MATCH = 0.35                # coseno embedding >= MATCH -> stessa voce nota
NEW_MATCH = 0.30            # coerenza tra interventi del candidato
CONFIRM = 2                 # interventi coerenti per creare una nuova voce
HOLD_S = 1.0                # una voce rilevata resta attiva 1 s dall'ultimo match
OVERLAP_MIN = 0.30          # soglia minima per considerare una voce "presente" nel mix
OVERLAP_GAP = 0.15          # se top-1 e top-2 sono vicini -> le voci si sovrappongono
RESIDUAL_MIN = 0.40         # coseno del residuo (dopo la voce dominante) per la 2a voce
RESIDUAL_NORM_MIN = 0.20    # modulo minimo del residuo per fidarsi della sua direzione

# retention: le voci che non vengono rilevate da VOICE_TTL_S vengono rimosse dal
# catalogo (gli ospiti che vanno via spariscono; chi torna dopo e' una nuova voce).
VOICE_TTL_S = 300           # 5 min dall'ultimo intervento -> la voce viene cancellata
PRUNE_INTERVAL_S = 5        # cadenza con cui il task di pulizia rileva le scadenze

_encoder = None
_encoder_device = "cpu"
_vad = None


def load_encoder():
    global _encoder
    if _encoder is None:
        from speechbrain.inference.speaker import EncoderClassifier
        _encoder = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="/tmp/speechbrain_ecapa",
            run_opts={"device": _encoder_device},
        )
    return _encoder


def load_vad():
    """Silero VAD istantaneo (stesso modello usato da faster-whisper)."""
    global _vad
    if _vad is None:
        from silero_vad import load_silero_vad
        _vad = load_silero_vad()
    return _vad


class SpeakerCatalog:
    def __init__(self):
        self.by_label = {}   # label -> {"embed": np.ndarray, "count": int}

    def match(self, embed):
        """Best cosine con le voci note. Ritorna (label|None, cos). Non crea nulla."""
        best_label, best_cos = None, -1.0
        for lab, v in self.by_label.items():
            c = float(np.dot(v["embed"], embed))
            if c > best_cos:
                best_cos, best_label = c, lab
        return best_label, best_cos

    def top2(self, embed):
        """Top-2 per coseno. Ritorna (best_label, best_cos, second_label, second_cos)."""
        best = (None, -1.0)
        sec = (None, -1.0)
        for lab, v in self.by_label.items():
            c = float(np.dot(v["embed"], embed))
            if c > best[1]:
                sec, best = best, (lab, c)
            elif c > sec[1]:
                sec = (lab, c)
        return best[0], best[1], sec[0], sec[1]

    def update(self, label, embed):
        v = self.by_label[label]
        v["count"] += 1
        v["embed"] = v["embed"] * (v["count"] - 1) / v["count"] + embed / v["count"]
        v["embed"] /= np.linalg.norm(v["embed"])
        v["last_seen"] = time.monotonic()

    def residual_top(self, embed, exclude_label):
        """Direzione residua di `embed` dopo aver tolto la voce dominante.

        Se l'embedding e' il mix di due voci, `embed - (embed·v1)v1` punta verso
        v2 anche quando una delle due domina: l'output (label, cos, |residuo|)
        permette di riconoscere la seconda voce. Residuo sotto
        RESIDUAL_NORM_MIN -> la direzione e' rumore (voce singola)."""
        v = self.by_label[exclude_label]["embed"]
        c = float(np.dot(embed, v))
        r = embed - c * v
        rn = float(np.linalg.norm(r))
        if rn < RESIDUAL_NORM_MIN:
            return None, -1.0, rn
        ru = r / (rn + 1e-8)
        best_label, best_cos = None, -1.0
        for lab, o in self.by_label.items():
            if lab == exclude_label:
                continue
            cc = float(np.dot(ru, o["embed"]))
            if cc > best_cos:
                best_cos, best_label = cc, lab
        return best_label, best_cos, rn

    def add(self, embed):
        nums = []
        for lab in self.by_label:
            try:
                nums.append(int(lab[len("voce"):]))
            except (ValueError, TypeError):
                pass
        num = (max(nums) + 1) if nums else 1
        label = f"voce{num}"
        self.by_label[label] = {"embed": embed, "count": 1, "last_seen": time.monotonic()}
        return label

    def prune(self, ttl, pinned=()):
        """Rimuove le voci inattive da piu' di ttl secondi, tranne quelle protette.
        Ritorna i nomi rimossi."""
        pinned = set(pinned)
        now = time.monotonic()
        stale = [k for k, v in self.by_label.items()
                 if k not in pinned
                 and v.get("last_seen") is not None
                 and now - v["last_seen"] > ttl]
        for k in stale:
            del self.by_label[k]
        return stale


class StreamSession:
    """Stato di una connessione WebSocket."""

    def __init__(self, rate=SR):
        self.rate = rate
        self.buf = np.zeros(0, dtype=np.float32)
        self.utt = np.zeros(0, dtype=np.float32)
        self.sil_wins = 0                # finestre Silero consecutive senza voce
        self.ring = np.zeros(0, dtype=np.float32)   # audio vocale recente (sliding)
        self.last_beat = None            # monotonic al beat +HEARTBEAT_S
        self.heartbeat_s = HEARTBEAT_S   # intervallo heartbeat corrente (ms/1000)
        self.catalog = SpeakerCatalog()
        self.candidate = None            # {"embed", "hits"}
        self.voices = {}                 # label -> conteggio interventi emessi
        self.pinned = set()              # label protette dalla rimozione automatica
        self.last_label = None
        self.ws = None
        self.vad = None                  # modello silero (lazy)
        self.vad_warned = False          # log errore VAD una sola volta
        self.beat_label = None           # label emessa dall'ultimo heartbeat (evita spam)
        self.beat_at = None              # monotonic dell'ultimo match (hold 1 s)
        self.overlap = None              # (b1, b2) se l'ultimo intervento era un mix

    def push(self, raw):
        self.buf = np.concatenate([self.buf, np.frombuffer(raw, dtype=np.float32)])

    def take(self, n):
        n = min(n, self.buf.size)
        out = self.buf[:n]
        self.buf = self.buf[n:]
        return out

    def _silero_speech(self, x):
        import torch
        if self.vad is None:
            self.vad = load_vad()
        try:
            p = float(self.vad(torch.from_numpy(x).float(), self.rate).item())
            return p > 0.5
        except Exception:
            # un VAD rotto non deve far passare TUTTO come parlato (inquinerebbe
            # catalog e utt). Tratta l'errore come silenzio e logga una sola volta.
            if not self.vad_warned:
                print("VAD: errore, trattato come silenzio", file=sys.stderr)
                self.vad_warned = True
            return False


def embed_window(model, x):
    if len(x) < EMBED_MIN_S * SR:
        return None
    import torch
    t = torch.from_numpy(x).float().unsqueeze(0)
    with torch.no_grad():
        e = model.encode_batch(t).squeeze().cpu().numpy()
    n = np.linalg.norm(e)
    return e / (n + 1e-8)


def detect_overlap(catalog, embed):
    """Ritorna (a, b) se `embed` sembra il mix di due voci note, altrimenti None.

    Due strade complementari:
      1) top-1 e top-2 entrambe sopra OVERLAP_MIN e vicine (OVERLAP_GAP):
         mix a volumi simili.
      2) la voce dominante lascia un residuo che punta forte a un'altra voce
         nota: mix sbilanciato in cui top-2 fallirebbe.
    Nella direzione residuale chiediamo RESIDUAL_MIN (piu' stringente: in uno
    spazio ad alta dimensione un residuo casuale ha coseni tipici ~1/sqrt(dim))."""
    b1, c1, b2, c2 = catalog.top2(embed)
    if b1 is None or c1 < OVERLAP_MIN:
        return None
    if b2 is not None and c2 >= OVERLAP_MIN and (c1 - c2) <= OVERLAP_GAP:
        return (b1, b2)
    rb, rc, rn = catalog.residual_top(embed, b1)
    if rn >= RESIDUAL_NORM_MIN and rb is not None and rc >= RESIDUAL_MIN:
        return (b1, rb)
    return None


class Pipeline:
    """Eseguono su thread: l'embedding ECAPA é un'operazione CPU bloccante."""

    async def classify(self, model, x, sess):
        embed = await asyncio.to_thread(embed_window, model, x)
        if embed is None:
            return None

        # 0) sovrapposizione di due voci note: embedding del mix. Non apriamo un
        #    candidato spurio e NON aggiorniamo i profili con il mix (li
        #    inquinerebbe). L'indicatore terra' il b1 via "overlap".
        ov = detect_overlap(sess.catalog, embed)
        if ov is not None:
            sess.overlap = ov
            return ov[0]

        cand = sess.candidate
        # 1) match con le voci note
        b1, c1 = sess.catalog.match(embed)
        if b1 is not None and c1 >= MATCH:
            sess.catalog.update(b1, embed)
            return b1

        # 2) se il candidato esiste e coincide da CONFIRM intervalli -> nuova voce.
        if cand is not None:
            c = float(np.dot(cand["embed"], embed))
            if c >= NEW_MATCH:
                hits = cand["hits"] + 1
                cand["embed"] = (cand["embed"] * cand["hits"] + embed) / hits
                cand["embed"] /= np.linalg.norm(cand["embed"])
                cand["hits"] = hits
                if hits >= CONFIRM:
                    # anti-merge: controlla ancora con le voci note (potrebbero
                    # essere cresciute nel frattempo)
                    bl2, bc2 = sess.catalog.match(cand["embed"])
                    if bl2 is not None and bc2 >= MATCH:
                        sess.catalog.update(bl2, embed)
                        sess.candidate = None
                        return bl2
                    new_label = sess.catalog.add(cand["embed"])
                    sess.candidate = None
                    return new_label
                return None
            # candidato non coerente: riparti
            sess.candidate = {"embed": embed, "hits": 1}
            return None

        # 3) nessun match, nessun candidato coerente: apri un candidato
        sess.candidate = {"embed": embed, "hits": 1}
        return None


async def notify(sess, msg):
    if sess.ws is not None:
        await sess.ws.send_text(json.dumps(msg, ensure_ascii=False))


def make_voices_msg(sess):
    return {"type": "voices", "voices": [
        {"name": k, "count": v, "pinned": k in sess.pinned}
        for k, v in sess.voices.items()
    ]}


async def prune_stale(sess):
    """Rimuove periodicamente le voci che non vengono rilevate da VOICE_TTL_S.

    L'ospite che va via sparisce dal catalogo e dalla lista voci; se rientra
    dopo il TTL verra' trattato come una nuova voce. Le voci protette (pinned)
    non vengono mai rimosse. Dopo ogni pulizia aggiorna il client.
    """
    try:
        while True:
            await asyncio.sleep(PRUNE_INTERVAL_S)
            removed = sess.catalog.prune(VOICE_TTL_S, sess.pinned)
            if removed:
                for k in removed:
                    sess.voices.pop(k, None)
                print(f"[prune] rimosse {len(removed)} voci: {removed}", flush=True)
                await notify(sess, make_voices_msg(sess))
    except asyncio.CancelledError:
        pass


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    model = await asyncio.to_thread(load_encoder)
    pipe = Pipeline()
    sess = StreamSession()
    sess.ws = ws
    audio_on = False
    prune_task = None

    def restart_prune():
        """(Ri)avvia il task di pulizia sul catalogo corrente della sessione."""
        nonlocal prune_task
        if prune_task is not None:
            prune_task.cancel()
        prune_task = asyncio.create_task(prune_stale(sess))

    restart_prune()
    await notify(sess, {"type": "status", "text": "backend: pronto"})
    try:
        while True:
            msg = await ws.receive()
            mtype = msg.get("type")
            if mtype == "websocket.disconnect":
                break
            if mtype == "websocket.receive":
                if "text" in msg:
                    data = json.loads(msg["text"])
                    t = data.get("type")
                    if t == "start":
                        sess = StreamSession()
                        sess.ws = ws
                        audio_on = False
                        restart_prune()
                        await notify(sess, {"type": "status", "text": "backend: sessione azzerata"})
                    elif t == "audio":
                        sess.rate = int(data.get("rate", SR))
                        audio_on = True
                    elif t == "stop":
                        audio_on = False
                    elif t == "heartbeat":
                        ms = int(data.get("ms", 64))
                        ms = max(32, min(1024, ms // 32 * 32))
                        sess.heartbeat_s = ms / 1000.0
                        sess.last_beat = None
                    elif t == "pin":
                        sess.pinned.add(data.get("name"))
                        await notify(sess, make_voices_msg(sess))
                    elif t == "unpin":
                        sess.pinned.discard(data.get("name"))
                        await notify(sess, make_voices_msg(sess))
                elif "bytes" in msg and audio_on:
                    for m in await feed_audio(sess, pipe, model, msg["bytes"]):
                        await notify(sess, m)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # non far morire il loop WS
        try:
            await notify(sess, {"type": "status", "text": f"backend: errore {e}"})
        except Exception:
            pass
    finally:
        if prune_task is not None:
            prune_task.cancel()
        sess.ws = None


async def handle_utt(sess, pipe, model, utt):
    if len(utt) < MIN_UTT_S * SR:
        return []
    label = await pipe.classify(model, utt, sess)
    if label is None:
        # intervento non attribuito (candidato in corso): una voce sconosciuta
        # e' stata rilevata -> la voce nota precedente cede subito a null.
        if sess.beat_label is not None:
            sess.beat_label = None
            sess.beat_at = None
            return [{"type": "now", "speaker": None}]
        return []
    sess.last_label = label
    sess.beat_label = label
    sess.beat_at = time.monotonic()
    voices_msg = make_voices_msg(sess)
    if sess.overlap is not None:
        out = [{"type": "overlap", "speakers": list(sess.overlap)}, voices_msg]
        sess.overlap = None
        return out
    sess.voices[label] = sess.voices.get(label, 0) + 1
    voices_msg = make_voices_msg(sess)
    return [{"type": "now", "speaker": label}, voices_msg]


SILENCE_END_WINS = int(SILENCE_END_S / (SILERO_WIN / SR)) + 1


async def beat_now(sess, pipe, model):
    """Rilegge ogni HEARTBEAT_S chi parla: embedding del solo audio vocale
    recente (RING_S), match col catalogo. Emette now/overlap quando la voce
    cambia; altrimenti non spamma. Le nuove voci nascono solo dal percorso a
    interventi."""
    if sess.ring.size < EMBED_MIN_S * SR:
        return []
    embed = await asyncio.to_thread(embed_window, model, sess.ring)
    if embed is None:
        return []
    now = time.monotonic()
    # sovrapposizione di due voci note: rilevato come il mix. Emettiamo solo
    # "overlap" (il worklet tiene l'audio a volume pieno); NON segue "now",
    # che azzererebbe lo stato di sovrapposizione nel worklet. I profili non
    # vengono aggiornati con l'embedding del mix (li inquinerebbe).
    ov = detect_overlap(sess.catalog, embed)
    if ov is not None:
        if sess.beat_label != ov:
            sess.beat_label = ov
            sess.beat_at = now
            sess.last_label = ov[0]
            return [{"type": "overlap", "speakers": list(ov)}]
        return []
    b1, c1 = sess.catalog.match(embed)
    # continuita' dell'overlap: se eravamo in overlap (a,b) e la voce dominante
    # resta a mentre il residuo punta ancora a b, NON usciamo dall'overlap.
    # Evita lo stutter now/overlap quando il mix oscilla appena sotto le soglie
    # (e la conseguente attenuazione errata di una voce che parla ancora).
    prev = sess.beat_label
    if isinstance(prev, tuple) and b1 == prev[0] and c1 >= MATCH:
        rb, rc, rn = sess.catalog.residual_top(embed, b1)
        if rn >= RESIDUAL_NORM_MIN * 0.5 and rb == prev[1] and rc >= RESIDUAL_MIN * 0.75:
            sess.beat_at = now
            return []
    if b1 is not None and c1 >= MATCH:
        sess.last_label = b1
        sess.beat_at = now
        if sess.beat_label != b1:
            sess.beat_label = b1
            return [{"type": "now", "speaker": b1}]
        return []
    # nessuna voce nota in questa finestra. La voce agganciata resta attiva
    # per HOLD_S dall'ultimo rilevamento: evita di perderla durante micro-pause
    # o brevi finestre miste. Dopo HOLD_S senza match passa a null (voce
    # sconosciuta -> volume pieno). Una voce nota diversa cambia subito sopra.
    if sess.beat_label is not None:
        if sess.beat_at is not None and now - sess.beat_at < HOLD_S:
            return []
        sess.beat_label = None
        sess.beat_at = None
        return [{"type": "now", "speaker": None}]
    return []


async def feed_audio(sess, pipe, model, raw):
    """Consuma un frame binario. Ritorna i messaggi da inviare al client."""
    sess.push(raw)
    out = []
    # allinea il buffer a finestre Silero da SILERO_WIN campioni
    n = SILERO_WIN
    while sess.buf.size >= n:
        x = sess.take(n)
        if sess._silero_speech(x):
            sess.utt = np.concatenate([sess.utt, x])
            sess.ring = np.concatenate([sess.ring, x])[-int(RING_S * SR):]
            sess.sil_wins = 0
            if sess.utt.size >= LONG_UTT_S * sess.rate:
                out += await handle_utt(sess, pipe, model, sess.utt)
                sess.utt = np.zeros(0, dtype=np.float32)
                sess.sil_wins = 0
        elif sess.utt.size:
            # pausa: accumula finche' non e' abbastanza lunga da chiudere
            sess.sil_wins += 1
            if sess.sil_wins >= SILENCE_END_WINS:
                out += await handle_utt(sess, pipe, model, sess.utt)
                sess.utt = np.zeros(0, dtype=np.float32)
                sess.sil_wins = 0
        # heartbeat: ricontrolla "chi parla adesso" ogni sess.heartbeat_s
        now = time.monotonic()
        if sess.last_beat is None or now - sess.last_beat >= sess.heartbeat_s:
            sess.last_beat = now
            out += await beat_now(sess, pipe, model)
    return out


def main():
    global _encoder_device
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()
    _encoder_device = args.device
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()