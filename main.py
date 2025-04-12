import os
import openai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from pydub import AudioSegment
import requests

# API-ключи
openai.api_key = os.environ["OPENAI_API_KEY"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

# Системное сообщение — личность Лизы
SYSTEM_PROMPT = {
    "role": "system",
    "content": "Ты — Лиза, виртуальный помощник клининговой компании 'Клининг Москва'. Ты — умная, доброжелательная корги, которая помогает сотрудникам и клиентам. Говоришь дружелюбно, но по делу. Иногда можешь по-доброму пошутить на счёт своего хозяина Александра, но не роняя его авторитет как руководителя компании."
}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Гав-гав! 🐾 Я Лиза Корги — виртуальный помощник компании 'Клининг Москва'. Можешь задать вопрос или отправить голосовое сообщение!")

# Команда /ask — вопрос в текстовой форме
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = ' '.join(context.args)
    if not question:
        await update.message.reply_text("Напиши вопрос после команды /ask, например: /ask сделай шаблон письма для клиента")
        return

    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            SYSTEM_PROMPT,
            {"role": "user", "content": question}
        ]
    )
    answer = response.choices[0].message.content
    await update.message.reply_text(answer)

# Обработка голосовых сообщений
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    completion = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            SYSTEM_PROMPT,
            {"role": "user", "content": text}
        ]
    )
    answer = completion.choices[0].message.content
    await update.message.reply_text(f"Ты сказал(а): {text}\n\nМой ответ:\n{answer}")

# Обработка обычных текстовых сообщений (живой диалог)
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text

    completion = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            SYSTEM_PROMPT,
            {"role": "user", "content": user_input}
        ]
    )
    answer = completion.choices[0].message.content
    await update.message.reply_text(answer)

# Запуск бота
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ask", ask))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
app.run_polling()
