# Wychwytywacz Instalacja  

Jak pobrać i skonfigurować wszystko, czego potrzebuje aplikacja.


> Katalog projektu w przykładach to `wychwytywacz`.

---

## Co trzeba zainstalować 

| Składnik | Min. wersja |
|----------|-------------|
| Node.js + npm  | 18+ |
| Python 3 | 3.9+ |
| FFmpeg | dowolna aktualna |
| Ollama | dowolna aktualna |


---

## 1. macOS

### 1.1. Homebrew 
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 1.2. Zależności systemowe
```bash
brew install node python@3.12 ffmpeg ollama
```

### 1.3. Ollama — serwer + model
```bash
brew services start ollama        # serwer w tle (albo: ollama serve w osobnym oknie)
ollama pull mistral:7b            # lub lżejszy: ollama pull llama3.2:3b
```

### 1.4. Projekt: środowisko Pythona + zależności Electrona
```bash
cd wychwytywacz

python3 -m venv backend/venv
source backend/venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
deactivate

npm install
```

### 1.5. Uruchom 
```bash
npm start
```

---

## 2. Linux

### 2.1. Zależności systemowe

**Debian / Ubuntu:**
```bash
# Node.js LTS 
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs

# Python + venv + pip
sudo apt-get install -y python3 python3-venv python3-pip

# FFmpeg
sudo apt-get install -y ffmpeg

# (do budowania AppImage) biblioteka FUSE
sudo apt-get install -y libfuse2
```

**Fedora:**
```bash
sudo dnf install -y nodejs python3 python3-pip
sudo dnf install -y ffmpeg          
```

**Arch:**
```bash
sudo pacman -S --needed nodejs npm python python-pip ffmpeg
```

### 2.2. Ollama — serwer + model
```bash
curl -fsSL https://ollama.com/install.sh | sh    
ollama pull mistral:7b                           # lub: ollama pull llama3.2:3b
```

### 2.3. Projekt: środowisko Pythona + zależności Electrona
```bash
cd wychwytywacz

python3 -m venv backend/venv
source backend/venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
deactivate

npm install
```

### 2.4. Uruchom 
```bash
npm start
```

---

## 3. Windows 


### 3.1. Zależności systemowe

- Node.js — https://nodejs.org (wersja LTS)
- Python — https://www.python.org/downloads/ 
- FFmpeg — https://www.gyan.dev/ffmpeg/builds/ 
- Ollama — https://ollama.com/download/windows

### 3.2. Ollama — model
Ollama startuje jako usługa po instalacji. Pobrać model:
```powershell
ollama pull mistral:7b
```

### 3.3. Projekt: środowisko Pythona + zależności Electrona
```powershell
cd wychwytywacz

python -m venv backend\venv
backend\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
deactivate

npm install

### 3.4. Uruchom 
```powershell
npm start
```

---

## 4. Weryfikacja 
```bash
node -v
npm -v
python3 --version      # Windows: python --version
ffmpeg -version
ollama --version
```
Serwer Ollama powinien odpowiadać pod `http://localhost:11434`.
Model Whisper powinien pobrać się sam przy pierwszej transkrypcji.



