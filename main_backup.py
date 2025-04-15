
import os
import openai
import logging
import requests
import fitz  # PyMuPDF
import docx  # python-docx
import json
import asyncio
import nest_asyncio
from telegram import Update, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from pydub import AudioSegment
from google_connect import get_google_docs_text, get_google_sheet_values, sync_drive_folder_to_knowledge
from db_utils import (
    create_db,
    save_conversation,
    get_conversation,
    save_knowledge,
    get_relevant_knowledge,
    find_knowledge_by_keyword
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

# Идентификаторы администраторов
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))
admin_ids = [126204360, ADMIN_CHAT_ID]

openai.api_key = os.environ["OPENAI_API_KEY"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

SYSTEM_PROMPT = {
    "role": "system",
    "content": "Ты — Лиза, виртуальный помощник клининговой компании Cleaning-Moscow. Ты гордишся нашей компанией. Ты хорошо разбираешься в клининге, но можешь помочь и с другими вопросами — по жизни, бизнесу, технологиям и многому другому. Ты умная, доброжелательная и любознательная."
}

async def google_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("Извините, только администратор может загружать документы.")
        return
    if not context.args:
        await update.message.reply_text("Укажи ID Google Документа. Пример: /doc 1A2B3C4D5E6F...")
        return
    try:
        doc_id = context.args[0]
        content = get_google_docs_text(doc_id)
        save_conversation(update.effective_user.id, content)
        await update.message.reply_text("📄 Документ прочитан и добавлен в базу знаний.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при загрузке документа: {e}")

async def google_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("Извините, только администратор может загружать таблицы.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Формат: /sheet <SPREADSHEET_ID> <RANGE>. Пример: /sheet 1A2B3C Range1!A1:E10")
        return
    try:
        sheet_id = context.args[0]
        sheet_range = " ".join(context.args[1:])
        rows = get_google_sheet_values(sheet_id, sheet_range)
        content = "\n".join([", ".join(row) for row in rows])
        save_conversation(update.effective_user.id, content)
        await update.message.reply_text("📊 Таблица обработана и сохранена!")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при загрузке таблицы: {e}")

async def sync_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admin_ids:
        await update.message.reply_text("⛔ Только администратор может запускать синхронизацию.")
        return
    if not context.args:
        await update.message.reply_text("Укажи ID папки Google Диска. Пример: /sync 1AbcDEF456...")
        return
    folder_id = context.args[0]
    try:
        sync_drive_folder_to_knowledge(folder_id)
        await update.message.reply_text("📁 Папка синхронизирована! Все файлы добавлены в базу знаний.")
    except Exception as e:
        logger.exception("Ошибка при синхронизации папки")
        await update.message.reply_text(f"Ошибка при синхронизации: {e}")

async def sync_every_hour():
    while True:
        try:
            logger.info("⏳ Автоматическая синхронизация папки Google Диска")
            sync_drive_folder_to_knowledge(GOOGLE_DRIVE_FOLDER_ID)
        except Exception as e:
            logger.error(f"Ошибка при авто-синхронизации: {e}")
        await asyncio.sleep(3600)  # 1 час

async def learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admin_ids:
        await update.message.reply_text("Извините, только администратор может обучать Лизу.")
        return
    text = update.message.text.removeprefix("/learn").strip()
    if not text:
        await update.message.reply_text("Пожалуйста, укажи, чему ты хочешь меня научить. Пример:\n/learn как мы убираем рестораны после открытия")
        return
    lines = text.split("\n", 1)
    title = lines[0][:100]
    content = lines[1] if len(lines) > 1 else lines[0]
    save_knowledge(title, content, user_id)
    await update.message.reply_text(f"Спасибо, Александр! Я запомнила информацию под названием: \"{title}\"")

async def reference(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Укажи ключевое слово для поиска. Пример: /ref офис")
        return
    keyword = ' '.join(context.args)
    result = find_knowledge_by_keyword(keyword)
    if result:
        await update.message.reply_text(f"🔎 Нашла в базе знаний:\n\n*{result[0]}*\n\n{result[1][:3000]}", parse_mode="Markdown")
    else:
        await update.message.reply_text("К сожалению, ничего не нашла по твоему запросу. Попробуй другое слово или обучи меня через /learn")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🐾 *Команды Лизы*:\n\n"
        "/start — Приветствие и вводная\n"
        "/learn — Обучить Лизу новому знанию (только админ)\n"
        "/ref [запрос] — Найти в базе знаний\n"
        "/clear — Очистить историю общения (только админ)\n"
        "/help — Показать это меню\n\n"
        "Можешь просто писать или отправлять голосовые/документы — Лиза всё поймёт!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")
    
async def process_user_input(user_id, user_input, context, send_reply):
    logger.info(f"User {user_id} wrote: {user_input}")
    context_history = get_conversation(user_id)
    context_history += f"\n{user_input}"
    save_conversation(user_id, context_history)
    knowledge_matches = get_relevant_knowledge(user_input)
    knowledge_text = "\n\n".join(knowledge_matches)
    try:
        messages = [SYSTEM_PROMPT, {"role": "user", "content": f"{knowledge_text}\n\nВопрос: {user_input}"}]
        completion = openai.chat.completions.create(model="gpt-4o", messages=messages)
        answer = completion.choices[0].message.content
        await send_reply(answer)
    except Exception as e:
        logger.exception("Error in user input processing")
        if ADMIN_CHAT_ID:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Text error: {str(e)}")
        await send_reply("Произошла ошибка при обработке запроса.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text.strip()
    await process_user_input(user_id, user_input, context, update.message.reply_text)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        file_path = "voice.ogg"
        mp3_path = "voice.mp3"
        await file.download_to_drive(file_path)
        AudioSegment.from_file(file_path).export(mp3_path, format="mp3")
        with open(mp3_path, "rb") as audio_file:
            transcript = openai.audio.transcriptions.create(model="whisper-1", file=audio_file)
        text = transcript.text.strip()
        logger.info(f"Transcribed: {text}")

        user_id = update.effective_user.id
        await process_user_input(user_id, text, context, update.message.reply_text)

    except Exception as e:
        logger.exception("Error in voice processing")
        await update.message.reply_text("Произошла ошибка при обработке голосового сообщения.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        document = update.message.document
        file_path = f"./{document.file_name}"
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(file_path)
        content = ""
        if file_path.endswith(".txt"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        elif file_path.endswith(".pdf"):
            with fitz.open(file_path) as pdf:
                for page in pdf:
                    content += page.get_text()
        elif file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            content = "\n".join([para.text for para in doc.paragraphs])
        else:
            await update.message.reply_text("Пожалуйста, отправьте .txt, .pdf или .docx файл.")
            return
        if update.effective_user.id in admin_ids:
            save_conversation(update.effective_user.id, content)
        logger.info(f"Received document from {update.effective_user.id}: {document.file_name}")
        await update.message.reply_text("Файл принят и обработан. Я запомнила информацию!")
    except Exception as e:
        logger.exception("Error in document processing")
        await update.message.reply_text("Не удалось обработать документ. Поддерживаются .txt, .pdf и .docx файлы.")

async def clear_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admin_ids:
        await update.message.reply_text("Извините, только администратор может очистить контекст.")
        return
    try:
        conn = sqlite3.connect("liza_db.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text("Контекст общения был очищен.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при очистке контекста: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Гав-гав! 🐾 Я Лиза Корги — виртуальный помощник клининговой компании Cleaning-Moscow. Можешь задать вопрос или отправить голосовое сообщение!")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("learn", learn))
app.add_handler(CommandHandler("ref", reference))
app.add_handler(CommandHandler("clear", clear_conversation))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
app.add_handler(CommandHandler("doc", google_doc))
app.add_handler(CommandHandler("sheet", google_sheet))
app.add_handler(CommandHandler("sync", sync_folder))

create_db()

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
