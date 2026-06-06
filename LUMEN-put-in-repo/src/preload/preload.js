const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('lumen', {
  tabs: {
    create: (url) => ipcRenderer.invoke('tabs:create', url),
    close: (id) => ipcRenderer.invoke('tabs:close', id),
    switch: (id) => ipcRenderer.invoke('tabs:switch', id),
    onUpdated: (cb) => {
      ipcRenderer.on('tabs:updated', (_, data) => cb(data));
    },
  },
  nav: {
    go: (input) => ipcRenderer.invoke('nav:go', input),
    back: () => ipcRenderer.invoke('nav:back'),
    forward: () => ipcRenderer.invoke('nav:forward'),
    reload: () => ipcRenderer.invoke('nav:reload'),
    stop: () => ipcRenderer.invoke('nav:stop'),
    onState: (cb) => {
      ipcRenderer.on('nav:state', (_, data) => cb(data));
    },
  },
  settings: {
    get: () => ipcRenderer.invoke('settings:get'),
    set: (patch) => ipcRenderer.invoke('settings:set', patch),
  },
  bookmarks: {
    get: () => ipcRenderer.invoke('bookmarks:get'),
    add: (item) => ipcRenderer.invoke('bookmarks:add', item),
    remove: (id) => ipcRenderer.invoke('bookmarks:remove', id),
  },
  history: {
    get: () => ipcRenderer.invoke('history:get'),
  },
  openExternal: (url) => ipcRenderer.invoke('app:openExternal', url),
  startNavigate: (url) => ipcRenderer.send('start:navigate', url),
  startSearch: (query) => ipcRenderer.send('start:search', query),
});
