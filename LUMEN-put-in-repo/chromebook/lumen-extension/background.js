import { parseCommand, combinePending } from "./commands.js";

const VERSION = "1.0.0";

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === "install" || details.reason === "update") {
    chrome.storage.local.set({ lumen_version: VERSION });
    if (details.reason === "install") {
      chrome.tabs.create({ url: chrome.runtime.getURL("welcome.html") });
    }
  }
});

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function runScroll(action) {
  const tab = await getActiveTab();
  if (!tab?.id) return { ok: false, error: "No active tab." };
  const u = tab.url || "";
  if (u.startsWith("chrome://") || u.startsWith("chrome-extension://") || u === "chrome://newtab/") {
    return { ok: false, error: "Open Tesco or a webpage first, then say scroll." };
  }
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (act) => {
        const API = "__lumenScroll";
        if (act === "start") {
          if (window[API]?.active) return "already-scrolling";
          const state = {
            active: true,
            rafId: null,
            stop() {
              this.active = false;
              if (this.rafId != null) cancelAnimationFrame(this.rafId);
            },
          };
          window[API] = state;
          const tick = () => {
            if (!state.active) return;
            const root = document.scrollingElement || document.documentElement;
            const maxY = Math.max(0, root.scrollHeight - window.innerHeight);
            if (window.scrollY < maxY - 1) window.scrollBy(0, 1.5);
            state.rafId = requestAnimationFrame(tick);
          };
          tick();
          return "scrolling";
        }
        if (act === "stop") {
          window[API]?.stop?.();
          return "scroll-stopped";
        }
        if (act === "nudge_up") {
          window[API]?.stop?.();
          window.scrollBy(0, -72);
          return "nudge-up";
        }
        return "none";
      },
      args: [action],
    });
    return { ok: true, result };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

async function navigate(url) {
  const tab = await getActiveTab();
  if (tab?.id && !tab.url?.startsWith("chrome-extension://")) {
    await chrome.tabs.update(tab.id, { url });
    return { ok: true };
  }
  await chrome.tabs.create({ url });
  return { ok: true };
}

async function goBack() {
  const tab = await getActiveTab();
  if (tab?.id) {
    await chrome.tabs.goBack(tab.id);
    return { ok: true };
  }
  return { ok: false, error: "No tab." };
}

async function reloadTab() {
  const tab = await getActiveTab();
  if (tab?.id) {
    await chrome.tabs.reload(tab.id);
    return { ok: true };
  }
  return { ok: false, error: "No tab." };
}

export async function handleVoiceText(text) {
  const { pending_prefix: pending } = await chrome.storage.session.get("pending_prefix");
  let cmd = pending ? combinePending(pending, text) : parseCommand(text);
  if (!cmd && pending) {
    await chrome.storage.session.remove("pending_prefix");
    cmd = parseCommand(text);
  }
  if (!cmd) {
    return { ok: false, reply: "Try: open Tesco, search milk, scroll, stop, up." };
  }
  if (cmd.kind === "pending") {
    await chrome.storage.session.set({ pending_prefix: cmd.prefix });
    return { ok: true, reply: cmd.reply };
  }
  await chrome.storage.session.remove("pending_prefix");

  if (cmd.kind === "navigate") {
    await navigate(cmd.url);
    return { ok: true, reply: cmd.reply };
  }
  if (cmd.kind === "back") {
    const r = await goBack();
    return { ok: r.ok, reply: r.ok ? cmd.reply : r.error };
  }
  if (cmd.kind === "reload") {
    const r = await reloadTab();
    return { ok: r.ok, reply: r.ok ? cmd.reply : r.error };
  }
  if (cmd.kind === "scroll") {
    const r = await runScroll(cmd.action);
    return { ok: r.ok, reply: r.ok ? cmd.reply : r.error };
  }
  return { ok: false, reply: "Unknown command." };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "lumen:command") {
    handleVoiceText(msg.text).then(sendResponse);
    return true;
  }
  if (msg.type === "lumen:open-tesco") {
    navigate("https://www.tesco.com/groceries/en-GB/").then(() =>
      sendResponse({ ok: true, reply: "Opening Tesco in Chrome." })
    );
    return true;
  }
});
