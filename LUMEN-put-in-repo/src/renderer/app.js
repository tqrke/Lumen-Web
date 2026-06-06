/* LUMEN Browser — UI Controller */

let state = {
  tabs: [],
  activeTabId: null,
  url: '',
  title: '',
  canGoBack: false,
  canGoForward: false,
  loading: false,
  secure: true,
  shields: { blocked: 0, savedBytes: 0 },
  ghostMode: false,
  settings: null,
};

const $ = (sel) => document.querySelector(sel);
const tabBar = $('#tab-bar');
const omnibox = $('#omnibox');
const panel = $('#panel');
const panelTitle = $('#panel-title');
const panelContent = $('#panel-content');

function init() {
  bindEvents();
  loadSettings();

  window.lumen.tabs.onUpdated((data) => {
    state.tabs = data.tabs;
    state.activeTabId = data.activeTabId;
    state.ghostMode = data.ghostMode;
    renderTabs();
    updateGhostBadge();
  });

  window.lumen.nav.onState((data) => {
    Object.assign(state, data);
    updateNavUI();
  });
}

function bindEvents() {
  $('#btn-new-tab').addEventListener('click', () => window.lumen.tabs.create());
  $('#btn-back').addEventListener('click', () => window.lumen.nav.back());
  $('#btn-forward').addEventListener('click', () => window.lumen.nav.forward());
  $('#btn-reload').addEventListener('click', () => window.lumen.nav.reload());

  omnibox.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      window.lumen.nav.go(omnibox.value);
      omnibox.blur();
    }
  });

  omnibox.addEventListener('focus', () => omnibox.select());

  $('#btn-bookmark-page').addEventListener('click', bookmarkCurrentPage);
  $('#btn-bookmarks').addEventListener('click', () => showPanel('Bookmarks', renderBookmarks));
  $('#btn-history').addEventListener('click', () => showPanel('History', renderHistory));
  $('#btn-shields').addEventListener('click', () => showPanel('LUMEN Shields', renderShields));
  $('#btn-settings').addEventListener('click', () => showPanel('Settings', renderSettings));
  $('#panel-close').addEventListener('click', hidePanel);

  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey) {
      if (e.key === 't') { e.preventDefault(); window.lumen.tabs.create(); }
      if (e.key === 'w') { e.preventDefault(); if (state.activeTabId) window.lumen.tabs.close(state.activeTabId); }
      if (e.key === 'l') { e.preventDefault(); omnibox.focus(); omnibox.select(); }
      if (e.key === 'r') { e.preventDefault(); window.lumen.nav.reload(); }
    }
    if (e.key === 'Escape') hidePanel();
  });
}

async function loadSettings() {
  state.settings = await window.lumen.settings.get();
  updateGhostBadge();
}

function renderTabs() {
  tabBar.innerHTML = '';
  state.tabs.forEach((tab) => {
    const el = document.createElement('div');
    el.className = 'tab' + (tab.id === state.activeTabId ? ' active' : '') + (tab.loading ? ' tab-loading' : '');
    el.innerHTML = `
      <span class="tab-title">${escapeHtml(tab.title || 'New Tab')}</span>
      <button class="tab-close" title="Close">×</button>
    `;
    el.addEventListener('click', (e) => {
      if (e.target.classList.contains('tab-close')) {
        window.lumen.tabs.close(tab.id);
      } else {
        window.lumen.tabs.switch(tab.id);
      }
    });
    tabBar.appendChild(el);
  });
}

function updateNavUI() {
  omnibox.value = state.url.startsWith('lumen://') ? '' : state.url;
  $('#btn-back').disabled = !state.canGoBack;
  $('#btn-forward').disabled = !state.canGoForward;

  const secureIcon = $('#secure-icon');
  if (state.url.startsWith('https://')) {
    secureIcon.textContent = '🔒';
    secureIcon.className = 'secure-icon secure';
  } else if (state.url.startsWith('http://')) {
    secureIcon.textContent = '⚠';
    secureIcon.className = 'secure-icon insecure';
  } else {
    secureIcon.textContent = '◆';
    secureIcon.className = 'secure-icon';
  }

  const blocked = state.shields?.blocked ?? 0;
  $('#shields-badge').textContent = `🛡 ${blocked}`;
}

function updateGhostBadge() {
  $('#ghost-badge').classList.toggle('hidden', !state.ghostMode);
}

async function bookmarkCurrentPage() {
  if (!state.url || state.url.startsWith('lumen://')) return;
  await window.lumen.bookmarks.add({ title: state.title || state.url, url: state.url });
  $('#btn-bookmark-page').textContent = '★';
  setTimeout(() => { $('#btn-bookmark-page').textContent = '☆'; }, 1000);
}

function showPanel(title, renderFn) {
  panelTitle.textContent = title;
  panelContent.innerHTML = '';
  panel.classList.remove('hidden');
  renderFn();
}

function hidePanel() {
  panel.classList.add('hidden');
}

