import sqlite3
from datetime import datetime


def create_db():
    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            user_id INTEGER PRIMARY KEY,
            context TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            user_id INTEGER,
            document_name TEXT,
            document_content TEXT,
            PRIMARY KEY (user_id, document_name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT,
            added_by INTEGER,
            timestamp TEXT
        )
    """)

    # Таблица: первая и последняя активность за день + username
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_user_activity (
            chat_id    INTEGER,
            user_id    INTEGER,
            username   TEXT,
            day        TEXT,   -- 'YYYY-MM-DD'
            first_msg  TEXT,   -- ISO datetime
            last_msg   TEXT,   -- ISO datetime
            PRIMARY KEY (chat_id, user_id, day)
        )
    """)

    conn.commit()
    conn.close()


def save_conversation(user_id, message):
    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()
    cursor.execute(
        "REPLACE INTO conversations (user_id, context) VALUES (?, ?)",
        (user_id, message)
    )
    conn.commit()
    conn.close()


def get_conversation(user_id):
    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT context FROM conversations WHERE user_id = ?",
        (user_id,)
    )
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else ""


def save_knowledge(title, content, added_by):
    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM knowledge WHERE title = ? AND content = ?",
        (title, content)
    )
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO knowledge (title, content, added_by, timestamp) "
            "VALUES (?, ?, ?, ?)",
            (title, content, added_by, datetime.now().isoformat())
        )
        conn.commit()
    conn.close()


def get_relevant_knowledge(query, limit=3):
    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()
    q = f"%{query.lower()}%"
    cursor.execute("""
        SELECT title, content FROM knowledge
        WHERE LOWER(content) LIKE ? OR LOWER(title) LIKE ?
        ORDER BY timestamp DESC LIMIT ?
    """, (q, q, limit))
    results = cursor.fetchall()
    conn.clo
