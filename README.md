# Wywoływacz

Nagrywanie, transkrypcja (Whisper) i podsumowanie (Ollama) audio.


---

## Wymagania

| Program | Wersja |
|---------|--------|
| Python | 3.9+ |
| FFmpeg | dowolna |
| Ollama | dowolna  |

---

## Windows

### Instalacja

1. **Python 3.9+**

2. **FFmpeg**
   - Pobierz: https://ffmpeg.org/download.html
   - Rozpakuj do `C:\ffmpeg`
   - Dodaj `C:\ffmpeg\bin` do PATH:
     - Szukaj "Zmienne srodowiskowe"
     - Path -> Edytuj -> Nowy -> `C:\ffmpeg\bin`

3. **Ollama (opcjonalne)**
   - Pobierz: https://ollama.com/download/windows
   - Zainstaluj i uruchom
   - W PowerShell: `ollama pull mistral:7b` oraz `ollama pull llama3.2:3b`

### Uruchomienie

```powershell
# Otworz PowerShell w folderze z kodem

# Wirtualne srodowisko
python -m venv venv
.\venv\Scripts\Activate

# Zaleznosci Python
pip install -r wymagania.txt

# Uruchom
python app.py
```

Otworz: http://localhost:5001

---

## macOS

### Instalacja

```bash
brew install python ffmpeg ollama

# Pobierz model 
ollama pull mistral:7b
ollama pull llama3.2:3b
```

### Uruchomienie

```bash
# Wirtualne srodowisko
python3 -m venv venv
source venv/bin/activate

# Python pakiety
pip install -r wymagania.txt

# Uruchom
python app.py
```

Otworz: http://localhost:5001

---

