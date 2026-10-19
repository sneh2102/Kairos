"""Speech for the interview coach: speech-to-text and text-to-speech.

STT: faster-whisper on this PC (GPU if CUDA libs load, else CPU), or Groq's
free hosted Whisper. TTS: Kokoro (local ONNX), Edge voices (free, online), or
"browser" — no audio from here, the renderer speaks with speechSynthesis.

Models download on first use into DATA_DIR/models, never bundled.
"""
import asyncio
import logging
import tempfile
import threading
from pathlib import Path

import requests

import config
from config import CONFIG

MODELS_DIR = config.DATA_DIR / "models"
WHISPER_DIR = MODELS_DIR / "whisper"
KOKORO_DIR = MODELS_DIR / "kokoro"
KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
# int8 model is ~90MB vs ~310MB and runs faster on CPU with no audible loss
KOKORO_FILES = ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

DEFAULTS = {
    "stt_engine": "local",          # local | groq
    "whisper_model": "small.en",    # tiny.en | base.en | small.en | distil-large-v3 | large-v3-turbo
    "whisper_device": "auto",       # auto | cuda | cpu
    "groq_api_key": "",
    "tts_engine": "kokoro",         # kokoro | edge | browser
    "kokoro_voice": "af_heart",
    "edge_voice": "en-US-AndrewNeural",
    "tts_speed": 1.0,
}


def settings() -> dict:
    return {**DEFAULTS, **(CONFIG.get("interview") or {})}


# ---- model downloads --------------------------------------------------------

# what -> "downloading" | "error: ..." ; absent = idle
_downloads: dict[str, str] = {}


def whisper_ready(size: str) -> bool:
    from faster_whisper.utils import download_model
    try:
        download_model(size, local_files_only=True, cache_dir=str(WHISPER_DIR))
        return True
    except Exception:
        return False


def kokoro_ready() -> bool:
    return all((KOKORO_DIR / f).exists() for f in KOKORO_FILES)


