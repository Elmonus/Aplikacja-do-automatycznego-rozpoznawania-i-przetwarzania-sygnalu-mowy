import os
import io
import tempfile
import logging
import uuid
import requests
from flask import Flask, request, send_file, render_template, jsonify, send_from_directory
from flask_cors import CORS
from pydub import AudioSegment
from werkzeug.utils import secure_filename


# Konfiguracja Ollama

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2:3b"  # llama3.2:3b, mistral:7b

# Konfiguracja logowania
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# dostep z roznych przegladarek
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Konfiguracja
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'flac', 'ogg', 'webm', 'm4a', 'aac'}
MAX_FILE_SIZE = 100 * 1024 * 1024

# Foldery
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


# Whisper

whisper_model = None

def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            logger.info("Ladowanie modelu Whisper...")
            
            whisper_model = WhisperModel(
                "small",
                device="cpu",
                compute_type="float32"
            )
            logger.info("Model Whisper zaladowany")
        except ImportError as e:
            logger.error(f"faster-whisper nie zainstalowany: {e}")
            raise
        except Exception as e:
            logger.error(f"Blad ladowania Whisper: {e}")
            raise
    return whisper_model


def convert_to_wav_bytes(audio_file):
    try:
        audio = AudioSegment.from_file(audio_file)
        audio = audio.set_frame_rate(16000).set_channels(1)
        
        output = io.BytesIO()
        audio.export(output, format='wav')
        output.seek(0)
        return output.read()
    except Exception as e:
        logger.error(f"Blad konwersji do WAV: {e}")
        raise


FORMAT_MIME = {
    'mp3': 'audio/mpeg',
    'wav': 'audio/wav',
    'flac': 'audio/flac',
    'ogg': 'audio/ogg',
    'webm': 'audio/webm',
    'm4a': 'audio/mp4',
    'aac': 'audio/aac'
}


