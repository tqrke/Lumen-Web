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

  3. Turn on GitHub Pages:
     GitHub repo -> Settings -> Pages
     Source: main branch, folder: /website

     Your site will be at:
     https://YOUR_USERNAME.github.io/lumen-browser/

  4. Update website\index.html download links to point at GitHub Releases
     (see the other folder for the ZIP files)

DO NOT copy anything from C:\LUMEN-do-not-put-in-repo into this folder.

================================================================================
