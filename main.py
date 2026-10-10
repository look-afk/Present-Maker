import asyncio
import logging
import os
import re
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

from research.search import collect_sources
from ai.client import generate_presentation_content
from presentation.export import create_pptx

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
dp = Dispatcher()
user_languages: dict[int, str] = {}
user_settings: dict[int, dict] = {}
busy_users: set[int] = set()
LANG_LABELS = {"ru": "русский", "en": "английский", "uz": "узбекский"}


STYLES = {"dark": "Тёмный современный", "academic": "Академический", "minimal": "Минималистичный", "colorful": "Яркий цветной", "classic": "Классический светлый"}
DETAILS = {"concise": "Кратко", "balanced": "Подробно", "deep": "Максимально подробно"}
VISUALS = {"mixed": "Текст + изображения", "text": "Преимущественно текст", "visual": "Больше визуала"}
STRUCTURES = {"lesson": "Учебный конспект", "story": "Связный рассказ", "research": "Исследование с аргументами", "timeline": "Хронология событий", "compare": "Сравнение вариантов"}


def get_settings(user_id):
    return user_settings.setdefault(user_id, {"style": "dark", "detail": "balanced", "visuals": "mixed", "structure": "lesson", "slides": 8})


def settings_keyboard(user_id):
    s = get_settings(user_id)
    kb = InlineKeyboardBuilder()
    kb.button(text=f"Оформление: {STYLES[s['style']]}", callback_data="setting:styles")
    kb.button(text=f"Подробность: {DETAILS[s['detail']]}", callback_data="setting:details")
    kb.button(text=f"Подача: {STRUCTURES[s['structure']]}", callback_data="setting:structures")
    kb.button(text=f"Визуал: {VISUALS[s['visuals']]}", callback_data="setting:visuals")
    kb.button(text=f"Слайдов: {s['slides']}", callback_data="setting:slides")
    kb.adjust(1)
    return kb.as_markup()


def option_keyboard(key, options, current):
    kb = InlineKeyboardBuilder()
    for value, label in options.items():
        kb.button(text=label + (" ✓" if str(current) == str(value) else ""), callback_data=f"choose:{key}:{value}")
    kb.button(text="Назад к настройкам", callback_data="setting:home")
    kb.adjust(1)
    return kb.as_markup()


def language_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Русский", callback_data="lang:ru")
    kb.button(text="English", callback_data="lang:en")
    kb.button(text="O‘zbekcha", callback_data="lang:uz")
    kb.adjust(1)
    return kb.as_markup()


@dp.message(Command("settings"))
async def settings_command(message: Message):
    s = get_settings(message.from_user.id)
    await message.answer(
        f"Настройки презентации\nОформление: {STYLES[s['style']]}\nПодробность: {DETAILS[s['detail']]}\n"
        f"Подача: {STRUCTURES[s['structure']]}\nВизуал: {VISUALS[s['visuals']]}\nСодержательных слайдов: {s['slides']}\n\nВыбери параметр:",
        reply_markup=settings_keyboard(message.from_user.id))


@dp.callback_query(F.data == "setting:home")
async def settings_home(callback: CallbackQuery):
    await callback.answer()
    s = get_settings(callback.from_user.id)
    await callback.message.edit_text(
        f"Настройки презентации\nОформление: {STYLES[s['style']]}\nПодробность: {DETAILS[s['detail']]}\n"
        f"Подача: {STRUCTURES[s['structure']]}\nВизуал: {VISUALS[s['visuals']]}\nСлайдов: {s['slides']}",
        reply_markup=settings_keyboard(callback.from_user.id))


@dp.callback_query(F.data.startswith("setting:"))
async def open_setting(callback: CallbackQuery):
    group = callback.data.split(":", 1)[1]
    s = get_settings(callback.from_user.id)
    configs = {
        "styles": ("style", STYLES, "Выбери оформление:"),
        "details": ("detail", DETAILS, "Насколько подробной должна быть презентация?"),
        "structures": ("structure", STRUCTURES, "Выбери способ подачи материала:"),
        "visuals": ("visuals", VISUALS, "Выбери баланс текста и визуальных элементов:"),
        "slides": ("slides", {"6": "6 слайдов", "8": "8 слайдов", "10": "10 слайдов", "12": "12 слайдов"}, "Сколько содержательных слайдов нужно?"),
    }
    if group not in configs:
        await callback.answer("Неизвестная настройка", show_alert=True); return
    key, options, prompt = configs[group]
    await callback.answer()
    await callback.message.edit_text(prompt, reply_markup=option_keyboard(key, options, s[key]))