def _download_kokoro():
    KOKORO_DIR.mkdir(parents=True, exist_ok=True)
    for name in KOKORO_FILES:
        dest = KOKORO_DIR / name
        if dest.exists():
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        with requests.get(f"{KOKORO_BASE}/{name}", stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        tmp.replace(dest)   # only a complete file ever counts as "ready"


def _download_whisper(size: str):
    from faster_whisper.utils import download_model
    download_model(size, cache_dir=str(WHISPER_DIR))


def start_download(what: str):
    """what = "kokoro" or "whisper:<size>". Runs in a thread; status() reports it."""
    if _downloads.get(what) == "downloading":
        return
    _downloads[what] = "downloading"   # set before the thread starts, so a double click can't start two

    def run():
        try:
            if what == "kokoro":
                _download_kokoro()
            else:
                _download_whisper(what.split(":", 1)[1])
            _downloads.pop(what, None)
        except Exception as e:
            logging.exception("model download failed: %s", what)
            _downloads[what] = f"error: {e}"

    threading.Thread(target=run, daemon=True).start()


def status() -> dict:
    s = settings()
    size = s["whisper_model"]
    return {
        "settings": {**s, "groq_api_key": bool(s["groq_api_key"])},
        "whisper": {"model": size, "ready": whisper_ready(size), "download": _downloads.get(f"whisper:{size}"),
                    "device": _whisper[1] if _whisper and _whisper[0] == size else None},
        "kokoro": {"ready": kokoro_ready(), "download": _downloads.get("kokoro")},
    }


# ---- speech to text ---------------------------------------------------------

_whisper: tuple[str, str, object] | None = None   # (size, device, WhisperModel)
_whisper_lock = threading.Lock()


def _load_whisper(size: str, want: str):
    from faster_whisper import WhisperModel
    from faster_whisper.utils import download_model
    path = download_model(size, cache_dir=str(WHISPER_DIR))
    devices = ["cuda", "cpu"] if want == "auto" else [want]
    last: Exception | None = None
    for dev in devices:
        try:
            m = WhisperModel(path, device=dev, compute_type="int8_float16" if dev == "cuda" else "int8")
            if dev == "cuda":
                # CUDA libs (cuBLAS/cuDNN) load lazily — a missing DLL only shows on
                # the first real decode, so probe with a second of silence now.
                import numpy as np
                list(m.transcribe(np.zeros(16000, dtype="float32"))[0])
            return dev, m
        except Exception as e:
            last = e
            logging.warning("whisper on %s unavailable: %s", dev, e)
    raise RuntimeError(f"Could not load Whisper: {last}")


def _whisper_model():
    global _whisper
    s = settings()
    size, want = s["whisper_model"], s["whisper_device"]
    with _whisper_lock:
        if not _whisper or _whisper[0] != size or (want != "auto" and _whisper[1] != want):
            if not whisper_ready(size):
                raise RuntimeError(f"Whisper model '{size}' isn't downloaded yet (Settings > Interview)")
            dev, m = _load_whisper(size, want)
            _whisper = (size, dev, m)
        return _whisper[2]


def _transcribe_local(path: Path) -> dict:
    model = _whisper_model()
    segments, info = model.transcribe(str(path), language="en", vad_filter=True, word_timestamps=True,
                                      beam_size=1)
    words, parts = [], []
    for seg in segments:
        parts.append(seg.text.strip())
        words += [{"w": w.word.strip(), "s": round(float(w.start), 2), "e": round(float(w.end), 2)} for w in seg.words or []]
    return {"text": " ".join(parts).strip(), "words": words, "duration": round(float(info.duration), 2)}


def _transcribe_groq(path: Path, key: str) -> dict:
    with open(path, "rb") as f:
        resp = requests.post(
            GROQ_URL, headers={"Authorization": f"Bearer {key}"}, timeout=60,
            files={"file": (path.name, f)},
            data={"model": "whisper-large-v3-turbo", "language": "en", "response_format": "verbose_json",
                  "timestamp_granularities[]": "word"},
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"Groq transcription failed ({resp.status_code}): {resp.text[:200]}")
    d = resp.json()
    words = [{"w": w["word"].strip(), "s": round(w["start"], 2), "e": round(w["end"], 2)} for w in d.get("words") or []]
    return {"text": d.get("text", "").strip(), "words": words, "duration": round(d.get("duration") or 0, 2)}


def transcribe(audio: bytes, suffix: str = ".webm") -> dict:
    """Returns {text, words: [{w, s, e}], duration}. Falls back local <-> Groq
    when the chosen engine fails and the other one is usable."""
    s = settings()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"answer{suffix}"
        path.write_bytes(audio)
        engines = ["groq", "local"] if s["stt_engine"] == "groq" else ["local", "groq"]
        last: Exception | None = None
        for eng in engines:
            if eng == "groq" and not s["groq_api_key"]:
                continue
            try:
                return _transcribe_groq(path, s["groq_api_key"]) if eng == "groq" else _transcribe_local(path)
            except Exception as e:
                last = e
                logging.warning("STT via %s failed: %s", eng, e)
        raise RuntimeError(str(last) if last else "No speech-to-text engine is set up")


# ---- text to speech ---------------------------------------------------------

_kokoro = None
_kokoro_lock = threading.Lock()


def kokoro_voices() -> list[str]:
    return sorted(_kokoro_engine().get_voices()) if kokoro_ready() else []


def _kokoro_engine():
    global _kokoro
    with _kokoro_lock:
        if _kokoro is None:
            if not kokoro_ready():
                raise RuntimeError("Kokoro voice model isn't downloaded yet (Settings > Interview)")
            from kokoro_onnx import Kokoro
            _kokoro = Kokoro(str(KOKORO_DIR / KOKORO_FILES[0]), str(KOKORO_DIR / KOKORO_FILES[1]))
        return _kokoro


def _tts_kokoro(text: str, s: dict) -> tuple[bytes, str]:
    import io
    import soundfile as sf
    samples, rate = _kokoro_engine().create(text, voice=s["kokoro_voice"], speed=float(s["tts_speed"]), lang="en-us")
    buf = io.BytesIO()
    sf.write(buf, samples, rate, format="WAV")
    return buf.getvalue(), "audio/wav"


def _tts_edge(text: str, s: dict) -> tuple[bytes, str]:
    import edge_tts
    pct = round((float(s["tts_speed"]) - 1) * 100)
    comm = edge_tts.Communicate(text, s["edge_voice"], rate=f"{pct:+d}%")

    async def collect() -> bytes:
        out = b""
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                out += chunk["data"]
        return out

    audio = asyncio.run(collect())   # called from a sync worker thread, no loop running there
    if not audio:
        raise RuntimeError("Edge TTS returned no audio")
    return audio, "audio/mpeg"


def warmup():
    """Loads Whisper + Kokoro in the background (~5s each cold) so the first
    real answer of an interview isn't the slow one. Missing models are skipped."""
    def run():
        s = settings()
        for fn in ((lambda: _whisper_model()) if s["stt_engine"] == "local" else None,
                   (lambda: _kokoro_engine()) if s["tts_engine"] == "kokoro" else None):
            if fn:
                try:
                    fn()
                except Exception as e:
                    logging.info("speech warmup skipped: %s", e)
    threading.Thread(target=run, daemon=True).start()


def synthesize(text: str, overrides: dict | None = None) -> tuple[bytes, str] | None:
    """(audio bytes, mime type), or None when the renderer should speak it
    itself (engine "browser", or every server engine failed). `overrides`
    lets Settings preview a voice before it's saved."""
    s = {**settings(), **{k: v for k, v in (overrides or {}).items() if k in DEFAULTS}}
    order = {"kokoro": ["kokoro", "edge"], "edge": ["edge", "kokoro"]}.get(s["tts_engine"], [])
    for eng in order:
        try:
            return _tts_kokoro(text, s) if eng == "kokoro" else _tts_edge(text, s)
        except Exception as e:
            logging.warning("TTS via %s failed: %s", eng, e)
    return None
