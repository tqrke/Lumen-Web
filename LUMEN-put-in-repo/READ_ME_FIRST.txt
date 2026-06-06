================================================================================
  FOLDER: C:\LUMEN-put-in-repo
  >>> UPLOAD THIS ENTIRE FOLDER TO GITHUB (the code repository) <<<
================================================================================

This folder has ~98 files — your SOURCE CODE and WEBSITE only.
This is what belongs in your GitHub repo. NOT the big ZIPs.

WHAT IS IN HERE
---------------
  website\          Your landing page (index.html)
  chromebook\       Chromebook extension source
  app.py, core\, ui\, assets\, etc.   Windows browser source code
  README.md, requirements.txt, LICENSE
  .gitignore        Tells Git to ignore build junk

WHAT TO DO
----------
  1. Create a new repo on GitHub (e.g. lumen-browser)

  2. Open PowerShell and run:

     cd C:\LUMEN-put-in-repo
     git init
     git add .
     git commit -m "LUMEN Browser 5.0 source and website"
     git branch -M main
     git remote add origin https://github.com/YOUR_USERNAME/lumen-browser.git
     git push -u origin main

     (Replace YOUR_USERNAME with your GitHub username)

  3. Host the website on Vercel (not GitHub Pages):
     - Go to vercel.com -> Add New Project -> Import your GitHub repo
     - Root Directory: website
     - Deploy

  4. Edit website\index.html line ~745:
     Change YOUR_GITHUB_USERNAME to your real GitHub username.
     Download buttons then pull ZIPs from GitHub Releases automatically.

  5. Attach the 2 ZIPs to a GitHub Release (see other folder).
     Vercel hosts the site. GitHub hosts the downloads.

DO NOT copy anything from C:\LUMEN-do-not-put-in-repo into this folder.

================================================================================