@app.route('/')
def index():
    logger.info("Strona glowna otwarta")
    return render_template('index.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(STATIC_FOLDER, filename)


@app.route('/convert', methods=['POST', 'OPTIONS'])
def convert_audio():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        logger.info("Konwersja...")
        
        if 'audio' not in request.files:
            return jsonify({'success': False, 'error': 'Brak pliku audio'}), 400
        
        file = request.files['audio']
        target_format = request.form.get('format', 'mp3')
        
        logger.info(f"Format: {target_format}")
        
        audio = AudioSegment.from_file(file)
        output = io.BytesIO()
        
        if target_format == 'mp3':
            audio.export(output, format='mp3', bitrate='192k')
        elif target_format == 'wav':
            audio.export(output, format='wav')
        elif target_format == 'flac':
            audio.export(output, format='flac')
        elif target_format == 'ogg':
            audio.export(output, format='ogg', codec='libvorbis')
        else:
            audio.export(output, format=target_format)
        
        output.seek(0)
        logger.info("Konwersja OK")
        
        return send_file(
            output,
            mimetype=FORMAT_MIME.get(target_format, 'audio/mpeg'),
            as_attachment=True,
            download_name=f'audio.{target_format}'
        )
        
    except Exception as e:
        logger.error(f"Blad: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/convert-for-playback', methods=['POST', 'OPTIONS'])
def convert_for_playback():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        if 'audio' not in request.files:
            return jsonify({'success': False, 'error': 'Brak pliku audio'}), 400
        
        file = request.files['audio']
        logger.info(f"Konwersja dla odtwarzania: {file.content_type}")
        
        audio = AudioSegment.from_file(file)
        output = io.BytesIO()
        audio.export(output, format='mp3', bitrate='128k')
        output.seek(0)
        
        return send_file(output, mimetype='audio/mpeg', as_attachment=False)
        
    except Exception as e:
        logger.error(f"Blad: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/transcribe', methods=['POST', 'OPTIONS'])
def transcribe_audio():
    if request.method == 'OPTIONS':
        return '', 204
    
    tmp_path = None
    try:
        logger.info("=== TRANSKRYPCJA ===")
        
        if 'audio' not in request.files:
            return jsonify({'success': False, 'error': 'Brak pliku audio'}), 400
        
        file = request.files['audio']
        language = request.form.get('language', 'pl')
        
        logger.info(f"Jezyk: {language}, typ: {file.content_type}")
        
        # Konwersja do WAV
        wav_bytes = convert_to_wav_bytes(file)
        logger.info(f"WAV: {len(wav_bytes)} bytes")
        
        # Zapis tymczasowy
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.wav')
        os.close(tmp_fd)
        with open(tmp_path, 'wb') as f:
            f.write(wav_bytes)
        
        # Whisper
        model = get_whisper_model()
        
        segments_gen, info = model.transcribe(
            tmp_path,
            language=language if language != 'auto' else None,
            beam_size=5,
            vad_filter=True
        )
        
        full_text = []
        segments_data = []
        
        for segment in segments_gen:
            text = segment.text.strip()
            if text:
                full_text.append(text)
                segments_data.append({
                    'start': round(segment.start, 2),
                    'end': round(segment.end, 2),
                    'text': text
                })
        
        result = {
            'success': True,
            'text': ' '.join(full_text),
            'segments': segments_data,
            'language': info.language if info.language else language,
            'duration': round(info.duration, 2) if info.duration else 0
        }
        
        logger.info(f"OK: {len(segments_data)} segmentow")
        return jsonify(result)
        
    except ImportError:
        return jsonify({'success': False, 'error': 'faster-whisper nie zainstalowany'}), 500
    except Exception as e:
        logger.error(f"Blad: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass


@app.route('/health')
def health():
    # Sprawdza czy Ollama dziala
    ollama_status = "niedostepny"
    ollama_models = []
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        if resp.ok:
            ollama_status = "ok"
            data = resp.json()
            ollama_models = [m['name'] for m in data.get('models', [])]
    except:
        pass
    
    return jsonify({
        'status': 'ok',
        'whisper_loaded': whisper_model is not None,
        'ollama_status': ollama_status,
        'ollama_models': ollama_models,
        'ollama_model_configured': OLLAMA_MODEL
    })


@app.route('/summarize', methods=['POST', 'OPTIONS'])
def summarize_text():
    """Podsumowanie tekstu przez Ollama"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'success': False, 'error': 'Brak tekstu do podsumowania'}), 400
        
        text = data['text']
        summary_type = data.get('type', 'short')  # short, detailed, bullets
        language = data.get('language', 'pl')
        
        logger.info(f"=== PODSUMOWANIE ({summary_type}) ===")
        logger.info(f"Tekst: {len(text)} znakow")
        
        # Sprawdz czy Ollama dziala
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
            if not resp.ok:
                raise Exception("Ollama nie odpowiada")
        except Exception as e:
            logger.error(f"Ollama niedostepna: {e}")
            return jsonify({
                'success': False, 
                'error': 'Ollama nie jest uruchomiona. Uruchom: ollama serve'
            }), 503
        
        # Przygotowuje prompt w zaleznosci od typu
        if language == 'pl':
            if summary_type == 'short':
                prompt = f"""Podsumuj ponizszy tekst w 2-3 zdaniach. Odpowiedz tylko podsumowaniem, bez wstepu.

Tekst:
{text}

Podsumowanie:"""
            elif summary_type == 'detailed':
                prompt = f"""Stworz szczegolowe podsumowanie ponizszego tekstu. Uwzglednij najwazniejsze punkty i wnioski. Odpowiedz tylko podsumowaniem.

Tekst:
{text}

Szczegolowe podsumowanie:"""
            elif summary_type == 'bullets':
                prompt = f"""Wypisz najwazniejsze punkty z ponizszego tekstu w formie listy (maksymalnie 5-7 punktow). Kazdy punkt rozpocznij od "-".

Tekst:
{text}

Kluczowe punkty:"""
            elif summary_type == 'action':
                prompt = f"""Na podstawie ponizszego tekstu wypisz konkretne zadania do wykonania (action items). Kazde zadanie rozpocznij od "-".

Tekst:
{text}

Zadania do wykonania:"""
            else:
                prompt = f"""Podsumuj ponizszy tekst:

{text}

Podsumowanie:"""
        else:
            # angielski jeśli nie polski
            if summary_type == 'short':
                prompt = f"""Summarize the following text in 2-3 sentences. Reply only with the summary.

Text:
{text}

Summary:"""
            elif summary_type == 'detailed':
                prompt = f"""Create a detailed summary of the following text. Include key points and conclusions.

Text:
{text}

Detailed summary:"""
            elif summary_type == 'bullets':
                prompt = f"""List the most important points from the following text (max 5-7 points). Start each point with "-".

Text:
{text}

Key points:"""
            elif summary_type == 'action':
                prompt = f"""Based on the following text, list specific action items. Start each item with "-".

Text:
{text}

Action items:"""
            else:
                prompt = f"""Summarize the following text:

{text}

Summary:"""
        
        logger.info(f"Wysylam do Ollama ({OLLAMA_MODEL})...")
        
        # Wywolaj Ollama
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Niska temperatura dla bardziej spójnych podsumowań
                    "num_predict": 500   # Max tokenow odpowiedzi
                }
            },
            timeout=120  # 2 minuty timeout
        )
        
        if not response.ok:
            logger.error(f"Ollama error: {response.status_code}")
            return jsonify({
                'success': False,
                'error': f'Blad Ollama: {response.status_code}'
            }), 500
        
        result = response.json()
        summary = result.get('response', '').strip()
        
        logger.info(f"Podsumowanie: {len(summary)} znakow")
        logger.info(f"=== PODSUMOWANIE OK ===")
        
        return jsonify({
            'success': True,
            'summary': summary,
            'model': OLLAMA_MODEL,
            'type': summary_type
        })
        
    except requests.exceptions.Timeout:
        logger.error("Ollama timeout")
        return jsonify({
            'success': False,
            'error': 'Timeout - podsumowanie trwa za dlugo. Sprobuj krotszego tekstu.'
        }), 504
    except requests.exceptions.ConnectionError:
        logger.error("Brak polaczenia z Ollama")
        return jsonify({
            'success': False,
            'error': 'Nie mozna polaczyc z Ollama. Sprawdz czy ollama serve jest uruchomione.'
        }), 503
    except Exception as e:
        logger.error(f"Blad podsumowania: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/ollama/models', methods=['GET'])
def get_ollama_models():
    """Lista dostepnych modeli Ollama"""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.ok:
            data = resp.json()
            models = [m['name'] for m in data.get('models', [])]
            return jsonify({
                'success': True,
                'models': models,
                'current': OLLAMA_MODEL
            })
        else:
            return jsonify({'success': False, 'error': 'Ollama nie odpowiada'}), 503
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 503


if __name__ == '__main__':
    print("""
  Serwer:
    http://localhost:5001
    http://127.0.0.1:5001
    """)
    
    app.run(debug=True, host='0.0.0.0', port=5001, threaded=True)
