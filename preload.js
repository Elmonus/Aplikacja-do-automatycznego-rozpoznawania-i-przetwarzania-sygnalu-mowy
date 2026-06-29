'use strict';

// Preload dziala w izolowanym kontekscie (contextIsolation: true).
// Na ten moment frontend komunikuje sie z backendem przez fetch() do http://127.0.0.1:5123,
// wiec nie potrzebujemy mostka IPC. Plik zostawiamy jako punkt rozszerzen
// (np. natywny zapis pliku, menu, powiadomienia systemowe).

const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('desktop', {
  isElectron: true,
  platform: process.platform,
  version: process.versions.electron,
});
