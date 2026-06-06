/** Voice commands — parity with LUMEN Windows (Chrome / Tesco in Chrome tabs). */

const TESCO_HOME = "https://www.tesco.com/groceries/en-GB/";
const TESCO_SEARCH = (q) =>
  `https://www.tesco.com/groceries/en-GB/search?query=${encodeURIComponent(q)}`;

const SITES = {
  youtube: "https://www.youtube.com",
  google: "https://www.google.com",
  gmail: "https://mail.google.com",
  maps: "https://www.google.com/maps",
  tesco: TESCO_HOME,
  sainsburys: "https://www.sainsburys.co.uk/shop/gb/groceries",
  sainsbury: "https://www.sainsburys.co.uk/shop/gb/groceries",
  asda: "https://www.asda.com/groceries",
  morrisons: "https://groceries.morrisons.com/",
  netflix: "https://www.netflix.com",
  spotify: "https://open.spotify.com",
  github: "https://github.com",
  wikipedia: "https://wikipedia.org",
};

const ITEM_TYPOS = {
  spagetti: "spaghetti",
  spaghett: "spaghetti",
  tomatos: "tomatoes",
  potatos: "potatoes",
  bred: "bread",
  milc: "milk",
  chese: "cheese",
};

export function normalize(text) {
  return (text || "")
    .toLowerCase()
    .replace(/[^\w\s']/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function fixItem(item) {
  const t = normalize(item);
  return ITEM_TYPOS[t] || t;
}

export function parseCommand(raw) {
  let t = normalize(raw);
  t = t.replace(/\bscroll\s+(you|uo|oop)\b/g, "scroll up");
  if (t === "up" || t === "up a bit" || t === "up a little") t = "scroll up";
  if (["scope", "scott", "scrope", "scoop"].includes(t)) t = "scroll up";

  if (/^stop(?:\s+scroll(?:ing)?)?$/.test(t) || t === "halt") {
    return { kind: "scroll", action: "stop", reply: "Stopped scrolling." };
  }
  if (
    /^(?:up(?:\s+(?:a\s+)?(?:bit|little))?|scroll\s+up(?:\s+(?:a\s+)?(?:bit|little))?|nudge\s+up)/.test(
      t
    )
  ) {
    return { kind: "scroll", action: "nudge_up", reply: "Scrolled up a little." };
  }
  if (/^(?:scroll(?:\s+down)?|start\s+scroll(?:ing)?|scroll\s+the\s+page)$/.test(t)) {
    return { kind: "scroll", action: "start", reply: "Scrolling slowly. Say stop to halt." };
  }

  if (/^(?:go\s+)?back$/.test(t) || t === "previous page") {
    return { kind: "back", reply: "Going back." };
  }
  if (t === "reload" || t === "refresh") {
    return { kind: "reload", reply: "Refreshing." };
  }

  const open = t.match(
    /^(?:open|go to|visit|launch)\s+(youtube|google|gmail|maps|tesco|sainsburys|sainsbury|asda|morrisons|netflix|spotify|github|wikipedia)\s*$/
  );
  if (open) {
    const key = open[1] === "sainsbury" ? "sainsburys" : open[1];
    return { kind: "navigate", url: SITES[key], reply: `Opening ${open[1]}.` };
  }
  if (t in SITES) {
    return { kind: "navigate", url: SITES[t], reply: `Opening ${t}.` };
  }

  const search = t.match(/^search(?:\s+for)?\s+(.+)$/);
  if (search && !/\b(?:the web|on google|online)\b/.test(t)) {
    const item = fixItem(search[1]);
    return {
      kind: "navigate",
      url: TESCO_SEARCH(item),
      reply: `Searching Tesco for ${item}.`,
    };
  }

  if (t === "search" || t === "search for") {
    return { kind: "pending", prefix: "search", reply: "Say the item — e.g. spaghetti, milk." };
  }

  const add = t.match(/^(?:add|put|get|buy)\s+(?:some\s+)?(.+)$/);
  if (add) {
    const item = fixItem(add[1]);
    return {
      kind: "navigate",
      url: TESCO_SEARCH(item),
      reply: `Searching Tesco to add ${item}. Tap Add on the product.`,
    };
  }

  const weather = t.match(/^weather(?:\s+(?:in|for|at))?\s*(.*)$/);
  if (t === "weather" || weather) {
    const place = (weather?.[1] || "London").trim() || "London";
    return {
      kind: "navigate",
      url: `https://www.google.com/search?q=weather+in+${encodeURIComponent(place)}`,
      reply: `Weather for ${place}.`,
    };
  }

  return null;
}

export function combinePending(prefix, rest) {
  const p = normalize(prefix);
  const r = (rest || "").trim();
  if (!r) return null;
  if (p === "search" || p === "search for") {
    return parseCommand(`search ${r}`);
  }
  return parseCommand(`${p} ${r}`);
}
