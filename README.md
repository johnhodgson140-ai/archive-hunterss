# Archive Hunter

Archive Hunter is a Telegram bot for hunting archive fashion deals across resale marketplaces, auction platforms, and replica communities. It includes memory/training support for archive designers like Hedi Slimane, Dior Homme, YSL, and rare auction pieces.

## Features

- Search archive pieces and auctions via `/scan`, `/search`, `/auction`
- View source coverage with `/sources`
- Persistent memory training with `/remember`, `/memory`, `/forget`, `/train`
- 24/7 hunt alerts via `/hunt`
- Market intel via `/deals`, `/intel`, `/price`
- Local DB fallback for profiles, hunts, and watched links when Supabase is not configured
- Support for Xianyu, Mercari JP, Yahoo Auctions, Grailed, Weidian, Taobao, and more

## Setup

1. Clone this repo:

```bash
git clone https://github.com/<your-username>/archive-hunter.git
cd archive-hunter
```

2. Create a Python virtual environment:

```bash
python -m venv .venv
.\.venv\Scripts\activate.bat
```

3. Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4. Copy and fill in `.env` with your keys, or use the included `.env.example`:

```text
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
SUPABASE_URL=https://your-supabase-url
SUPABASE_KEY=your-supabase-key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

If you do not use Supabase, leave `SUPABASE_URL` and `SUPABASE_KEY` empty. The bot will still work locally and store profiles, hunts, and watched links in `db_store.json`.

5. Run the bot:

```bash
python bot.py
```

Or simply double-click `run_bot.bat` on Windows.

## GitHub Usage

- Add this repo to GitHub and use it as your archive hunting app.
- Share the repo with collaborators.
- Use the GitHub Actions workflow to validate the bot on each push or PR.

## Docker

Build and run:

```bash
docker build -t archive-hunter .
docker run --env-file .env archive-hunter
```

## GitHub Pages website

This repository now includes a static website in the `docs/` folder. After you push to `main`, GitHub Actions will deploy it automatically to GitHub Pages.

To enable the website:

1. Open your repository Settings in GitHub.
2. Select **Pages**.
3. Choose the `main` branch and `/docs` folder.
4. Save.

The site will publish at `https://<your-username>.github.io/<repo-name>/`.

## Notes

- Do not commit `.env` or keys to GitHub.
- `memory_store.json` persists your archive memory data locally.

## License

MIT License
