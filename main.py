import os
import logging
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
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
    handle_text,
    handle_voice,
    handle_document,
    sync_every_hour
)

# Настройка логгера
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("liza_corgi.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Токены и переменные окружения
BOT_TOKEN = os.environ["BOT_TOKEN"]
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

# Запуск бота
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Регистрация команд
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("learn", learn))
app.add_handler(CommandHandler("ref", reference))
app.add_handler(CommandHandler("clear", clear_conversation))
app.add_handler(CommandHandler("doc", google_doc))
app.add_handler(CommandHandler("sheet", google_sheet))
app.add_handler(CommandHandler("sync", sync_folder))

# Регистрация сообщений
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

# Создание базы данных
create_db()

# Основной цикл
async def main():
    if GOOGLE_DRIVE_FOLDER_ID:
        app.create_task(sync_every_hour())
    else:
        logger.warning("GOOGLE_DRIVE_FOLDER_ID не задан — авто-синхронизация не будет запущена")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
