# Audio Transcriber — wersja desktopowa (Electron + Python)

Desktopowa aplikacja do **nagrywania, transkrypcji i podsumowania audio** — działa
w 100% lokalnie i offline, bez przeglądarki i bez chmury.

To wersja desktopowa Twojej webówki Flask. Architektura zachowuje **Pythona jako bazę**:
Electron uruchamia serwer Flask jako proces w tle (loopback `127.0.0.1`) i wyświetla
interfejs w natywnym oknie aplikacji.

```
┌──────────────────────────────────────────────┐
│  Electron (okno aplikacji)                     │
│   └── ładuje UI z http://127.0.0.1:5123        │
│                                                │
│  child_process → Python / Flask (app.py)       │
│        ├── /transcribe   faster-whisper        │
│        ├── /summarize    Ollama (localhost)    │
│        ├── /convert      pydub + FFmpeg         │
│        └── /health       status                │
└──────────────────────────────────────────────┘
```

## Wymagania

| Składnik | Wersja | Uwagi |
|----------|--------|-------|
| Python | 3.9+ (zalecane 3.10–3.12) | backend |
| Node.js + npm | 18+ | Electron |
| FFmpeg | dowolna | konwersja audio (pydub) |
| Ollama | opcjonalnie | tylko do podsumowań |

Instalacja FFmpeg i Ollama:
```bash
# macOS
brew install ffmpeg ollama

# Debian/Ubuntu
sudo apt install ffmpeg
curl -fsSL https://ollama.com/install.sh | sh
```

## Instalacja

```bash
# macOS / Linux
chmod +x setup.sh
./setup.sh

# Windows
setup.bat
```

Skrypt tworzy `backend/venv`, instaluje zależności Pythona i `npm install`.

## Uruchomienie

```bash
# (opcjonalnie) serwer Ollama do podsumowań — osobny terminal
ollama serve
ollama pull mistral:7b      # lub: ollama pull llama3.2:3b

# aplikacja
npm start
```

Electron sam wystartuje backend i otworzy okno. Przy pierwszej transkrypcji
pobierze się model Whisper (`base`, ~74 MB).

## Budowanie instalatorów

```bash
npm run build:mac     # DMG + ZIP
npm run build:win     # NSIS installer + portable
npm run build:linux   # AppImage + DEB
```

Wynik w katalogu `dist/`. Backend Pythona trafia do zasobów aplikacji
(`extraResources`), ale **interpreter Pythona i FFmpeg muszą być w systemie** —
aplikacja korzysta z `backend/venv` jeśli istnieje, w przeciwnym razie z systemowego `python3`.

> Pełne samowystarczalne paczki (bez wymaganego Pythona u użytkownika) wymagałyby
> dołączenia interpretera np. przez PyInstaller — to osobny krok, mogę go dorobić.

## Konfiguracja

Zmienne środowiskowe czytane przez `backend/app.py`:

| Zmienna | Domyślnie | Opis |
|---------|-----------|------|
| `AUDIO_APP_PORT` | `5123` | port backendu (ustawia Electron) |
| `WHISPER_MODEL` | `base` | `tiny`/`base`/`small`/`medium`/`large-v3` |
| `WHISPER_DEVICE` | `cpu` | `cpu` lub `cuda` |
| `WHISPER_COMPUTE` | `int8` | `int8`/`float16`/`float32` |
| `OLLAMA_MODEL` | `mistral:7b` | model do podsumowań |
| `OLLAMA_URL` | `http://localhost:11434` | adres Ollama |

## Funkcje

- Nagrywanie z mikrofonu (rec / pauza / stop) + wczytywanie plików (drag & drop)
- Transkrypcja Whisper z autodetekcją języka i podziałem na segmenty z czasami
- Kopiowanie transkrypcji (czysty tekst lub z timestampami)
- Podsumowanie przez Ollama: krótkie / szczegółowe / punkty / zadania
- Konwersja i eksport: MP3 / WAV / FLAC / OGG

## Rozwiązywanie problemów

- **Okno utknęło na ekranie ładowania** — backend nie wstał. Uruchom `setup.sh`
  ponownie i sprawdź, czy `python3` i FFmpeg są w PATH.
- **Brak dźwięku z mikrofonu** — na macOS nadaj aplikacji uprawnienia w
  *Ustawienia systemowe → Prywatność → Mikrofon*.
- **Podsumowanie zwraca błąd połączenia** — uruchom `ollama serve` i pobierz model.
- **Timeout podsumowania** — użyj mniejszego modelu (`llama3.2:3b`).
