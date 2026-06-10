# archive-hunterss GitHub Package

This folder contains the files needed to add GitHub Pages and repository setup to your `archive-hunterss` repo.

## Files to copy into your repo root

- `commit_to_github.bat`
- `.env.example`
- `.nojekyll`
- `.github/workflows/pages.yml`
- `docs/index.html`
- `docs/styles.css`

## What to do

1. Copy the files into your repo root.
2. Keep your existing `bot.py`, `requirements.txt`, `README.md`, and `.gitignore`.
3. Add and commit on the `main` branch.

## GitHub Pages setup

This package deploys the site from `docs/` using GitHub Actions.

After pushing to `main`:

- Go to your repo on GitHub.
- Open `Settings` → `Pages`.
- Verify the source is set to the branch `main` and folder `/docs`.
- Save if needed.

Your site will appear at:

`https://<your-username>.github.io/archive-hunterss/`
