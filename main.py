import os
import openai
import logging
from telegram import Update, Document
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from pydub import AudioSegment
import requests
import fitz  # PyMuPDF
import docx  # python-docx

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
    "content": "Ты — Лиза, виртуальный помощник клининговой компании Cleaning-Moscow. Ты — умная, доброжелательная корги, которая помогает сотрудникам и клиентам. Говоришь дружелюбно, но по делу. Иногда можешь по-доброму и с юмором упомянуть своего хозяина Александра, подчеркивая его профессионализм, но делаешь это не слишком часто. Сайт: cleaning-moscow.ru."
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
        await update.message.reply_text("Извините, эта команда только для администратора.")
        return
    try:
        with open("liza_corgi.log", "r") as f:
            lines = f.readlines()[-20:]
        log_text = "".join(lines)
        await update.message.reply_text(f"Последние строки из логов:\n\n{log_text}")
    except Exception as e:
        await update.message.reply_text(f"Не удалось прочитать лог: {e}")

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

from telegram.ext import Application

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ask", ask))
app.add_handler(CommandHandler("debug", debug))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

import asyncio
from aiohttp import web

async def webhook_handler(request):
    update = Update.de_json(await request.json(), app.bot)
    await app.process_update(update)
    return web.Response(text="ok")

async def main():
    await app.bot.set_webhook("https://srv-cvtc9115pdvs739lcan0.onrender.com/webhook")
    app_web = web.Application()
    app_web.router.add_post("/webhook", webhook_handler)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 10000)))
    await site.start()
    logger.info("Webhook server started")
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())
