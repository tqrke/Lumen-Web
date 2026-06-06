"""Voice grocery shopping — search and add items on Tesco and other UK stores."""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

GROCERY_STORES: dict[str, str] = {
    "tesco": "https://www.tesco.com/groceries/en-GB/",
    "sainsburys": "https://www.sainsburys.co.uk/shop/gb/groceries",
    "sainsbury": "https://www.sainsburys.co.uk/shop/gb/groceries",
    "asda": "https://www.asda.com/groceries",
    "morrisons": "https://groceries.morrisons.com/",
    "ocado": "https://www.ocado.com/",
    "waitrose": "https://www.waitrose.com/ecom/shop/browse/groceries",
    "iceland": "https://www.iceland.co.uk/",
    "aldi": "https://www.aldi.co.uk/",
}

GROCERY_HOSTS = tuple(
    host
    for hosts in (
        ("tesco.com",),
        ("sainsburys.co.uk",),
        ("asda.com",),
        ("morrisons.com",),
        ("ocado.com",),
        ("waitrose.com",),
        ("iceland.co.uk",),
        ("aldi.co.uk",),
    )
    for host in hosts
)

_ITEM_TYPOS: dict[str, str] = {
    "spagetti": "spaghetti",
    "spaghett": "spaghetti",
    "spagetti pasta": "spaghetti",
    "tomatos": "tomatoes",
    "potatos": "potatoes",
    "bred": "bread",
    "milc": "milk",
    "chese": "cheese",
    "bananna": "banana",
    "strawberrys": "strawberries",
}


def normalize_item(item: str) -> str:
    t = re.sub(r"\s+", " ", item.strip().lower())
    t = re.sub(r"\s+(please|thanks|thank you)$", "", t)
    return _ITEM_TYPOS.get(t, t)


def is_grocery_url(url: str) -> bool:
    low = (url or "").lower()
    return any(h in low for h in GROCERY_HOSTS)


def store_url(name: str) -> str | None:
    return GROCERY_STORES.get(name.strip().lower())


def tesco_search_url(item: str) -> str:
    """Direct Tesco search URL — works without page JavaScript."""
    q = quote_plus(normalize_item(item))
    return f"https://www.tesco.com/groceries/en-GB/search?query={q}"


_GROCERY_JS = r"""
function _lumenVisible(el) {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 4 && r.height > 4 && r.bottom > 0;
}
function _lumenClickAdd() {
  const selectors = [
    'button[data-auto="product-add-button"]',
    'button[data-auto="add-button"]',
    'button[data-auto="add-to-basket-button"]',
    'button[aria-label*="Add" i]',
    'button[aria-label*="add to" i]',
    'button[class*="add-to-basket" i]',
    'button[class*="AddToBasket" i]',
    '[data-test="add-button"]',
    'button.ddsweb-button[data-auto*="add" i]',
  ];
  for (const sel of selectors) {
    for (const btn of document.querySelectorAll(sel)) {
      if (!_lumenVisible(btn)) continue;
      const label = (btn.getAttribute('aria-label') || btn.textContent || '').toLowerCase();
      if (label.includes('remove') || label.includes('delete')) continue;
      try { btn.click(); return 'added:' + sel; } catch (e) {}
    }
  }
  const tiles = document.querySelectorAll(
    '[data-auto="product-tile"], [data-auto="product-list-item"], li[class*="ProductTile"], article[class*="product"]'
  );
  for (const tile of tiles) {
    const btn = tile.querySelector('button');
    if (!btn || !_lumenVisible(btn)) continue;
    const label = (btn.getAttribute('aria-label') || btn.textContent || '').toLowerCase();
    if (label.includes('add') || label.includes('basket') || label.includes('trolley')) {
      try { btn.click(); return 'added:tile'; } catch (e) {}
    }
  }
  return 'none';
}
function _lumenSearch(item) {
  const selectors = [
    'input[data-auto="search-box-input"]',
    'input#search',
    'input[name="searchBox"]',
    'input[type="search"]',
    'input[placeholder*="Search" i]',
    'input[aria-label*="Search" i]',
    'input[data-test="search-input"]',
    'input[class*="search" i]',
  ];
  let input = null;
  for (const sel of selectors) {
    input = document.querySelector(sel);
    if (input && _lumenVisible(input)) break;
    input = null;
  }
  if (!input) return 'no-search';
  input.focus();
  input.value = item;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  const form = input.closest('form');
  if (form) {
    try { form.requestSubmit(); return 'search-submit'; } catch (e) {}
    try { form.submit(); return 'search-submit'; } catch (e) {}
  }
  const enter = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true };
  input.dispatchEvent(new KeyboardEvent('keydown', enter));
  input.dispatchEvent(new KeyboardEvent('keyup', enter));
  const searchBtn = document.querySelector(
    'button[data-auto="search-box-button"], button[type="submit"][aria-label*="Search" i], button.search-button'
  );
  if (searchBtn && _lumenVisible(searchBtn)) {
    try { searchBtn.click(); return 'search-click'; } catch (e) {}
  }
  return 'search-enter';
}
"""


def search_item_js(item: str) -> str:
    """Search Tesco (or current grocery site) for an item — no add to basket."""
    safe = json.dumps(normalize_item(item))
    return _GROCERY_JS + f"(() => _lumenSearch({safe}))()"


def add_item_js(item: str, *, add_only: bool = False) -> str:
    safe = json.dumps(normalize_item(item))
    if add_only:
        return _GROCERY_JS + f"(() => _lumenClickAdd())()"
    return _GROCERY_JS + f"""
(() => {{
  const item = {safe};
  const added = _lumenClickAdd();
  if (added !== 'none') return added;
  return _lumenSearch(item);
}})()
"""


def open_basket_js() -> str:
    return """
(() => {
  const links = document.querySelectorAll('a[href*="basket"], a[href*="trolley"], a[href*="cart"]');
  for (const a of links) {
    const t = (a.textContent || a.getAttribute('aria-label') || '').toLowerCase();
    if (t.includes('basket') || t.includes('trolley') || t.includes('cart')) {
      a.click();
      return 'basket-open';
    }
  }
  const btn = document.querySelector('[data-auto="basket-icon"], [data-auto="trolley-icon"], a[class*="basket"]');
  if (btn) { btn.click(); return 'basket-icon'; }
  return 'none';
})()
"""
