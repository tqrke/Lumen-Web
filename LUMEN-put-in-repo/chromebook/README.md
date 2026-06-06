# LUMEN for Chromebook

One download → install in Chrome → use voice like on Windows. **Tesco runs in Chrome** (not Edge).

## Build the Chromebook release (you, the developer)

```powershell
cd chromebook
python build_release.py
```

Output: **`dist/LUMEN-Chromebook-1.0.0.zip`**

Upload that ZIP to Google Drive, your website, or GitHub Releases.

---

## Users: install on a Chromebook

1. **Download** `LUMEN-Chromebook-1.0.0.zip` and **unzip** it.
2. Open **Chrome** → go to **`chrome://extensions`**
3. Turn **Developer mode** **ON** (top-right).
4. Click **Load unpacked**.
5. Choose the **`lumen-extension`** folder from inside the zip.
6. **Pin** LUMEN Mind (puzzle icon in the toolbar).
7. Click the **LUMEN** icon → side panel opens.
8. Tap **Tap to speak** → allow **microphone**.

A welcome tab opens on first install with the same steps.

---

## Using LUMEN (same ideas as Windows)

| Say | What happens |
|-----|----------------|
| open Tesco | Tesco opens in the **current Chrome tab** |
| search spaghetti | Tesco search in Chrome |
| search → then milk | Two-step search (like Windows) |
| scroll | Slow auto-scroll |
| stop | Stop scrolling |
| up / scroll up | Small scroll back |
| open YouTube, weather, maps | Opens in Chrome |

**Keep listening** is on by default — after each command it listens again (like conversation mode on Windows).

---

## Windows vs Chromebook

| | Windows | Chromebook |
|--|---------|------------|
| Download | `LUMEN-Browser-*.zip` | `LUMEN-Chromebook-*.zip` |
| App | `.exe` + folder | Chrome extension |
| Browser | Built-in LUMEN + Edge for Tesco | **Chrome tabs** for everything |
| Wake word “Lumen” | Yes | Tap to speak (Chrome limit) |
| Tesco | Microsoft Edge window | **Google Chrome tab** |

---

## 100% free — no Chrome Web Store

You **do not** need to pay Google or upload to the Web Store. Ship the ZIP for free (GitHub Releases, Google Drive, USB). Users install with **Load unpacked** — see **`FREE-DISTRIBUTION.md`** and **`START-HERE.html`** in the ZIP.

The Web Store is optional (Google charges developers $5 once, not users). Stay off the store if you want zero cost and full control.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Mic not working | Chrome settings → Privacy → Microphone → allow for Chrome |
| Scroll does nothing | Be on a real page (Tesco), not `chrome://` or blank new tab |
| Extension won’t load | Use **Load unpacked** on the `lumen-extension` folder, not the zip |
| “Speech not supported” | Use Google Chrome (not a minimal browser) |
