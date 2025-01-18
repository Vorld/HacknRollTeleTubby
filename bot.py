import logging
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_API_TOKEN")

async def help(update, context):
    chat_id = update.message.chat_id

    await context.bot.send_message(chat_id, "Help!")


async def tags(update, context):
    chat_id = update.message.chat_id
    await context.bot.send_message(chat_id, "tags!")

async def briefing(update, context):
    chat_id = update.message.chat_id
    await context.bot.send_message(chat_id, "briefing!")


if __name__ == "__main__":
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("tags", tags))
    application.add_handler(CommandHandler("briefing", briefing))
    application.run_polling(allowed_updates=Update.ALL_TYPES)