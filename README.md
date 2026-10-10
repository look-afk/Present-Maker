# Presentation Bot v0.4 — customizable research presentations

A Telegram bot that searches public sources, extracts readable article text and available OpenAlex abstracts/open-access PDFs, asks an AI model to synthesize a detailed explanatory study note, and exports editable PowerPoint slides.

## What's included
- Explanatory study-note slides with connected paragraphs, examples, takeaways, and source IDs—not just short bullet lists.
- Five visual themes: dark, academic, minimalist, colorful, and classic light.
- Custom settings for detail level, presentation structure, visual balance, and 6/8/10/12 content slides.
- Wikipedia, OpenAlex, open-access PDF, and Wikimedia Commons source collection.
- Source reading-status labels to distinguish full pages, abstracts, snippets, and metadata.

## Run locally
1. Install Python 3.12 or newer.
2. Install dependencies: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` and `OPENROUTER_API_KEY`.
4. Run `python main.py`.
5. In Telegram, send `/start`, choose the language, use `/settings` to customize the deck, and send a topic.

## Render
Create a Background Worker and connect this repository. The repository's `Procfile` starts `python main.py`. Set these environment variables in Render:
- `TELEGRAM_BOT_TOKEN`
- `OPENROUTER_API_KEY`
- Optional: `OPENROUTER_MODEL` (defaults to `openrouter/free`)

The worker must remain running to receive Telegram updates. Do not commit your real `.env` file or API keys.

## Limits
This is not exhaustive web research. Search coverage depends on the topic and public APIs. Scanned PDFs are not OCR-processed, paywalled papers may expose only metadata or an abstract, and model output should be reviewed before use.