@dp.callback_query(F.data.startswith("choose:"))
async def choose_setting(callback: CallbackQuery):
    _, key, value = callback.data.split(":", 2)
    allowed = {"style": STYLES, "detail": DETAILS, "structure": STRUCTURES, "visuals": VISUALS,
               "slides": {"6": "", "8": "", "10": "", "12": ""}}
    if key not in allowed or value not in allowed[key]:
        await callback.answer("Неизвестная настройка", show_alert=True); return
    s = get_settings(callback.from_user.id)
    s[key] = int(value) if key == "slides" else value
    await callback.answer("Сохранено")
    await callback.message.edit_text("Настройка сохранена. Можешь изменить другой параметр:", reply_markup=settings_keyboard(callback.from_user.id))


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Я создаю презентации: ищу материалы, анализирую источники и собираю PowerPoint.\n\n"
        "1. Выбери язык.\n2. Настрой оформление через /settings.\n3. Отправь тему одним сообщением.\n\n"
        "Пример: Искусственный интеллект в образовании",
        reply_markup=language_keyboard(),
    )


@dp.message(Command("language"))
async def change_language(message: Message):
    await message.answer("Выбери язык презентации:", reply_markup=language_keyboard())


@dp.callback_query(F.data.startswith("lang:"))
async def choose_language(callback: CallbackQuery):
    lang = callback.data.split(":", 1)[1]
    if lang not in LANG_LABELS:
        await callback.answer("Неизвестный язык", show_alert=True)
        return
    user_languages[callback.from_user.id] = lang
    get_settings(callback.from_user.id)
    await callback.answer("Язык выбран")
    await callback.message.answer(f"Язык презентации: {LANG_LABELS[lang]}. Настройки доступны через /settings. Теперь отправь тему.")


@dp.message(F.text)
async def topic_received(message: Message):
    user_id = message.from_user.id
    topic = message.text.strip()
    if topic.startswith("/"):
        return
    if user_id in busy_users:
        await message.answer("Твоя предыдущая презентация ещё создаётся. Дождись её завершения.")
        return
    if user_id not in user_languages:
        await message.answer("Сначала выбери язык:", reply_markup=language_keyboard())
        return
    if len(topic) < 3:
        await message.answer("Напиши тему подробнее.")
        return
    if len(topic) > 250:
        await message.answer("Тема слишком длинная. Ограничь её 250 символами.")
        return

    busy_users.add(user_id)
    status = await message.answer("Этап 1/5: ищу источники и иллюстрации…")
    try:
        lang = user_languages[user_id]
        diagnostics = []
        sources = await asyncio.to_thread(collect_sources, topic, diagnostics)
        readable = [s for s in sources if s.get("source_type") != "image" and len((s.get("text") or "").strip()) >= 250]
        if not readable:
            details = "\n".join(diagnostics[-8:])[:1200] or "Источники не вернули текст."
            raise RuntimeError("Не удалось найти содержательные текстовые материалы.\n" + details)
        await status.edit_text(f"Этап 2/5: найдено текстовых материалов — {len(readable)}, изображений — {sum(s.get('source_type') == 'image' for s in sources)}. Анализирую содержание и пишу конспект…")
        settings = dict(get_settings(user_id))
        content = await asyncio.to_thread(generate_presentation_content, topic, lang, sources, settings)
        await status.edit_text("Этап 3/5: создаю оформление слайдов…")
        slug = re.sub(r"[^\w-]+", "_", topic, flags=re.UNICODE).strip("_")[:42] or "topic"
        outdir = OUTPUT_DIR / str(user_id)
        outdir.mkdir(parents=True, exist_ok=True)
        pptx_path = outdir / f"{slug}.pptx"
        await asyncio.to_thread(create_pptx, topic, lang, content, sources, pptx_path, settings)
        await status.edit_text("Этап 4/5: отправляю PowerPoint…")
        await message.answer_document(FSInputFile(pptx_path), caption=f"Готово: {content.get('title', topic)}\nЯзык: {LANG_LABELS[lang]}\nТекстовых материалов: {len(readable)}\nСлайдов с объяснениями: {len(content.get('slides', []))}")
        await status.edit_text("Этап 5/5: завершено. Отправь следующую тему или измени настройки через /settings.")
    except Exception as exc:
        log.exception("Presentation generation failed")
        reason = str(exc).replace("<", "‹").replace(">", "›")[:650]
        await status.edit_text("Не удалось создать презентацию.\n\nПричина: " + reason + "\n\nПроверь настройки .env и доступ к бесплатной модели.")
    finally:
        busy_users.discard(user_id)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN в .env")
    bot = Bot(BOT_TOKEN)
    log.info("Presentation bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
