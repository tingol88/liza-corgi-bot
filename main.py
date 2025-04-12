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
    "content": "Ты — Лиза, виртуальный помощник клининговой компании Cleaning-Moscow. Ты — умная, доброжелательная корги, которая помогает сотрудникам и клиентам. Говоришь дружелюбно, но по делу. Иногда можешь по-доброму пошутить на счёт своего хозяина Александра, но не роняя его авторитет как руководителя компании. Сайт: cleaning-moscow.ru."
}

# ... все функции start, ask, debug, handle_voice, handle_text остаются без изменений ...

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        document = update.message.document
        file_path = f"./{document.file_name}"
        await context.bot.get_file(document.file_id).download_to_drive(file_path)

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

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ask", ask))
app.add_handler(CommandHandler("debug", debug))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
app.run_polling()
