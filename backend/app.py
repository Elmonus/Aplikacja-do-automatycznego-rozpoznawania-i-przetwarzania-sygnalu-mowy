import os
import io
import sys
import uuid
import tempfile
import logging

import requests
from flask import (
    Flask, request, jsonify, send_file, send_from_directory
)
from flask_cors import CORS
from pydub import AudioSegment
from werkzeug.utils import secure_filename


# Konfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("audio-backend")

# Port  (ustawia ją Electron)
PORT = int(os.environ.get("AUDIO_APP_PORT", "5123"))
HOST = "127.0.0.1"

# Whisper
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")  # tiny/base/small/medium/large-v3
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")       # cpu/cuda
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")    # int8/float16/float32

# Ollama
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral:7b")    # lub llama3.2:3b
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "300"))

# Pliki
ALLOWED_EXTENSIONS = {"mp3", "wav", "flac", "ogg", "webm", "m4a", "aac", "mp4"}
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB

# Czy dzialamy jako zamrozony plik PyInstaller?
IS_FROZEN = getattr(sys, "frozen", False)
BASE_DIR = (
    os.path.dirname(sys.executable) if IS_FROZEN
    else os.path.dirname(os.path.abspath(__file__))
)

# Frontend: Electron przekazuje sciezke przez AUDIO_APP_FRONTEND_DIR.
# Fallback dla uruchomienia recznego (dev).
FRONTEND_DIR = os.environ.get("AUDIO_APP_FRONTEND_DIR") or os.path.join(
    os.path.dirname(BASE_DIR), "frontend"
)

# Uploady MUSZA trafiac do katalogu zapisywalnego. W spakowanej aplikacji
# katalog Resources jest tylko-do-odczytu, dlatego domyslnie uzywamy temp.
UPLOAD_FOLDER = os.environ.get("AUDIO_APP_UPLOAD_DIR") or os.path.join(
    tempfile.gettempdir(), "audio_transcriber_uploads"
)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# FFmpeg: Electron moze przekazac sciezki do dolaczonych binarek.
_ffmpeg = os.environ.get("FFMPEG_BINARY")
_ffprobe = os.environ.get("FFPROBE_BINARY")
if _ffmpeg:
    AudioSegment.converter = _ffmpeg
    # dopiac katalog ffmpeg do PATH (faster-whisper/av tez moga go potrzebowac)
    os.environ["PATH"] = os.path.dirname(_ffmpeg) + os.pathsep + os.environ.get("PATH", "")
if _ffprobe:
    AudioSegment.ffprobe = _ffprobe

app = Flask(__name__, static_folder=None)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

logger.info("BASE_DIR=%s frozen=%s", BASE_DIR, IS_FROZEN)
logger.info("FRONTEND_DIR=%s", FRONTEND_DIR)
logger.info("UPLOAD_FOLDER=%s", UPLOAD_FOLDER)
logger.info("FFMPEG=%s FFPROBE=%s", _ffmpeg or "(PATH)", _ffprobe or "(PATH)")


# WHISPER - (ladowany przy pierwszym uzyciu)
_whisper_model = None


