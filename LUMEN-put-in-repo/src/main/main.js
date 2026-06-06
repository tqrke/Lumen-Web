const {
  app,
  BrowserWindow,
  BrowserView,
  ipcMain,
  session,
  shell,
  Menu,
  dialog,
} = require('electron');
const path = require('path');
const fs = require('fs');

const USER_DATA = app.getPath('userData');
const SETTINGS_PATH = path.join(USER_DATA, 'lumen-settings.json');
const BOOKMARKS_PATH = path.join(USER_DATA, 'lumen-bookmarks.json');
const HISTORY_PATH = path.join(USER_DATA, 'lumen-history.json');

const CHROME_HEIGHT = 118;
const SIDEBAR_WIDTH = 52;

const FREE_SEARCH_ENGINES = {
  duckduckgo: {
    name: 'DuckDuckGo',
    home: 'https://duckduckgo.com',
    search: 'https://duckduckgo.com/?q=%s',
  },
  brave: {
    name: 'Brave Search',
    home: 'https://search.brave.com',
    search: 'https://search.brave.com/search?q=%s',
  },
  searx: {
    name: 'SearXNG (Privacy)',
    home: 'https://searx.be',
    search: 'https://searx.be/search?q=%s',
  },
  wikipedia: {
    name: 'Wikipedia',
    home: 'https://www.wikipedia.org',
    search: 'https://en.wikipedia.org/wiki/Special:Search?search=%s',
  },
};

const DEFAULT_BLOCKLIST = [
  'doubleclick.net',
  'google-analytics.com',
  'googletagmanager.com',
  'facebook.net',
  'connect.facebook.net',
  'scorecardresearch.com',
  'hotjar.com',
  'mixpanel.com',
  'segment.io',
  'adservice.google.com',
  'pagead2.googlesyndication.com',
  'amazon-adsystem.com',
  'taboola.com',
  'outbrain.com',
  'criteo.com',
  'quantserve.com',
  'moatads.com',
  'adnxs.com',
];

let mainWindow = null;
let settings = loadJson(SETTINGS_PATH, getDefaultSettings());
let bookmarks = loadJson(BOOKMARKS_PATH, []);
let history = loadJson(HISTORY_PATH, []);
let tabs = [];
let activeTabId = null;
let shieldsStats = { blocked: 0, savedBytes: 0 };
let ghostMode = false;

function getDefaultSettings() {
  return {
    searchEngine: 'duckduckgo',
    privacyTier: 'enhanced',
    httpsOnly: true,
    blockTrackers: true,
    verticalTabs: false,
    theme: 'dark',
    homepage: 'lumen://start',
  };
}

function loadJson(filePath, fallback) {
  try {
    if (fs.existsSync(filePath)) {
      return JSON.parse(fs.readFileSync(filePath, 'utf8'));
    }
  } catch {
    /* use fallback */
  }
  return fallback;
}

function saveJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
}

function getSearchEngine() {
  return FREE_SEARCH_ENGINES[settings.searchEngine] || FREE_SEARCH_ENGINES.duckduckgo;
}

function navCanGoBack(wc) {
  return wc.navigationHistory?.canGoBack?.() ?? wc.canGoBack();
}

function navCanGoForward(wc) {
  return wc.navigationHistory?.canGoForward?.() ?? wc.canGoForward();
}

function isBlockedUrl(url) {
  if (!settings.blockTrackers) return false;
  try {
    const host = new URL(url).hostname.replace(/^www\./, '');
    const list =
      settings.privacyTier === 'paranoid'
        ? [...DEFAULT_BLOCKLIST, 'googletagservices.com', 'googleadservices.com']
        : DEFAULT_BLOCKLIST;
    return list.some(
      (d) => host === d || host.endsWith('.' + d)
    );
  } catch {
    return false;
  }
}

function normalizeInput(input) {
  const trimmed = input.trim();
  if (!trimmed) return getSearchEngine().home;

  if (trimmed === 'lumen://start') return trimmed;
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  if (/^localhost(:\d+)?(\/|$)/i.test(trimmed)) return `http://${trimmed}`;
  if (/^[\w-]+(\.[\w-]+)+(\/.*)?$/i.test(trimmed) && !trimmed.includes(' ')) {
    return `https://${trimmed}`;
  }

  const engine = getSearchEngine();
  return engine.search.replace('%s', encodeURIComponent(trimmed));
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0b0f19',
    title: 'LUMEN Browser',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));

  mainWindow.on('resize', layoutActiveView);
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  buildMenu();
}

