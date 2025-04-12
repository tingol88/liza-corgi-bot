import os
import openai
import logging
from telegram import Update, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from pydub import AudioSegment
import requests
import fitz  # PyMuPDF
import docx  # python-docx
import sqlite3
import json

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
admin_ids = [126204360, ADMIN_CHAT_ID]  # Добавлены новые администраторы

openai.api_key = os.environ["OPENAI_API_KEY"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

SYSTEM_PROMPT = {
    "role": "system",
    "content": "Ты — Лиза, виртуальный помощник клининговой компании Cleaning-Moscow. Ты — умная, доброжелательная корги, которая помогает сотрудникам и клиентам. Говоришь дружелюбно, но по делу. Иногда можешь по-доброму и с юмором упомянуть своего хозяина Александра, подчеркивая его профессионализм, но делаешь это не слишком часто. Сайт: cleaning-moscow.ru."
}

# Функции для работы с контекстом и документами
def create_db():
    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()

    # Создаем таблицу для хранения контекста общения
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversations (
        user_id INTEGER PRIMARY KEY,
        context TEXT
    )
    ''')

    # Создаем таблицу для хранения документов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS documents (
        user_id INTEGER,
        document_name TEXT,
        document_content TEXT,
        PRIMARY KEY (user_id, document_name)
    )
    ''')

    conn.commit()
    conn.close()

# Функция для сохранения контекста общения
def save_conversation(user_id, message):
    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM conversations WHERE user_id = ?", (user_id,))
    existing_data = cursor.fetchone()

    if existing_data:
        cursor.execute("UPDATE conversations SET context = ? WHERE user_id = ?", (message, user_id))
    else:
        cursor.execute("INSERT INTO conversations (user_id, context) VALUES (?, ?)", (user_id, message))

    conn.commit()
    conn.close()

# Функция для получения контекста общения
def get_conversation(user_id):
    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()

    cursor.execute("SELECT context FROM conversations WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    conn.close()
    return result[0] if result else ""

# Функция для сохранения документов
def save_document(user_id, document_name, document_content):
    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()

    cursor.execute("INSERT OR REPLACE INTO documents (user_id, document_name, document_content) VALUES (?, ?, ?)",
                   (user_id, document_name, document_content))

    conn.commit()
    conn.close()

# Функция для получения документа
def get_document(user_id, document_name):
    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()

    cursor.execute("SELECT document_content FROM documents WHERE user_id = ? AND document_name = ?",
                   (user_id, document_name))
    result = cursor.fetchone()

    conn.close()
    return result[0] if result else None

# Функции обработки команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} sent /start")
    await update.message.reply_text("Гав-гав! 🐾 Я Лиза Корги — виртуальный помощник клининговой компании Cleaning-Moscow. Можешь задать вопрос или отправить голосовое сообщение!")

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = ' '.join(context.args)
    logger.info(f"User {update.effective_user.id} asked via /ask: {question}")
    if not question:
        await update.message.reply_text("Напиши вопрос после команды /ask, например: /ask сделай шаблон письма для клиента")
        return
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                SYSTEM_PROMPT,
                {"role": "user", "content": question}
            ]
        )
        answer = response.choices[0].message.content
        await update.message.reply_text(answer)
    except Exception as e:
        logger.exception("Error in /ask")
        if ADMIN_CHAT_ID:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"/ask error: {str(e)}")

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids:
        await update.message.reply_text("Извините, эта команда только для администратора.")
        return
    try:
        with open("liza_corgi.log", "r") as f:
            lines = f.readlines()[-20:]
        log_text = "".join(lines)
        await update.message.reply_text(f"Последние строки из логов:\n\n{log_text}")
    except Exception as e:
        await update.message.reply_text(f"Не удалось прочитать лог: {e}")

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

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private" and not update.message.text and f"@{context.bot.username}" not in (update.message.caption or ""):
        return
    logger.info(f"User {update.effective_user.id} sent voice message")
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        file_path = "voice.ogg"
        mp3_path = "voice.mp3"
        await file.download_to_drive(file_path)
        AudioSegment.from_file(file_path).export(mp3_path, format="mp3")
        with open(mp3_path, "rb") as audio_file:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        text = transcript.text
        logger.info(f"Transcribed: {text}")
        completion = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                SYSTEM_PROMPT,
                {"role": "user", "content": text}
            ]
        )
        answer = completion.choices[0].message.content
        await update.message.reply_text(f"Ты сказал(а): {text}\n\nМой ответ:\n{answer}")
    except Exception as e:
        logger.exception("Error in voice processing")
        if ADMIN_CHAT_ID:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Voice message error: {str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text
    logger.info(f"User {user_id} wrote: {user_input}")

    # Получаем контекст общения
    conversation = get_conversation(user_id)
    conversation += f"\n{user_input}"

    # Сохраняем контекст
    save_conversation(user_id, conversation)

    try:
        completion = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                SYSTEM_PROMPT,
                {"role": "user", "content": conversation}
            ]
        )
        answer = completion.choices[0].message.content
        await update.message.reply_text(answer)
    except Exception as e:
        logger.exception("Error in text message")
        if ADMIN_CHAT_ID:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Text error: {str(e)}")

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
        completion = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                SYSTEM_PROMPT,
                {"role": "user", "content": f"Проанализируй следующий текст:\n\n{content}"}
            ]
        )
        answer = completion.choices[0].message.content
        await update.message.reply_text(f"📄 Я изучила файл и вот, что думаю:\n\n{answer[:3500]}")
    except Exception as e:
        logger.exception("Error in document processing")
        if ADMIN_CHAT_ID:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Document processing error: {str(e)}")
        await update.message.reply_text("Не удалось обработать документ. Поддерживаются .txt, .pdf и .docx файлы.")

# Использование polling
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ask", ask))
app.add_handler(CommandHandler("debug", debug))
app.add_handler(CommandHandler("clear", clear_conversation))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

create_db()
app.run_polling()