def get_whisper_model():
    """Laduje model Whisper dopiero przy pierwszej transkrypcji."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info("Ladowanie modelu Whisper (%s, %s, %s)...",
                    WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE)
        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE,
        )
        logger.info("Model Whisper zaladowany.")
    return _whisper_model



# Pomoc
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def format_timestamp(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def build_summary_prompt(text: str, mode: str, language: str = "pl") -> str:
    """Wysyla prompt dla Ollama zaleznie od wybranego trybu i jezyka.
    Po polsku gdy language == 'pl', w przeciwnym razie po angielsku."""
    prompts_pl = {
        "short": (
            "Podsumuj ponizsza transkrypcje w 2-3 zdaniach po polsku. "
            "Skup sie na najwazniejszej tresci.\n\nTRANSKRYPCJA:\n"
        ),
        "detailed": (
            "Stworz szczegolowe podsumowanie ponizszej transkrypcji po polsku. "
            "Zachowaj kluczowe informacje, kontekst i wnioski. Uzyj akapitow.\n\nTRANSKRYPCJA:\n"
        ),
        "bullets": (
            "Wypisz najwazniejsze punkty z ponizszej transkrypcji jako liste po polsku. "
            "Kazdy punkt zacznij od mysli wiodacej (-). Bez dodatkowego wstepu.\n\nTRANSKRYPCJA:\n"
        ),
        "tasks": (
            "Z ponizszej transkrypcji wyodrebnij konkretne zadania do wykonania (action items) po polsku. "
            "Wypisz je jako liste z mysli wiodacych (-). Jesli zadan brak, napisz 'Brak konkretnych zadan'.\n\nTRANSKRYPCJA:\n"
        ),
    }
    prompts_en = {
        "short": (
            "Summarize the following transcript in 2-3 sentences. "
            "Focus on the most important content.\n\nTRANSCRIPT:\n"
        ),
        "detailed": (
            "Create a detailed summary of the following transcript. "
            "Include key points, context and conclusions. Use paragraphs.\n\nTRANSCRIPT:\n"
        ),
        "bullets": (
            "List the most important points from the following transcript as a list. "
            "Start each point with a dash (-). No introduction.\n\nTRANSCRIPT:\n"
        ),
        "tasks": (
            "From the following transcript, extract specific action items. "
            "List them with dashes (-). If there are none, write 'No specific action items'.\n\nTRANSCRIPT:\n"
        ),
    }
    is_polish = (language or "pl").lower().startswith("pl")
    table = prompts_pl if is_polish else prompts_en
    prefix = table.get(mode, table["short"])
    suffix = "\n\nPODSUMOWANIE:" if is_polish else "\n\nSUMMARY:"
    return prefix + text + suffix



# interfejs
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def frontend_files(filename):
    # ewentualne dodatkowe pliki frontendu
    return send_from_directory(FRONTEND_DIR, filename)


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "whisper_loaded": _whisper_model is not None,
        "whisper_model": WHISPER_MODEL_SIZE,
        "ollama_model": OLLAMA_MODEL,
    })



# transkrypcja
@app.route("/transcribe", methods=["POST"])
def transcribe():
    if "audio" not in request.files:
        return jsonify({"error": "Brak pliku audio"}), 400

    file = request.files["audio"]
    if file.filename == "":
        return jsonify({"error": "Pusta nazwa pliku"}), 400

    language = request.form.get("language", "").strip() or None
    if language == "auto":
        language = None

    tmp_in = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}_{secure_filename(file.filename or 'audio')}")
    tmp_wav = None
    try:
        file.save(tmp_in)

        # Konwersja do WAV 16 kHz mono 
        tmp_wav = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}.wav")
        audio = AudioSegment.from_file(tmp_in)
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(tmp_wav, format="wav")

        model = get_whisper_model()
        segments, info = model.transcribe(
            tmp_wav,
            language=language,
            beam_size=5,
            vad_filter=True,
        )

        seg_list = []
        full_text_parts = []
        for seg in segments:
            seg_list.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "start_str": format_timestamp(seg.start),
                "end_str": format_timestamp(seg.end),
                "text": seg.text.strip(),
            })
            full_text_parts.append(seg.text.strip())

        return jsonify({
            "success": True,
            "text": " ".join(full_text_parts).strip(),
            "segments": seg_list,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration": round(info.duration, 2),
        })

    except Exception as exc:  # noqa: BLE001
        logger.exception("Blad transkrypcji")
        return jsonify({"error": f"Blad transkrypcji: {exc}"}), 500
    finally:
        for p in (tmp_in, tmp_wav):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass



# podsumowanie (Ollama)
@app.route("/summarize", methods=["POST"])
def summarize():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    # nowy frontend wysyla "type"; zachowujemy zgodnosc ze starym "mode"
    mode = data.get("type") or data.get("mode", "short")
    if mode == "action":          # alias z interfejsu -> klucz promptu
        mode = "tasks"
    language = data.get("language", "pl")   # 'pl' -> po polsku, inne -> po angielsku
    model = data.get("model", OLLAMA_MODEL)

    if not text:
        return jsonify({"error": "Brak tekstu do podsumowania"}), 400

    prompt = build_summary_prompt(text, mode, language)
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        if resp.status_code != 200:
            return jsonify({
                "error": f"Ollama zwrocila status {resp.status_code}. "
                         f"Sprawdz czy serwer dziala (ollama serve) i czy masz model '{model}'."
            }), 502
        result = resp.json()
        return jsonify({
            "success": True,
            "summary": (result.get("response") or "").strip(),
            "model": model,
        })

    except requests.exceptions.ConnectionError:
        return jsonify({
            "error": "Nie mozna polaczyc z Ollama (localhost:11434). "
                     "Uruchom serwer komenda: ollama serve"
        }), 502
    except requests.exceptions.Timeout:
        return jsonify({
            "error": "Przekroczono limit czasu. Sprobuj mniejszego modelu (np. llama3.2:3b) "
                     "lub krotszego tekstu."
        }), 504
    except Exception as exc:  # noqa: BLE001
        logger.exception("Blad podsumowania")
        return jsonify({"error": f"Blad podsumowania: {exc}"}), 500


@app.route("/ollama/models")
def ollama_models():
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            tags = resp.json().get("models", [])
            names = [m.get("name") for m in tags if m.get("name")]
            return jsonify({"available": True, "models": names})
        return jsonify({"available": False, "models": []})
    except Exception:  # noqa: BLE001
        return jsonify({"available": False, "models": []})


#konwersja
@app.route("/convert", methods=["POST"])
def convert():
    if "audio" not in request.files:
        return jsonify({"error": "Brak pliku audio"}), 400

    file = request.files["audio"]
    out_format = request.form.get("format", "mp3").lower()
    if out_format not in {"mp3", "wav", "flac", "ogg"}:
        return jsonify({"error": "Nieobslugiwany format"}), 400

    tmp_in = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}_{secure_filename(file.filename or 'audio')}")
    try:
        file.save(tmp_in)
        audio = AudioSegment.from_file(tmp_in)

        buf = io.BytesIO()
        export_params = {}
        if out_format == "mp3":
            export_params = {"bitrate": "192k"}
        audio.export(buf, format=out_format, **export_params)
        buf.seek(0)

        mimetypes = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "flac": "audio/flac",
            "ogg": "audio/ogg",
        }
        return send_file(
            buf,
            mimetype=mimetypes[out_format],
            as_attachment=True,
            download_name=f"audio.{out_format}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Blad konwersji")
        return jsonify({"error": f"Blad konwersji: {exc}"}), 500
    finally:
        if os.path.exists(tmp_in):
            try:
                os.remove(tmp_in)
            except OSError:
                pass



# ENDPOINT - konwersja do odtwarzania (WebM/OGG -> MP3)
@app.route("/convert-for-playback", methods=["POST"])
def convert_for_playback():
    if "audio" not in request.files:
        return jsonify({"error": "Brak pliku audio"}), 400

    file = request.files["audio"]
    tmp_in = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}_{secure_filename(file.filename or 'audio')}")
    try:
        file.save(tmp_in)
        audio = AudioSegment.from_file(tmp_in)
        buf = io.BytesIO()
        audio.export(buf, format="mp3", bitrate="192k")
        buf.seek(0)
        # inline (nie jako zalacznik), blob trafia prosto do <audio>
        return send_file(buf, mimetype="audio/mpeg", as_attachment=False,
                         download_name="playback.mp3")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Blad konwersji do odtwarzania")
        return jsonify({"error": f"Blad konwersji: {exc}"}), 500
    finally:
        if os.path.exists(tmp_in):
            try:
                os.remove(tmp_in)
            except OSError:
                pass



if __name__ == "__main__":
    logger.info("Backend startuje na http://%s:%s", HOST, PORT)
    logger.info("Frontend: %s", FRONTEND_DIR)
    # threaded=True - rownolegla obsluga health-check i dlugiej transkrypcji
    app.run(host=HOST, port=PORT, threaded=True, debug=False)