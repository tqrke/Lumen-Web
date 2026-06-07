================================================================================
  C:\LUMEN-vercel-site  —  push THIS to your lumen-web GitHub repo
================================================================================

Your Vercel project: lumen-web
Live URL: https://lumen-web-ashy.vercel.app/

WHY YOU GOT 404
---------------
Vercel looks for index.html at the ROOT of the repo.
Your file was inside website/ — Vercel could not find it.

THIS FOLDER IS THE FIX
----------------------
  index.html   ← at the root (not in a subfolder)
  vercel.json

WHAT TO DO
----------
  1. Push ONLY these files to your lumen-web GitHub repo:

     cd C:\LUMEN-vercel-site
     git init
     git add index.html vercel.json
     git commit -m "Fix 404: index.html at repo root"
     git remote add origin https://github.com/josh-roberts/lumen-web.git
     git push -u origin main

     (Use your real lumen-web repo URL if different)

  2. Vercel will auto-redeploy, OR click Redeploy in the dashboard.

  3. Vercel project settings (lumen-web):
     - Framework Preset: Other
     - Root Directory: . (leave empty / repo root)
     - Build Command: (empty)
     - Output Directory: (empty)

  4. GitHub Releases (separate lumen-browser repo) must have:
     - LUMEN-Browser-5.0.0-win64.zip
     - LUMEN-Chromebook-1.0.0.zip

     Download buttons point to:
     github.com/josh-roberts/lumen-browser/releases/latest/download/...

If your GitHub username or repo name is different, edit index.html line ~746.

================================================================================
