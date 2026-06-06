"""Run pause/play/stop/mute/volume on the active page (YouTube, Spotify, HTML5 players)."""

_VOLUME_STEP = 10

_YT_PLAYER_JS = """
function _lumenPlayer() {
  const p = document.getElementById('movie_player');
  if (p && typeof p.getVolume === 'function') return p;
  return null;
}
function _lumenVideo() {
  return document.querySelector('video.html5-main-video')
    || document.querySelector('#movie_player video')
    || document.querySelector('video');
}
function _lumenSendKey(key, code, keyCode) {
  const opts = { key, code, keyCode, which: keyCode, bubbles: true, cancelable: true };
  const targets = [
    document.querySelector('#movie_player'),
    _lumenVideo(),
    document.activeElement,
    document.body,
  ].filter(Boolean);
  for (const t of targets) {
    try { t.focus(); } catch (e) {}
    t.dispatchEvent(new KeyboardEvent('keydown', opts));
    t.dispatchEvent(new KeyboardEvent('keyup', opts));
  }
  document.dispatchEvent(new KeyboardEvent('keydown', opts));
  document.dispatchEvent(new KeyboardEvent('keyup', opts));
}
function _lumenVisible(el) {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 8 && r.height > 8 && r.bottom > 0 && r.top < (window.innerHeight || 800);
}
function _lumenWatchHref(el) {
  if (!el) return '';
  const href = el.href || el.getAttribute('href') || '';
  if (!href || href.includes('googleads') || href.includes('shorts')) return '';
  if (!href.includes('/watch')) return '';
  return href.split('&list=')[0];
}
function _lumenResultLinks() {
  const selectors = [
    'ytd-rich-item-renderer a#video-title-link',
    'ytd-rich-item-renderer a#video-title',
    'ytd-rich-grid-media a#video-title-link',
    'ytd-rich-grid-media a#video-title',
    'ytd-video-renderer a#video-title-link',
    'ytd-video-renderer a#video-title',
    'ytd-video-renderer a.yt-simple-endpoint',
    'ytd-grid-video-renderer a#video-title',
    'ytd-item-section-renderer a#video-title-link',
    'ytd-browse-video-action-renderer a#video-title',
    'a#video-title-link.yt-simple-endpoint',
    'a#video-title.yt-simple-endpoint',
  ];
  const links = [];
  const seen = new Set();
  for (const sel of selectors) {
    for (const link of document.querySelectorAll(sel)) {
      const href = _lumenWatchHref(link);
      if (!href || seen.has(href)) continue;
      if (!_lumenVisible(link)) continue;
      seen.add(href);
      links.push(link);
    }
  }
  if (!links.length) {
    for (const link of document.querySelectorAll('a[href*="/watch?v="]')) {
      const href = _lumenWatchHref(link);
      if (!href || seen.has(href)) continue;
      if (!_lumenVisible(link)) continue;
      seen.add(href);
      links.push(link);
    }
  }
  if (!links.length) {
    const thumb = document.querySelector('ytd-video-renderer a#thumbnail[href*="/watch"]')
      || document.querySelector('ytd-rich-item-renderer a#thumbnail[href*="/watch"]');
    if (thumb) {
      const href = _lumenWatchHref(thumb);
      if (href) links.push(thumb);
    }
  }
  return links;
}
"""


def _video_at_index_js(index: int) -> str:
    idx = max(0, int(index) - 1)
    return _YT_PLAYER_JS + f"""
(() => {{
  const links = _lumenResultLinks();
  const link = links[{idx}];
  if (link) {{
    try {{ link.scrollIntoView({{ block: 'center', behavior: 'instant' }}); }} catch (e) {{}}
    const href = _lumenWatchHref(link) || link.href;
    if (href) {{
      try {{ link.click(); return href; }} catch (e) {{}}
      window.location.assign(href);
      return href;
    }}
  }}
  return 'none:' + links.length;
}})()
"""

