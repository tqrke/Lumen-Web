"""Minimal threat block page."""

from urllib.parse import quote


def threat_block_html(url: str, reason: str, colors: dict) -> str:
    c = colors
    safe_url = quote(url, safe="")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Site blocked</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{
  font-family:"Segoe UI Variable","Segoe UI",system-ui,sans-serif;
  background:{c['bg0']};color:{c['text']};
  min-height:100vh;display:flex;align-items:center;justify-content:center;padding:40px;
}}
.card{{max-width:480px;width:100%;padding:48px 40px;text-align:center}}
h1{{font-size:22px;font-weight:600;margin-bottom:12px;color:{c['text']}}}
.reason{{color:{c['text_muted']};font-size:14px;line-height:1.6;margin-bottom:24px}}
.url{{
  font-size:12px;color:{c['text_muted']};word-break:break-all;
  padding:12px 16px;background:{c['bg2']};border-radius:4px;
  border:1px solid {c['border']};margin-bottom:32px;text-align:left;
}}
.actions{{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}}
.btn{{
  display:inline-block;padding:10px 24px;border-radius:4px;font-size:13px;
  text-decoration:none;font-weight:500;
}}
.primary{{background:{c['primary']};color:#fff}}
.ghost{{background:transparent;color:{c['text']};border:1px solid {c['border']}}}
</style></head><body>
<div class="card">
  <h1>This site has been blocked</h1>
  <p class="reason">{reason}</p>
  <div class="url">{url}</div>
  <div class="actions">
    <a class="btn primary" href="lumen://start">Return home</a>
    <a class="btn ghost" href="lumen://force?{safe_url}">Continue anyway</a>
  </div>
</div>
</body></html>"""
