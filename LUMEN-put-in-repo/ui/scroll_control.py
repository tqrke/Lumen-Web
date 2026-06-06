"""Slow auto-scroll on any webpage until the user says stop."""

from __future__ import annotations

# ~90 px/sec at 60fps — readable pace for grocery lists and articles.
_SCROLL_PX_PER_FRAME = 1.5
# One voice "scroll up" — small corrective nudge (~3–4 lines of text).
_NUDGE_UP_PX = 72

START_SCROLL_JS = f"""
(() => {{
  const API = '__lumenScroll';
  if (window[API] && window[API].active) return 'already-scrolling';
  const speed = { _SCROLL_PX_PER_FRAME };
  const state = {{
    active: true,
    rafId: null,
    stop() {{
      this.active = false;
      if (this.rafId != null) {{
        cancelAnimationFrame(this.rafId);
        this.rafId = null;
      }}
    }},
  }};
  window[API] = state;
  const scrollRoot = () =>
    document.scrollingElement || document.documentElement || document.body;
  const tick = () => {{
    if (!state.active) return;
    const root = scrollRoot();
    const maxY = Math.max(
      0,
      Math.max(root.scrollHeight || 0, document.body.scrollHeight || 0)
        - (window.innerHeight || root.clientHeight || 0),
    );
    if ((window.scrollY || root.scrollTop || 0) < maxY - 1) {{
      window.scrollBy(0, speed);
    }}
    state.rafId = requestAnimationFrame(tick);
  }};
  tick();
  return 'scrolling';
}})()
"""

STOP_SCROLL_JS = """
(() => {
  const API = '__lumenScroll';
  if (window[API] && typeof window[API].stop === 'function') {
    window[API].stop();
    return 'scroll-stopped';
  }
  return 'not-scrolling';
})()
"""

NUDGE_UP_JS = f"""
(() => {{
  const API = '__lumenScroll';
  if (window[API] && typeof window[API].stop === 'function') {{
    window[API].stop();
  }}
  window.scrollBy(0, -{_NUDGE_UP_PX});
  return 'nudge-up';
}})()
"""

_SCROLL_JS = {
    "start": START_SCROLL_JS,
    "stop": STOP_SCROLL_JS,
    "nudge_up": NUDGE_UP_JS,
}


def scroll_js_for_action(action: str) -> str:
    return _SCROLL_JS.get(action, START_SCROLL_JS)


def scroll_status_message(action: str) -> tuple[str, str]:
    """Return (status_bar, mind_bubble_subtitle)."""
    if action == "stop":
        return "Stopped scrolling.", "Scrolling halted"
    if action == "nudge_up":
        return "Scrolled up a little.", "Say again to nudge up more"
    return "Scrolling… say stop to halt.", "Say stop when done"
