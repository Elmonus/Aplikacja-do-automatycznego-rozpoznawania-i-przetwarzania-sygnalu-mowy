'use strict';

const { app, BrowserWindow, session, dialog, shell } = require('electron');
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');
const treeKill = require('tree-kill');

// ============================================================
// KONFIGURACJA
// ============================================================
const PORT = 5123;
const HOST = '127.0.0.1';
const BACKEND_URL = `http://${HOST}:${PORT}`;
const BACKEND_DIR = path.join(__dirname, 'backend');

let mainWindow = null;
let backendProcess = null;
let backendReady = false;

const isDev = !app.isPackaged;

// ============================================================
// WYBOR INTERPRETERA PYTHONA
// Priorytet: venv w backend/ -> python3 -> python
// ============================================================
function resolvePythonCommand() {
  const isWin = process.platform === 'win32';
  const venvPython = isWin
    ? path.join(BACKEND_DIR, 'venv', 'Scripts', 'python.exe')
    : path.join(BACKEND_DIR, 'venv', 'bin', 'python');

  const fs = require('fs');
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  // Fallback na systemowy Python
  return isWin ? 'python' : 'python3';
}

// ============================================================
// URUCHOMIENIE BACKENDU FLASK
// ============================================================
function startBackend() {
  const python = resolvePythonCommand();
  console.log(`[main] Uruchamiam backend: ${python} app.py (cwd=${BACKEND_DIR})`);

  backendProcess = spawn(python, ['app.py'], {
    cwd: BACKEND_DIR,
    env: {
      ...process.env,
      AUDIO_APP_PORT: String(PORT),
      PYTHONUNBUFFERED: '1',
    },
  });

  backendProcess.stdout.on('data', (data) => {
    process.stdout.write(`[flask] ${data}`);
  });
  backendProcess.stderr.on('data', (data) => {
    // Flask i logging pisza na stderr - to normalne, nie traktujemy jako blad
    process.stderr.write(`[flask] ${data}`);
  });
  backendProcess.on('error', (err) => {
    console.error('[main] Nie udalo sie uruchomic Pythona:', err);
    dialog.showErrorBox(
      'Brak Pythona',
      'Nie udalo sie uruchomic backendu. Upewnij sie, ze Python 3.9+ jest zainstalowany ' +
      'oraz ze uruchomiono instalator (setup.sh / setup.bat).'
    );
  });
  backendProcess.on('exit', (code, signal) => {
    console.log(`[main] Backend zakonczyl dzialanie (code=${code}, signal=${signal})`);
    backendProcess = null;
  });
}

// ============================================================
// CZEKANIE NA GOTOWOSC BACKENDU (poll /health)
// ============================================================
function pingHealth() {
  return new Promise((resolve) => {
    const req = http.get(`${BACKEND_URL}/health`, (res) => {
      let body = '';
      res.on('data', (c) => (body += c));
      res.on('end', () => resolve(res.statusCode === 200));
    });
    req.on('error', () => resolve(false));
    req.setTimeout(2000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForBackend(timeoutMs = 60000, intervalMs = 500) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await pingHealth()) {
      backendReady = true;
      return true;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

// ============================================================
// OKNO APLIKACJI
// ============================================================
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 880,
    minWidth: 720,
    minHeight: 600,
    backgroundColor: '#0a0a0a',
    show: false,
    title: 'Audio Transcriber',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  // Ekran ladowania, zanim backend wstanie
  mainWindow.loadFile(path.join(__dirname, 'frontend', 'loading.html'));
  mainWindow.once('ready-to-show', () => mainWindow.show());

  // Linki zewnetrzne otwieraj w przegladarce systemowej
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  if (isDev) {
    // mainWindow.webContents.openDevTools({ mode: 'detach' });
  }
}

function loadApp() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.loadURL(BACKEND_URL);
  }
}

// ============================================================
// ZEZWOLENIE NA MIKROFON
// (localhost jest secure context, ale Electron i tak pyta o zgode)
// ============================================================
function configureMediaPermissions() {
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    const allowed = ['media', 'audioCapture', 'microphone'];
    callback(allowed.includes(permission));
  });
  session.defaultSession.setPermissionCheckHandler((webContents, permission) => {
    return ['media', 'audioCapture', 'microphone'].includes(permission);
  });
}

// ============================================================
// CYKL ZYCIA APLIKACJI
// ============================================================
app.whenReady().then(async () => {
  configureMediaPermissions();
  createWindow();
  startBackend();

  const ok = await waitForBackend();
  if (ok) {
    console.log('[main] Backend gotowy - laduje interfejs.');
    loadApp();
  } else {
    dialog.showErrorBox(
      'Backend nie odpowiada',
      'Serwer Flask nie wystartowal w wyznaczonym czasie. ' +
      'Sprawdz, czy zaleznosci Pythona sa zainstalowane (setup.sh / setup.bat) ' +
      'oraz czy FFmpeg jest dostepny w systemie.'
    );
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
      if (backendReady) loadApp();
    }
  });
});

// ============================================================
// ZAMYKANIE - zatrzymanie backendu
// ============================================================
function shutdownBackend() {
  if (backendProcess && backendProcess.pid) {
    console.log('[main] Zatrzymuje backend...');
    treeKill(backendProcess.pid, 'SIGTERM');
    backendProcess = null;
  }
}

app.on('window-all-closed', () => {
  shutdownBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', shutdownBackend);
process.on('exit', shutdownBackend);
process.on('SIGINT', () => {
  shutdownBackend();
  process.exit(0);
});
