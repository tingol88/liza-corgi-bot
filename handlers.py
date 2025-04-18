from telegram import Update
from telegram.ext import ContextTypes
from db_utils import save_conversation, save_knowledge, find_knowledge_by_keyword
from google_connect import get_google_docs_text, get_google_sheet_values, sync_drive_folder_to_knowledge
import sqlite3

ADMIN_IDS = [126204360, 982915733]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Гав-гав! 🐾 Я Лиза Корги — виртуальный помощник клининговой компании Cleaning-Moscow. Можешь задать вопрос или отправить голосовое сообщение!")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🛠️ Команды Лизы:\n\n"
        "/start — Приветствие и вводная\n"
        "/learn — Обучить Лизу новому знанию (только админ)\n"
        "/ref [запрос] — Найти в базе знаний\n"
        "/list_knowledge [n] — Показать последние записи (до 1000)\n"
        "/clear — Очистить историю общения (только админ)\n"
        "/help — Показать это меню\n"
        "/sync - <ID_папки_на_Google_Диске>"
    )
    await update.message.reply_text(help_text)  # Без parse_mode



async def learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Извините, только администратор может обучать Лизу.")
        return
    text = update.message.text.removeprefix("/learn").strip()
    if not text:
        await update.message.reply_text("Пожалуйста, укажи, чему ты хочешь меня научить. Пример:\n/learn как мы убираем рестораны после открытия")
        return
    lines = text.split("\n", 1)
    title = lines[0][:100]
    content = lines[1] if len(lines) > 1 else lines[0]
    try:
        save_knowledge(title, content, user_id)
        await update.message.reply_text(f"Спасибо, Александр! Я запомнила информацию под названием: \"{title}\"")
    except Exception as e:
        await update.message.reply_text(f"⚠️ {e}")


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


async def list_knowledge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Команда доступна только администраторам.")
        return

    try:
        limit = min(int(context.args[0]), 1000) if context.args else 20
    except ValueError:
        await update.message.reply_text("Укажи число — сколько записей показать. Пример: /list_knowledge 50")
        return

    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, timestamp FROM knowledge ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("База знаний пока пуста.")
        return

    message = f"🧐 Последние {len(rows)} знаний в базе:\n\n"
    for i, (id_, title, timestamp) in enumerate(rows, 1):
        short_title = title[:60] + "..." if len(title) > 60 else title
        message += f"{i}. [ID: {id_}] {short_title} ({timestamp[:19]})\n"
    await update.message.reply_text(message)


async def clear_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
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


async def google_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
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
    if update.effective_user.id not in ADMIN_IDS:
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
    if user_id not in ADMIN_IDS:
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
        await update.message.reply_text(f"Ошибка при синхронизации: {e}")


async def debug_knowledge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Только администратор может использовать отладку.")
        return

    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title, content, timestamp FROM knowledge ORDER BY timestamp DESC LIMIT 5")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📬 База знаний пуста.")
        return

    msg = "🧠 *Последние знания в базе:*\n\n"
    for i, (title, content, ts) in enumerate(rows, 1):
        short = content.strip().replace('\n', ' ')[:120]
        msg += f"{i}. *{title}* ({ts[:19]})\n_{short}_\n\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def delete_knowledge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Только администратор может удалять знания.")
        return

    if not context.args:
        await update.message.reply_text("Укажи один или несколько ID записей для удаления. Пример: /delete_knowledge 123 124")
        return

    try:
        ids = [int(arg) for arg in context.args]
    except ValueError:
        await update.message.reply_text("Все ID должны быть числами. Пример: /delete_knowledge 123 124")
        return

    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()
    placeholders = ','.join('?' for _ in ids)
    cursor.execute(f"DELETE FROM knowledge WHERE id IN ({placeholders})", ids)
    conn.commit()
    deleted = cursor.rowcount
    conn.close()

    if deleted:
        await update.message.reply_text(f"✅ Удалено записей: {deleted}")
    else:
        await update.message.reply_text("⚠️ Ни одна запись не была удалена. Проверь ID.")

