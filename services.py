import openai
import logging
import sqlite3
import os
import fitz  # PyMuPDF
import docx
from pydub import AudioSegment
import asyncio

from db_utils import (
    save_conversation,
    get_conversation,
    get_relevant_knowledge,
)

logger = logging.getLogger(__name__)
openai.api_key = os.environ["OPENAI_API_KEY"]

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Ты — Лиза, виртуальный помощник клининговой компании Cleaning-Moscow. "
        "Ты гордишься нашей компанией. Отвечай дружелюбно, чётко и только на основе "
        "обучающих материалов, если они есть."
    ),
}


async def process_user_input(user_id, user_input, context, send_reply):
    logger.info(f"User {user_id} wrote: {user_input}")
    context_history = get_conversation(user_id)
    context_history += f"\n{user_input}"
    save_conversation(user_id, context_history)

    knowledge_matches = get_relevant_knowledge(user_input)
    knowledge_text = "\n\n".join(knowledge_matches)
    has_knowledge = bool(knowledge_matches)

    try:
        if has_knowledge:
            note = "🧠 Я нашла информацию в базе знаний:\n\n"
            user_prompt = (
                f"Вот обучающие материалы из базы знаний:\n"
                f"{knowledge_text}\n\n"
                f"Теперь ответь на вопрос, используя ТОЛЬКО эти материалы:\n"
                f"{user_input}"
            )
        else:
            note = ""
            user_prompt = f"Вопрос: {user_input}"

        messages = [
            SYSTEM_PROMPT,
            {"role": "user", "content": user_prompt},
        ]

        completion = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
        )
        answer = completion.choices[0].message.content

        try:
            await send_reply(note + answer, parse_mode="Markdown")
        except Exception:
            await send_reply(note + answer)

    except Exception:
        logger.exception("Ошибка в process_user_input")
        await send_reply("⚠️ Произошла ошибка при обработке запроса.")


async def handle_text(update, context):
    user_id = update.effective_user.id
    user_input = update.message.text.strip()
    await process_user_input(user_id, user_input, context, update.message.reply_text)


async def handle_voice(update, context):
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
                file=audio_file,
            )
        text = transcript.text.strip()
        logger.info(f"Transcribed: {text}")

        user_id = update.effective_user.id
        await process_user_input(user_id, text, context, update.message.reply_text)

    except Exception:
        logger.exception("Error in voice processing")
        await update.message.reply_text(
            "Произошла ошибка при обработке голосового сообщения."
        )


async def handle_document(update, context):
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
            await update.message.reply_text(
                "Пожалуйста, отправьте .txt, .pdf или .docx файл."
            )
            return

        save_conversation(update.effective_user.id, content)
        logger.info(
            f"Received document from {update.effective_user.id}: {document.file_name}"
        )
        await update.message.reply_text(
            "Файл принят и обработан. Я запомнила информацию!"
        )
    except Exception:
        logger.exception("Error in document processing")
        await update.message.reply_text(
            "Не удалось обработать документ. Поддерживаются .txt, .pdf и .docx файлы."
        )


async def sync_every_hour():
    from google_connect import sync_drive_folder_to_knowledge

    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    while True:
        try:
            logger.info("⏳ Автоматическая синхронизация папки Google Диска")
            if folder_id:
                sync_drive_folder_to_knowledge(folder_id)
        except Exception as e:
            logger.error(f"Ошибка при авто-синхронизации: {e}")
        await asyncio.sleep(3600)


# ---------- Логирование первой и последней активности за день ----------

async def log_daily_activity(update, context):
    """
    ВРЕМЕННЫЙ ВАРИАНТ:
    Пишем первую/последнюю активность за день напрямую в БД, минуя db_utils,
    чтобы убедиться, что хендлер работает и БД заполняется.
    """
    msg = update.effective_message
    if msg is None or msg.from_user is None:
        return

    from datetime import datetime

    username = msg.from_user.username or msg.from_user.full_name or ""
    now = msg.date or datetime.utcnow()
    day = now.date().isoformat()
    iso_dt = now.isoformat()

    logger.info(
        f"[ACTIVITY] direct-write chat={msg.chat.id} user={msg.from_user.id} ({username}) day={day} dt={iso_dt}"
    )

    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO daily_user_activity (chat_id, user_id, username, day, first_msg, last_msg)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id, user_id, day) DO UPDATE SET
            username = excluded.username,
            last_msg = excluded.last_msg
    """, (
        msg.chat.id,
        msg.from_user.id,
        username,
        day,
        iso_dt,
        iso_dt,
    ))
    conn.commit()
    conn.close()
