# Distribute LUMEN free (no Chrome Web Store)

You do **not** need the Chrome Web Store. Everything below costs **$0**.

## What you give users

One file: **`dist/LUMEN-Chromebook-1.0.0.zip`**

Build it:

```powershell
cd chromebook
python build_release.py
```

Inside the ZIP:

| File / folder | Purpose |
|---------------|---------|
| `START-HERE.html` | Open in Chrome — install steps (no website needed) |
| `lumen-extension/` | Folder users pick in **Load unpacked** |
| `INSTALL.txt` | Short text version of the steps |

## Free ways to host the ZIP

| Host | Cost | Notes |
|------|------|-------|
| [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github) | Free | Best for updates — attach the ZIP to a release |
| Google Drive | Free | Share link → anyone can download |
| OneDrive / Dropbox | Free | Same |
| USB stick | Free | Schools, family |
| [GitHub Pages](https://pages.github.com/) | Free | Host `START-HERE.html` + link to ZIP |

No developer account, no $5 fee, no user payments.

## What users must do (one-time)

Chromebooks only allow non-store extensions via **Load unpacked** (Developer mode ON). This is normal for free indie extensions.

1. Download ZIP  
2. Unzip  
3. Double-click **`START-HERE.html`** (or read `INSTALL.txt`)  
4. Follow the 8 steps  

Takes about **2 minutes**. After that, LUMEN works like an app pinned in Chrome.

## Optional: free website link

Put the ZIP on GitHub Releases and share:

```
https://github.com/YOUR_USER/lumen-browser/releases/latest
```

Users download → unzip → `START-HERE.html`.

## What you cannot do (Google rules)

- Email a `.crx` file and have users drag it in — Chrome blocks this for security  
- Avoid Developer mode on consumer Chromebooks without the Web Store  

So: **ZIP + Load unpacked** is the correct free path.

## Chrome Web Store (optional later)

- Costs **$5 once** for a *developer* account (not per user)  
- Users still install free  
- Only needed if you want **one-click install without Developer mode**  

You can stay 100% off the store forever.