function layoutActiveView() {
  if (!mainWindow || activeTabId === null) return;
  const tab = tabs.find((t) => t.id === activeTabId);
  if (!tab || !tab.view) return;

  const [w, h] = mainWindow.getContentSize();
  const sidebar = settings.verticalTabs ? 200 : SIDEBAR_WIDTH;
  const top = CHROME_HEIGHT;

  tab.view.setBounds({
    x: sidebar,
    y: top,
    width: Math.max(100, w - sidebar),
    height: Math.max(100, h - top),
  });
}

function createTab(url) {
  const id = Date.now() + Math.random();
  const targetUrl = url || settings.homepage;

  const view = new BrowserView({
    webPreferences: {
      preload: path.join(__dirname, '../preload/preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      partition: ghostMode ? 'persist:ghost' : 'persist:main',
    },
  });

  const tab = {
    id,
    url: targetUrl,
    title: 'New Tab',
    view,
    loading: true,
    canGoBack: false,
    canGoForward: false,
    secure: true,
  };

  tabs.push(tab);
  setupViewEvents(tab);
  switchTab(id);

  if (targetUrl === 'lumen://start') {
    view.webContents.loadFile(path.join(__dirname, '../renderer/start.html'));
  } else {
    view.webContents.loadURL(targetUrl);
  }

  sendTabsUpdate();
  return id;
}

function setupViewEvents(tab) {
  const { view } = tab;
  const wc = view.webContents;

  wc.on('did-start-loading', () => {
    tab.loading = true;
    sendTabsUpdate();
    sendNavState(tab);
  });

  wc.on('did-stop-loading', () => {
    tab.loading = false;
    tab.url = wc.getURL();
    tab.title = wc.getTitle() || tab.url;
    tab.canGoBack = navCanGoBack(wc);
    tab.canGoForward = navCanGoForward(wc);
    tab.secure = tab.url.startsWith('https://');

    if (tab.url.startsWith('http') && !ghostMode) {
      addHistory(tab.url, tab.title);
    }

    sendTabsUpdate();
    sendNavState(tab);
  });

  wc.on('page-title-updated', (_, title) => {
    tab.title = title;
    sendTabsUpdate();
  });

  wc.on('did-navigate', (_, url) => {
    tab.url = url;
    tab.canGoBack = navCanGoBack(wc);
    tab.canGoForward = navCanGoForward(wc);
    sendNavState(tab);
  });

  wc.on('did-navigate-in-page', (_, url) => {
    tab.url = url;
    tab.canGoBack = navCanGoBack(wc);
    tab.canGoForward = navCanGoForward(wc);
    sendNavState(tab);
  });

  wc.setWindowOpenHandler(({ url }) => {
    createTab(url);
    return { action: 'deny' };
  });
}

function switchTab(id) {
  const tab = tabs.find((t) => t.id === id);
  if (!tab || !mainWindow) return;

  tabs.forEach((t) => {
    if (t.view) mainWindow.removeBrowserView(t.view);
  });

  activeTabId = id;
  mainWindow.addBrowserView(tab.view);
  layoutActiveView();
  sendTabsUpdate();
  sendNavState(tab);
}

function closeTab(id) {
  const idx = tabs.findIndex((t) => t.id === id);
  if (idx === -1) return;

  const tab = tabs[idx];
  if (tab.view) {
    mainWindow.removeBrowserView(tab.view);
    tab.view.webContents.destroy();
  }
  tabs.splice(idx, 1);

  if (tabs.length === 0) {
    createTab();
    return;
  }

  if (activeTabId === id) {
    switchTab(tabs[Math.max(0, idx - 1)].id);
  } else {
    sendTabsUpdate();
  }
}

function getActiveTab() {
  return tabs.find((t) => t.id === activeTabId);
}

function navigateActive(input) {
  const tab = getActiveTab();
  if (!tab) return;

  const url = normalizeInput(input);
  tab.url = url;

  if (url === 'lumen://start') {
    tab.view.webContents.loadFile(path.join(__dirname, '../renderer/start.html'));
  } else {
    tab.view.webContents.loadURL(url);
  }
}

function sendTabsUpdate() {
  if (!mainWindow) return;
  mainWindow.webContents.send('tabs:updated', {
    tabs: tabs.map(({ id, url, title, loading, secure }) => ({
      id,
      url,
      title,
      loading,
      secure,
    })),
    activeTabId,
    verticalTabs: settings.verticalTabs,
    ghostMode,
  });
}

function sendNavState(tab) {
  if (!mainWindow || !tab) return;
  mainWindow.webContents.send('nav:state', {
    url: tab.url === 'lumen://start' ? '' : tab.url,
    title: tab.title,
    canGoBack: tab.canGoBack,
    canGoForward: tab.canGoForward,
    loading: tab.loading,
    secure: tab.secure,
    shields: shieldsStats,
  });
}

function addHistory(url, title) {
  history.unshift({
    url,
    title,
    time: Date.now(),
  });
  history = history.slice(0, 500);
  saveJson(HISTORY_PATH, history);
}

function configureSession() {
  const ses = session.fromPartition(ghostMode ? 'persist:ghost' : 'persist:main');

  ses.webRequest.onBeforeRequest({ urls: ['*://*/*'] }, (details, callback) => {
    if (isBlockedUrl(details.url)) {
      shieldsStats.blocked += 1;
      shieldsStats.savedBytes += 45000;
      callback({ cancel: true });
      return;
    }
    callback({});
  });

  if (settings.httpsOnly) {
    ses.webRequest.onBeforeRequest({ urls: ['http://*/*'] }, (details, callback) => {
      try {
        const u = new URL(details.url);
        if (['localhost', '127.0.0.1'].includes(u.hostname)) {
          callback({});
          return;
        }
        u.protocol = 'https:';
        callback({ redirectURL: u.toString() });
      } catch {
        callback({});
      }
    });
  }
}

function buildMenu() {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'New Tab',
          accelerator: 'CmdOrCtrl+T',
          click: () => createTab(),
        },
        {
          label: 'New Ghost Window',
          accelerator: 'CmdOrCtrl+Shift+N',
          click: () => {
            ghostMode = true;
            configureSession();
            createTab(getSearchEngine().home);
          },
        },
        { type: 'separator' },
        {
          label: 'Quit',
          accelerator: 'CmdOrCtrl+Q',
          click: () => app.quit(),
        },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function registerIPC() {
  ipcMain.handle('tabs:create', (_, url) => createTab(url));
  ipcMain.handle('tabs:close', (_, id) => closeTab(id));
  ipcMain.handle('tabs:switch', (_, id) => switchTab(id));
  ipcMain.handle('nav:go', (_, input) => navigateActive(input));
  ipcMain.handle('nav:back', () => getActiveTab()?.view.webContents.goBack());
  ipcMain.handle('nav:forward', () => getActiveTab()?.view.webContents.goForward());
  ipcMain.handle('nav:reload', () => getActiveTab()?.view.webContents.reload());
  ipcMain.handle('nav:stop', () => getActiveTab()?.view.webContents.stop());

  ipcMain.handle('settings:get', () => ({
    ...settings,
    searchEngines: Object.entries(FREE_SEARCH_ENGINES).map(([id, e]) => ({
      id,
      name: e.name,
    })),
    shieldsStats,
    ghostMode,
  }));

  ipcMain.handle('settings:set', (_, patch) => {
    settings = { ...settings, ...patch };
    saveJson(SETTINGS_PATH, settings);
    configureSession();
    layoutActiveView();
    sendTabsUpdate();
    return settings;
  });

  ipcMain.handle('bookmarks:get', () => bookmarks);
  ipcMain.handle('bookmarks:add', (_, item) => {
    bookmarks.unshift({
      id: Date.now(),
      title: item.title,
      url: item.url,
      time: Date.now(),
    });
    saveJson(BOOKMARKS_PATH, bookmarks);
    return bookmarks;
  });
  ipcMain.handle('bookmarks:remove', (_, id) => {
    bookmarks = bookmarks.filter((b) => b.id !== id);
    saveJson(BOOKMARKS_PATH, bookmarks);
    return bookmarks;
  });

  ipcMain.handle('history:get', () => history.slice(0, 100));

  ipcMain.handle('app:openExternal', (_, url) => shell.openExternal(url));

  ipcMain.on('start:navigate', (_, url) => navigateActive(url));
  ipcMain.on('start:search', (_, query) => navigateActive(query));
}

app.whenReady().then(() => {
  configureSession();
  registerIPC();
  createMainWindow();
  createTab(settings.homepage);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
      createTab(settings.homepage);
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
