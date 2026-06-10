# GitHub Setup Bundle

This folder contains the files needed to set up the Archive Hunter repo on GitHub.

## Included files

- `commit_to_github.bat` — initializes git, commits all files, and optionally adds a remote.
- `.env.example` — sample environment file for your bot keys.
- `.nojekyll` — enables GitHub Pages hosting for the `docs/` folder.
- `docs/index.html` — static GitHub Pages homepage.
- `docs/styles.css` — styling for the homepage.
- `pages.yml` — GitHub Actions workflow to deploy the Pages site.

## What to do

1. Move these files into your repository root:
   - `commit_to_github.bat`
   - `.env.example`
   - `.nojekyll`
   - `.github/workflows/pages.yml`
   - `docs/index.html`
   - `docs/styles.css`

2. Update the homepage content if needed.
3. Commit and push to GitHub.

## Notes

- If you already have `.gitignore`, keep it in the root.
- The Pages workflow requires a `main` branch and `docs/` folder.