async function renderBookmarks() {
  const bookmarks = await window.lumen.bookmarks.get();
  if (bookmarks.length === 0) {
    panelContent.innerHTML = '<p class="empty-state">No bookmarks yet. Click ☆ in the toolbar to save a page.</p>';
    return;
  }
  bookmarks.forEach((b) => {
    const el = document.createElement('div');
    el.className = 'panel-item';
    el.innerHTML = `<div class="panel-item-title">${escapeHtml(b.title)}</div><div class="panel-item-url">${escapeHtml(b.url)}</div>`;
    el.addEventListener('click', () => {
      window.lumen.nav.go(b.url);
      hidePanel();
    });
    panelContent.appendChild(el);
  });
}

async function renderHistory() {
  const history = await window.lumen.history.get();
  if (history.length === 0) {
    panelContent.innerHTML = '<p class="empty-state">No browsing history yet.</p>';
    return;
  }
  history.forEach((h) => {
    const el = document.createElement('div');
    el.className = 'panel-item';
    el.innerHTML = `<div class="panel-item-title">${escapeHtml(h.title)}</div><div class="panel-item-url">${escapeHtml(h.url)}</div>`;
    el.addEventListener('click', () => {
      window.lumen.nav.go(h.url);
      hidePanel();
    });
    panelContent.appendChild(el);
  });
}

async function renderShields() {
  const settings = await window.lumen.settings.get();
  const saved = Math.round((settings.shieldsStats?.savedBytes ?? 0) / 1024);
  panelContent.innerHTML = `
    <p class="panel-desc">LUMEN Shields blocks trackers and ads using free, open filter lists. No paid services required.</p>
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-value">${settings.shieldsStats?.blocked ?? 0}</div>
        <div class="stat-label">Trackers Blocked</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${saved} KB</div>
        <div class="stat-label">Data Saved</div>
      </div>
    </div>
    <div class="setting-row">
      <label>Block trackers & ads</label>
      <input type="checkbox" id="set-block" ${settings.blockTrackers ? 'checked' : ''} />
    </div>
    <div class="setting-row">
      <label>HTTPS-Only mode</label>
      <input type="checkbox" id="set-https" ${settings.httpsOnly ? 'checked' : ''} />
    </div>
    <div class="setting-row">
      <label>Privacy tier</label>
      <select id="set-tier">
        <option value="standard" ${settings.privacyTier === 'standard' ? 'selected' : ''}>Standard</option>
        <option value="enhanced" ${settings.privacyTier === 'enhanced' ? 'selected' : ''}>Enhanced</option>
        <option value="paranoid" ${settings.privacyTier === 'paranoid' ? 'selected' : ''}>Paranoid</option>
      </select>
    </div>
  `;

  const save = async () => {
    await window.lumen.settings.set({
      blockTrackers: $('#set-block').checked,
      httpsOnly: $('#set-https').checked,
      privacyTier: $('#set-tier').value,
    });
  };

  $('#set-block').addEventListener('change', save);
  $('#set-https').addEventListener('change', save);
  $('#set-tier').addEventListener('change', save);
}

async function renderSettings() {
  const settings = await window.lumen.settings.get();
  const engineOptions = settings.searchEngines
    .map((e) => `<option value="${e.id}" ${settings.searchEngine === e.id ? 'selected' : ''}>${escapeHtml(e.name)}</option>`)
    .join('');

  panelContent.innerHTML = `
    <p class="panel-desc">All features are 100% free. No Google APIs, no subscriptions, no paid integrations.</p>
    <div class="setting-row">
      <label>Search engine</label>
      <select id="set-engine">${engineOptions}</select>
    </div>
    <div class="setting-row">
      <label>Block trackers</label>
      <input type="checkbox" id="set-block2" ${settings.blockTrackers ? 'checked' : ''} />
    </div>
    <div class="setting-row">
      <label>HTTPS-Only</label>
      <input type="checkbox" id="set-https2" ${settings.httpsOnly ? 'checked' : ''} />
    </div>
    <div class="setting-row">
      <label>Privacy tier</label>
      <select id="set-tier2">
        <option value="standard" ${settings.privacyTier === 'standard' ? 'selected' : ''}>Standard</option>
        <option value="enhanced" ${settings.privacyTier === 'enhanced' ? 'selected' : ''}>Enhanced</option>
        <option value="paranoid" ${settings.privacyTier === 'paranoid' ? 'selected' : ''}>Paranoid</option>
      </select>
    </div>
    <p class="panel-desc" style="margin-top:16px">
      Free search engines: DuckDuckGo, Brave Search, SearXNG, Wikipedia.<br/>
      Ghost Mode: File → New Ghost Window (Ctrl+Shift+N)
    </p>
  `;

  const save = async () => {
    await window.lumen.settings.set({
      searchEngine: $('#set-engine').value,
      blockTrackers: $('#set-block2').checked,
      httpsOnly: $('#set-https2').checked,
      privacyTier: $('#set-tier2').value,
    });
    loadSettings();
  };

  $('#set-engine').addEventListener('change', save);
  $('#set-block2').addEventListener('change', save);
  $('#set-https2').addEventListener('change', save);
  $('#set-tier2').addEventListener('change', save);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

init();
