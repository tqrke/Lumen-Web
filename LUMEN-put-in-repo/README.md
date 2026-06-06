# LUMEN Browser v3.1

**Download, run, talk.** A native Windows browser with **LUMEN Mind** — an accessibility-focused voice assistant for everyday tasks. No Ollama or API keys required.

## For users (download & run)

**Download one file from [Releases](https://github.com/YOUR_USER/lumen-browser/releases):**

| File | What users do |
|------|----------------|
| `LUMEN-Browser-5.0.0-win64.zip` | Unzip → open folder → double-click **LUMEN-Browser.exe** |
| `LUMEN-Browser-Setup.exe` *(optional)* | Run installer → launch from Start menu |

1. Allow **microphone** when Windows asks
2. Say **"Lumen"** or click the floating orb

> **Why a ZIP folder, not one tiny EXE?** LUMEN embeds Chromium (Qt WebEngine) for real web pages. That engine needs DLLs beside the main program — the same reason Chrome ships as a folder. The ZIP is still **one download**; users unzip once and run the exe inside.

**Requirements:** Windows 10/11 64-bit, microphone, internet. **Microsoft Edge** (for Tesco voice shopping) uses the Edge already on the PC — it is not bundled.

### Chromebook

Build: `cd chromebook && python build_release.py` → **`dist/LUMEN-Chromebook-1.0.0.zip`**

Users unzip → Chrome → `chrome://extensions` → Load unpacked → `lumen-extension` folder. Pin LUMEN → tap to speak. **Tesco uses Chrome tabs** (not Edge). See **[chromebook/README.md](chromebook/README.md)**.

### What works without installing anything else

| Feature | Example |
|---------|---------|
| Voice wake | "Lumen" → greeting → speak naturally (no wake needed for 2 min) |
| Continuous talk | After wake, keep giving commands without saying Lumen again |
| Browse by voice | "Open YouTube", "Map of London", "Weather in Paris" |
| Video controls | "Mute", "Volume up", "Play first video", "Play second video", "Go back" |
| Questions | "What is AI?", "Tell me about the Roman Empire" |
| Page summary | "Summarize this page" |
| Spoken replies | Mind speaks confirmations and answers aloud |

Answers use **Wikipedia** and **DuckDuckGo** over the internet — same as a normal browser session.

### Optional (power users only)

If you already run **[Ollama](https://ollama.com)** locally, enable **"Optional: use Ollama"** in Control Center for richer chat. This is **not required** for publishing or for normal users.

---

## For developers

```powershell
cd lumen-browser
pip install -r requirements.txt
python build_icon.py
python app.py
```

### Build for release (publish to users)

```powershell
cd lumen-browser
pip install -r requirements.txt
python build_exe.py --zip
```

| Output | Use |
|--------|-----|
| `dist\LUMEN-Browser\LUMEN-Browser.exe` | Local test |
| `dist\LUMEN-Browser-5.0.0-win64.zip` | **Upload to GitHub Releases** — one download for users |
| `dist\LUMEN-Browser-Setup.exe` | Optional installer (`python build_exe.py --installer` + [Inno Setup 6](https://jrsoftware.org/isdl.php)) |

Or double-click **`build_release.bat`** on Windows.

**Do not** ship only `LUMEN-Browser.exe` without the `_internal` folder and `QtWebEngineProcess.exe` — the browser will not start.

### Code signing (optional, reduces SmartScreen warnings)

Sign the exe with your certificate:

```powershell
signtool sign /fd SHA256 /a dist\LUMEN-Browser\LUMEN-Browser.exe
```

### First-run notes for users

- First launch may download a small **offline voice model** (~40 MB) to `%USERPROFILE%\.lumen\`
- **Internet** needed for browsing, voice fallback STT, TTS, and knowledge answers
- Settings, memory, and logs live in `%USERPROFILE%\.lumen\`

### Diagnostics (support / tuning)

| Log | Purpose |
|-----|---------|
| `%USERPROFILE%\.lumen\voice.log` | Wake word, STT, command routing |
| `%USERPROFILE%\.lumen\tts.log` | Speech output |
| `%USERPROFILE%\.lumen\perf.log` | Slow operations (>120 ms) and session summary |
| `%USERPROFILE%\.lumen\perf_session.json` | Aggregated timing stats on exit |

## Browser features

- Ad/tracker blocking + threat firewall
- Privacy tunnel (local SOCKS5 + encrypted DNS)
- Themes, RAM saver, tab hibernation
- Control Center for shields, voice, search engine, AI options

## License

MIT — see [LICENSE](LICENSE)
