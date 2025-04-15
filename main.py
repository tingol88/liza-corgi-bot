import os
import asyncio
import logging
import nest_asyncio

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)
from db_utils import create_db
from handlers import (
    start,
    help_command,
    learn,
    reference,
    clear_conversation,
    google_doc,
    google_sheet,
    sync_folder,
    debug_knowledge
)
from services import (
    handle_text,
    handle_voice,
    handle_document,
    sync_every_hour,
    list_knowledge
)

# Настройка логгера
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

app = ApplicationBuilder().token(BOT_TOKEN).build()

# Регистрация хендлеров
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("learn", learn))
app.add_handler(CommandHandler("ref", reference))
app.add_handler(CommandHandler("clear", clear_conversation))
app.add_handler(CommandHandler("doc", google_doc))
app.add_handler(CommandHandler("sheet", google_sheet))
app.add_handler(CommandHandler("sync", sync_folder))
app.add_handler(CommandHandler("debug_knowledge", debug_knowledge))
app.add_handler(CommandHandler("list_knowledge", list_knowledge))

app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

create_db()

async def main():
    if GOOGLE_DRIVE_FOLDER_ID:
        app.create_task(sync_every_hour())
    else:
        logger.warning("GOOGLE_DRIVE_FOLDER_ID не задан — авто-синхронизация не будет запущена")
    await app.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
