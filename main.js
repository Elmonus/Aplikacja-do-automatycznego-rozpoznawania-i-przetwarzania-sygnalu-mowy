'use strict';

const { app, BrowserWindow, session, dialog, shell } = require('electron');
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');
const treeKill = require('tree-kill');


// Konfiguracja
const PORT = 5123;
const HOST = '127.0.0.1';
const BACKEND_URL = `http://${HOST}:${PORT}`;
const BACKEND_DIR = path.join(__dirname, 'backend');

let mainWindow = null;
let backendProcess = null;
let backendReady = false;

const isDev = !app.isPackaged;



// Priorytet: venv w backend/ -> python3 -> python
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


// Backend w flask
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

    process.stderr.write(`[flask] ${data}`);
  });
  backendProcess.on('error', (err) => {
    console.error('[main] Nie udalo sie uruchomic Pythona:', err);
    dialog.showErrorBox(
      'Brak Pythona',
      'Nie udalo sie uruchomic backendu'
    );
  });
  backendProcess.on('exit', (code, signal) => {
    console.log(`[main] Backend zakonczyl dzialanie (code=${code}, signal=${signal})`);
    backendProcess = null;
  });
}


// Sprawdzanie backendu
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


// Okno aplikacji
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

  // Ladowanie
  mainWindow.loadFile(path.join(__dirname, 'frontend', 'loading.html'));
  mainWindow.once('ready-to-show', () => mainWindow.show());

  // Linki
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


// Mikrofon
function configureMediaPermissions() {
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    const allowed = ['media', 'audioCapture', 'microphone'];
    callback(allowed.includes(permission));
  });
  session.defaultSession.setPermissionCheckHandler((webContents, permission) => {
    return ['media', 'audioCapture', 'microphone'].includes(permission);
  });
}


// Cykl
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
      'Sprawdz, czy zaleznosci Pythona sa zainstalowane ' +
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


// Zamykanie
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
