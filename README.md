# Present-Maker

A Telegram bot that researches a topic and produces editable PowerPoint decks. The renderer uses multiple slide compositions instead of a single repeated layout.

## Features
- Telegram workflow with language selection and presentation preferences.
- Research collection from Wikipedia, OpenAlex and Wikimedia Commons.
- OpenRouter-powered content generation.
- Editable PowerPoint export using python-pptx.
- Five themes: dark, academic (warm paper), minimal, colorful and classic.
- Layouts: split text/image, cards, image-led, comparison, timeline, quote, metrics and conclusion.
- Speaker notes and source-list slide.
- Offline smoke test.

## Run locally
1. Install Python 3.12+ and uv.
2. Run setup.bat.
3. Open .env and add TELEGRAM_BOT_TOKEN and OPENROUTER_API_KEY.
4. Run run.bat.

Alternatively, install dependencies with pip install -r requirements.txt and run python main.py.

## Deployment
On Render, create a Background Worker, connect this repository, and set TELEGRAM_BOT_TOKEN and OPENROUTER_API_KEY. Optional OPENROUTER_MODEL defaults to openrouter/free. Procfile runs the bot.

## Test
Run: uv run python tests/smoke_test.py

Research is not exhaustive. Review slides and sources before presenting.
