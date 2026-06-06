"""Auto-dismiss cookie consent banners on page load."""

COOKIE_DISMISS_JS = """
(function lumenCookieAccept(){
  if (window.__lumenCookiesDone) return;
  window.__lumenCookiesDone = true;
  const labels = [
    'accept all','accept cookies','allow all','allow cookies','i agree','agree all',
    'got it','ok','accept & continue','accept and continue','yes, i agree',
    'accept recommended','accept essential','continue','agree and proceed'
  ];
  const selectors = [
    '#onetrust-accept-btn-handler','#accept-cookie-notification',
    '.accept-cookies','.cookie-accept','.js-accept-cookies','.cc-accept',
    '[data-testid="accept"]','[data-testid="uc-accept-all-button"]',
    'button[id*="accept" i]','button[class*="accept" i]',
    'a[id*="accept" i]','#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
    '.fc-cta-consent','.pm-accept-all','.truste-button2'
  ];
  function tryClick(el){
    try { el.click(); return true; } catch(e) { return false; }
  }
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && tryClick(el)) return;
  }
  const nodes = document.querySelectorAll('button, a, input[type=button], [role=button]');
  for (const el of nodes) {
    const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().toLowerCase();
    if (!t || t.length > 48) continue;
    if (labels.some(l => t === l || t.includes(l))) {
      if (tryClick(el)) return;
    }
  }
})();
"""
