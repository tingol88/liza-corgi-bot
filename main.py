import os
import openai
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from pydub import AudioSegment
import requests

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

ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))

openai.api_key = os.environ["OPENAI_API_KEY"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

SYSTEM_PROMPT = {
    "role": "system",
    "content": "Ты — Лиза, виртуальный помощник клининговой компании Cleaning-Moscow. Ты — умная, доброжелательная корги, которая помогает сотрудникам и клиентам. Говоришь дружелюбно, но по делу. Иногда можешь по-доброму пошутить на счёт своего хозяина Александра, но не роняя его авторитет как руководителя компании. Сайт: cleaning-moscow.ru."
}

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
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("Sorry, this command is for administrator only.")
        return
    try:
        with open("liza_corgi.log", "r") as f:
            lines = f.readlines()[-20:]
        log_text = "".join(lines)
        await update.message.reply_text(f"Last lines from log:\n\n{log_text}")
    except Exception as e:
        await update.message.reply_text(f"Could not read log: {e}")

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
    if update.message.chat.type != "private" and f"@{context.bot.username}" not in update.message.text:
        return
    user_input = update.message.text
    logger.info(f"User {update.effective_user.id} wrote: {user_input}")
    try:
        completion = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                SYSTEM_PROMPT,
                {"role": "user", "content": user_input}
            ]
        )
        answer = completion.choices[0].message.content
        await update.message.reply_text(answer)
    except Exception as e:
        logger.exception("Error in text message")
        if ADMIN_CHAT_ID:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Text error: {str(e)}")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ask", ask))
app.add_handler(CommandHandler("debug", debug))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
app.run_polling()