MEDIA_CONTROL_JS = {
    "pause": _YT_PLAYER_JS + """
(() => {
  const p = _lumenPlayer();
  if (p && typeof p.pauseVideo === 'function') { p.pauseVideo(); return 'yt-pause'; }
  const v = _lumenVideo();
  if (v) { v.pause(); return 'paused'; }
  const yt = document.querySelector('.ytp-play-button');
  if (yt && /pause/i.test(yt.getAttribute('aria-label') || '')) { yt.click(); return 'yt-btn'; }
  const btn = document.querySelector('button[aria-label*="Pause" i], [data-testid="control-button-pause"]');
  if (btn) { btn.click(); return 'btn-paused'; }
  return 'none';
})()
""",
    "play": _YT_PLAYER_JS + """
(() => {
  const p = _lumenPlayer();
  if (p && typeof p.playVideo === 'function') { p.playVideo(); return 'yt-play'; }
  const v = _lumenVideo();
  if (v) { v.play().catch(() => {}); return 'playing'; }
  const yt = document.querySelector('.ytp-play-button');
  if (yt && /play/i.test(yt.getAttribute('aria-label') || '')) { yt.click(); return 'yt-btn'; }
  const btn = document.querySelector('button[aria-label*="Play" i], [data-testid="control-button-play"]');
  if (btn) { btn.click(); return 'btn-playing'; }
  return 'none';
})()
""",
    "stop": _YT_PLAYER_JS + """
(() => {
  const p = _lumenPlayer();
  if (p && typeof p.stopVideo === 'function') { p.stopVideo(); return 'yt-stop'; }
  const els = document.querySelectorAll('video, audio');
  for (const el of els) {
    el.pause();
    try { el.currentTime = 0; } catch (e) {}
  }
  return els.length ? 'stopped' : 'none';
})()
""",
    "mute": _YT_PLAYER_JS + """
(() => {
  const p = _lumenPlayer();
  if (p && typeof p.mute === 'function') {
    if (typeof p.isMuted === 'function' && p.isMuted()) return 'already-muted';
    p.mute();
    return 'yt-muted';
  }
  const btn = document.querySelector('button.ytp-mute-button, .ytp-mute-button');
  if (btn) {
    const label = (btn.getAttribute('data-title-no-tooltip') || btn.getAttribute('aria-label') || '').toLowerCase();
    if (label.includes('unmute')) return 'already-muted';
    btn.click();
    return 'yt-btn-mute';
  }
  const v = _lumenVideo();
  if (v) { v.muted = true; return 'video-muted'; }
  _lumenSendKey('m', 'KeyM', 77);
  return 'key-m';
})()
""",
    "unmute": _YT_PLAYER_JS + """
(() => {
  const p = _lumenPlayer();
  if (p && typeof p.unMute === 'function') {
    if (typeof p.isMuted === 'function' && !p.isMuted()) return 'already-unmuted';
    p.unMute();
    return 'yt-unmuted';
  }
  const btn = document.querySelector('button.ytp-mute-button, .ytp-mute-button');
  if (btn) {
    const label = (btn.getAttribute('data-title-no-tooltip') || btn.getAttribute('aria-label') || '').toLowerCase();
    if (label.includes('unmute')) { btn.click(); return 'yt-btn-unmute'; }
    return 'already-unmuted';
  }
  const v = _lumenVideo();
  if (v) { v.muted = false; return 'video-unmuted'; }
  _lumenSendKey('m', 'KeyM', 77);
  return 'key-m';
})()
""",
    "volume_up": _YT_PLAYER_JS + f"""
(() => {{
  const step = {_VOLUME_STEP};
  const p = _lumenPlayer();
  if (p && typeof p.setVolume === 'function') {{
    const cur = typeof p.getVolume === 'function' ? p.getVolume() : 50;
    p.setVolume(Math.min(100, cur + step));
    if (typeof p.isMuted === 'function' && p.isMuted() && typeof p.unMute === 'function') p.unMute();
    return 'yt-vol-up';
  }}
  const v = _lumenVideo();
  if (v) {{
    v.muted = false;
    v.volume = Math.min(1, v.volume + step / 100);
    return 'video-vol-up';
  }}
  _lumenSendKey('ArrowUp', 'ArrowUp', 38);
  return 'key-up';
}})()
""",
    "volume_down": _YT_PLAYER_JS + f"""
(() => {{
  const step = {_VOLUME_STEP};
  const p = _lumenPlayer();
  if (p && typeof p.setVolume === 'function') {{
    const cur = typeof p.getVolume === 'function' ? p.getVolume() : 50;
    p.setVolume(Math.max(0, cur - step));
    return 'yt-vol-down';
  }}
  const v = _lumenVideo();
  if (v) {{
    v.volume = Math.max(0, v.volume - step / 100);
    return 'video-vol-down';
  }}
  _lumenSendKey('ArrowDown', 'ArrowDown', 40);
  return 'key-down';
}})()
""",
    "first_video": _video_at_index_js(1),
    "video_1": _video_at_index_js(1),
    "video_2": _video_at_index_js(2),
    "video_3": _video_at_index_js(3),
    "video_4": _video_at_index_js(4),
    "video_5": _video_at_index_js(5),
}
