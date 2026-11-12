import asyncio
import html
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    LinkPreviewOptions,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

from workua_parser import WorkUaError, normalize_query, search_workua_jobs

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log", encoding="utf-8")],
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logger.error("BOT_TOKEN не знайдено! Створіть файл .env (див. .env.example).")
    raise SystemExit("BOT_TOKEN is not set")

router = Router()
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def get_search_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Python"), KeyboardButton(text="Продавець")],
            [KeyboardButton(text="Менеджер"), KeyboardButton(text="Дизайнер")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def format_jobs(query: str, jobs: list) -> str:
    header = f"🔎 Результати за запитом «{html.escape(query)}»:"
    items = []
    for i, job in enumerate(jobs, start=1):
        item = f'{i}. <a href="{html.escape(job.url, quote=True)}">{html.escape(job.title)}</a>'
        if job.salary:
            item += f"\n💰 {html.escape(job.salary)}"
        items.append(item)
    return header + "\n\n" + "\n\n".join(items)


@router.message(Command("start"))
async def send_welcome(message: Message):
    logger.info("/start від користувача %s", message.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Пошук вакансій", callback_data="search_jobs")
    builder.button(text="ℹ️ Про бота", callback_data="about")
    builder.adjust(1)
    await message.answer("👋 Оберіть опцію:", reply_markup=builder.as_markup())


@router.message(Command("status"))
async def status(message: Message):
    await message.answer("🤖 Бот активний і готовий до роботи!")


@router.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "Просто напишіть назву професії або технології (наприклад: <b>python</b>), "
        "і я надішлю вакансії з Work.ua.\n\nКоманди: /start, /status, /help"
    )


@router.callback_query(F.data == "search_jobs")
async def search_prompt(callback: CallbackQuery):
    if callback.message:
        await callback.message.answer(
            "Введіть назву професії або оберіть із запропонованих:",
            reply_markup=get_search_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "about")
async def about(callback: CallbackQuery):
    if callback.message:
        await callback.message.answer(
            "🤖 <b>SmartJobAlertsBot</b> — бот, який допомагає швидко знаходити вакансії.\n\n"
            "🔎 Введіть бажану професію або технологію, і бот надішле посилання "
            "на актуальні вакансії з Work.ua."
        )
    await callback.answer()


@router.message(F.text, ~F.text.startswith("/"))
async def handle_query(message: Message):
    query = normalize_query(message.text)
    if not query:
        await message.answer("Введіть, будь ласка, назву професії.")
        return

    logger.info("Пошук '%s' від користувача %s", query, message.from_user.id)
    wait_msg = await message.answer("🔎 Шукаю вакансії...")

    try:
        # parser uses blocking `requests`, so run it in a worker thread
        jobs = await asyncio.to_thread(search_workua_jobs, query)
    except WorkUaError as e:
        logger.error("Work.ua error: %s", e)
        text = "⚠️ Не вдалося отримати дані з Work.ua. Спробуйте пізніше."
        jobs = None
    except Exception:
        logger.exception("Неочікувана помилка під час пошуку")
        text = "⚠️ Виникла помилка під час пошуку. Спробуйте ще раз."
        jobs = None
    else:
        text = (
            format_jobs(query, jobs)
            if jobs
            else "😔 Вакансій не знайдено. Спробуйте інше ключове слово."
        )

    try:
        await wait_msg.delete()
    except Exception:
        pass
    await message.answer(
        text, reply_markup=get_search_keyboard(), link_preview_options=NO_PREVIEW
    )


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message):
    await message.answer("Невідома команда. Спробуйте /start або /help.")


@router.message()
async def non_text(message: Message):
    await message.answer("Надішліть, будь ласка, текстовий запит, наприклад: python")


async def main():
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    logger.info("Запуск бота...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
