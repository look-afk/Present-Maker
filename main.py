import asyncio
import json
import logging
import os
import re
import secrets
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

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
STATE_FILE = Path("bot_state.json")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
dp = Dispatcher()
user_languages: dict[int, str] = {}
user_settings: dict[int, dict] = {}
busy_users: set[int] = set()
recipient_links: dict[str, dict] = {}
recipients: dict[int, dict] = {}
auto_send_recipient: dict[int, bool] = {}


def load_state():
    if not STATE_FILE.exists():
        return
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        recipient_links.update({str(k): v for k, v in data.get("recipient_links", {}).items()})
        recipients.update({int(k): v for k, v in data.get("recipients", {}).items()})
        auto_send_recipient.update({int(k): bool(v) for k, v in data.get("auto_send_recipient", {}).items()})
    except (OSError, ValueError, TypeError) as exc:
        log.warning("Could not load bot state: %s", exc)


def save_state():
    try:
        STATE_FILE.write_text(json.dumps({
            "recipient_links": recipient_links,
            "recipients": {str(k): v for k, v in recipients.items()},
            "auto_send_recipient": {str(k): v for k, v in auto_send_recipient.items()},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        log.exception("Could not save bot state")


load_state()
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
    recipient = recipients.get(user_id)
    recipient_label = recipient.get("name", "Получатель") if recipient else "не привязан"
    auto_label = "вкл." if auto_send_recipient.get(user_id, False) else "выкл."
    kb.button(text=f"Отправка: {recipient_label} ({auto_label})", callback_data="setting:recipient")
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


@dp.callback_query(F.data == "setting:recipient")
async def recipient_setting(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    recipient = recipients.get(user_id)
    recipient_text = f"Текущий получатель: {recipient.get('name', 'Получатель')}." if recipient else "Получатель пока не привязан."
    kb = InlineKeyboardBuilder()
    kb.button(text="Как привязать получателя", callback_data="recipient:help")
    if recipient:
        label = "Отключить автоотправку" if auto_send_recipient.get(user_id, False) else "Включить автоотправку"
        kb.button(text=label, callback_data="recipient:toggle")
    kb.button(text="Назад к настройкам", callback_data="setting:home")
    kb.adjust(1)
    await callback.message.edit_text(
        "Автоматическая отправка готовых презентаций\n\n" + recipient_text +
        "\n\nДля привязки отправь команду /addrecipient Мама. Перешли созданную ссылку маме; ей нужно открыть её и нажать Start. После привязки включи автоотправку здесь.",
        reply_markup=kb.as_markup(),
    )


@dp.callback_query(F.data == "recipient:help")
async def recipient_help(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Отправь команду: /addrecipient Мама. Я создам ссылку; перешли её маме, чтобы она открыла бота и нажала Start.")


@dp.callback_query(F.data == "recipient:toggle")
async def recipient_toggle(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in recipients:
        await callback.answer("Сначала привяжи получателя через /addrecipient Мама", show_alert=True)
        return
    auto_send_recipient[user_id] = not auto_send_recipient.get(user_id, False)
    save_state()
    await callback.answer("Настройка сохранена")
    recipient = recipients[user_id]
    kb = InlineKeyboardBuilder()
    kb.button(text="Как привязать получателя", callback_data="recipient:help")
    kb.button(text="Отключить автоотправку" if auto_send_recipient[user_id] else "Включить автоотправку", callback_data="recipient:toggle")
    kb.button(text="Назад к настройкам", callback_data="setting:home")
    kb.adjust(1)
    await callback.message.edit_text(
        f"Получатель: {recipient.get('name', 'Получатель')}\nАвтоотправка: {'включена' if auto_send_recipient[user_id] else 'выключена'}.",
        reply_markup=kb.as_markup(),
    )


@dp.message(Command("addrecipient"))
async def add_recipient(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    name = parts[1].strip()[:40] if len(parts) > 1 else "Получатель"
    token = secrets.token_urlsafe(9)
    recipient_links[token] = {"owner_id": message.from_user.id, "name": name}
    save_state()
    bot_username = (await message.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=link_{token}"
    await message.answer(f"Ссылка для привязки «{name}» создана. Перешли её получателю; ему нужно открыть её и нажать Start.\n\n{link}")


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
    payload = (message.text or "").partition(" ")[2].strip()
    if payload.startswith("link_"):
        token = payload[len("link_"):]
        link_data = recipient_links.pop(token, None)
        if not link_data:
            await message.answer("Ссылка недействительна или уже использована. Попроси владельца создать новую через /addrecipient.")
            return
        owner_id = int(link_data["owner_id"])
        recipients[owner_id] = {"chat_id": message.chat.id, "name": link_data.get("name", "Получатель")}
        auto_send_recipient.setdefault(owner_id, False)
        save_state()
        await message.answer("Готово. Ты привязан как получатель презентаций.")
        try:
            await message.bot.send_message(owner_id, f"Получатель «{link_data.get('name', 'Получатель')}» привязан. Включи автоотправку в /settings.")
        except Exception:
            log.exception("Could not notify owner about linked recipient")
        return
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


def parse_topics(raw_text: str) -> list[str]:
    topics = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip().rstrip("\\").strip()
        if not line:
            continue
        line = line.replace("**", "").replace("__", "")
        if " — " in line:
            line = line.split(" — ", 1)[0].strip()
        line = re.sub(r"^\s*(?:[-*•]\s*)?(?:\d+[.)]\s*)?", "", line).strip()
        line = re.sub(r"\s*\((?:\d+\s*)?(?:soat|час(?:а|ов)?|hours?|hrs?)\)\s*$", "", line, flags=re.I).strip()
        line = line.strip(" .;\\")
        if len(line) >= 3 and not line.startswith("/"):
            topics.append(line)
    unique, seen = [], set()
    for topic in topics:
        if topic.casefold() not in seen:
            seen.add(topic.casefold())
            unique.append(topic)
    return unique


async def generate_one(message: Message, topic: str, lang: str, index: int, total: int):
    status = await message.answer(f"[{index}/{total}] Ищу источники: «{topic}»…")
    try:
        diagnostics = []
        sources = await asyncio.to_thread(collect_sources, topic, diagnostics)
        readable = [s for s in sources if s.get("source_type") != "image" and len((s.get("text") or "").strip()) >= 250]
        if not readable:
            details = "\n".join(diagnostics[-8:])[:1000] or "Источники не вернули текст."
            raise RuntimeError("Не удалось найти содержательные текстовые материалы.\n" + details)
        await status.edit_text(f"[{index}/{total}] Найдено текстовых материалов: {len(readable)}. Создаю презентацию…")
        settings = dict(get_settings(message.from_user.id))
        content = await asyncio.to_thread(generate_presentation_content, topic, lang, sources, settings)
        slug = re.sub(r"[^\w-]+", "_", topic, flags=re.UNICODE).strip("_")[:42] or f"topic_{index}"
        outdir = OUTPUT_DIR / str(message.from_user.id)
        outdir.mkdir(parents=True, exist_ok=True)
        pptx_path = outdir / f"{slug}_{index}.pptx"
        await asyncio.to_thread(create_pptx, topic, lang, content, sources, pptx_path, settings)
        caption = f"Готово: {content.get('title', topic)}\nЯзык: {LANG_LABELS[lang]}\nТекстовых материалов: {len(readable)}\nСлайдов: {len(content.get('slides', []))}"
        await message.answer_document(FSInputFile(pptx_path), caption=caption)
        recipient = recipients.get(message.from_user.id)
        if recipient and auto_send_recipient.get(message.from_user.id, False):
            try:
                await message.bot.send_document(chat_id=recipient["chat_id"], document=FSInputFile(pptx_path), caption=f"Презентация: {content.get('title', topic)}")
            except Exception:
                log.exception("Could not send presentation to linked recipient")
                await message.answer("Файл готов, но отправить его получателю автоматически не удалось.")
        await status.edit_text(f"[{index}/{total}] Готово.")
        return True, None
    except Exception as exc:
        log.exception("Presentation generation failed for topic %r", topic)
        reason = str(exc).replace("<", "‹").replace(">", "›")[:600]
        await status.edit_text(f"[{index}/{total}] Не удалось создать «{topic}».\n\nПричина: {reason}")
        return False, topic


@dp.message(F.text)
async def topic_received(message: Message):
    user_id = message.from_user.id
    raw_text = (message.text or "").strip()
    if raw_text.startswith("/"):
        return
    if user_id in busy_users:
        await message.answer("Предыдущая задача ещё выполняется. Дождись её завершения.")
        return
    if user_id not in user_languages:
        await message.answer("Сначала выбери язык:", reply_markup=language_keyboard())
        return
    topics = parse_topics(raw_text)
    if not topics:
        await message.answer("Не удалось распознать темы. Отправь одну тему или список, по одной теме на строку.")
        return
    if len(topics) > 10:
        await message.answer(f"В одном сообщении можно отправить не больше 10 тем. Распознано: {len(topics)}. Раздели список на несколько сообщений.")
        return
    if any(len(topic) > 250 for topic in topics):
        await message.answer("Одна из тем длиннее 250 символов. Сократи её и отправь список повторно.")
        return
    busy_users.add(user_id)
    try:
        await message.answer(f"Принято тем: {len(topics)}. Создаю отдельные презентации по очереди.")
        failed, lang = [], user_languages[user_id]
        for index, topic in enumerate(topics, start=1):
            success, failed_topic = await generate_one(message, topic, lang, index, len(topics))
            if not success and failed_topic:
                failed.append(failed_topic)
        if failed:
            await message.answer(f"Обработка завершена. Успешно: {len(topics) - len(failed)} из {len(topics)}.\nНе удалось создать:\n" + "\n".join(f"• {topic}" for topic in failed))
        else:
            await message.answer(f"Готово: все {len(topics)} презентаций созданы.")
    finally:
        busy_users.discard(user_id)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        body = b"Present-Maker is running"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN в Environment Variables")

    port = int(os.getenv("PORT", "10000"))
    http_server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    Thread(target=http_server.serve_forever, daemon=True).start()
    log.info("Health server listening on 0.0.0.0:%s", port)

    bot = Bot(BOT_TOKEN)
    log.info("Presentation bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
