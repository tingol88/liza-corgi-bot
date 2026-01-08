import os
from io import BytesIO
import sqlite3

import fitz  # PyMuPDF
import docx
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient import http

from db_utils import save_knowledge

GOOGLE_CREDENTIALS_PATH = os.environ["GOOGLE_CREDENTIALS_PATH"]


def _get_creds():
    return service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_PATH
    )


# -------- Google Docs / Sheets чтение --------


def get_google_docs_text(document_id: str) -> str:
    creds = _get_creds()
    service = build("docs", "v1", credentials=creds)
    doc = service.documents().get(documentId=document_id).execute()
    text = ""
    for element in doc.get("body", {}).get("content", []):
        if "paragraph" in element:
            for run in element["paragraph"].get("elements", []):
                text += run.get("textRun", {}).get("content", "")
    return text


def get_google_sheet_values(spreadsheet_id: str, range_name: str):
    creds = _get_creds()
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
    ).execute()
    return result.get("values", [])


# -------- Синхронизация папки Google Drive в базу знаний --------


def sync_drive_folder_to_knowledge(folder_id: str):
    creds = _get_creds()
    drive_service = build("drive", "v3", credentials=creds)

    results = drive_service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id, name, mimeType)",
    ).execute()

    files = results.get("files", [])
    known_types = {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "text/plain": "txt",
    }

    for file in files:
        file_id = file["id"]
        name = file["name"]
        mime = file["mimeType"]
        ext = known_types.get(mime)
        if not ext:
            continue

        request = drive_service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = http.MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        fh.seek(0)
        if ext == "txt":
            content = fh.read().decode("utf-8", errors="ignore")
        elif ext == "pdf":
            doc = fitz.open("pdf", fh.read())
            content = "\n".join(page.get_text() for page in doc)
        elif ext == "docx":
            f = BytesIO(fh.read())
            d = docx.Document(f)
            content = "\n".join(p.text for p in d.paragraphs)
        else:
            content = ""

        if content.strip():
            # 126204360 – твой user_id, чтобы было видно, кто загрузил
            save_knowledge(name, content.strip(), added_by=126204360)


# -------- Экспорт daily_user_activity в Google Sheets --------


def export_daily_activity_to_sheet(spreadsheet_id: str, range_name: str):
    """
    Экспортирует всю таблицу daily_user_activity в указанный диапазон Google Sheets.

    Формат колонок:
    [chat_id, user_id, username, day, first_msg, last_msg]
    """
    conn = sqlite3.connect("liza_db.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT chat_id, user_id, username, day, first_msg, last_msg
        FROM daily_user_activity
        ORDER BY day, chat_id, user_id
        """
    )
    rows = cursor.fetchall()
    conn.close()

    values = [["chat_id", "user_id", "username", "day", "first_msg", "last_msg"]]
    for chat_id, user_id, username, day, first_msg, last_msg in rows:
        values.append(
            [
                str(chat_id),
                str(user_id),
                username or "",
                day,
                first_msg,
                last_msg,
            ]
        )

    creds = _get_creds()
    service = build("sheets", "v4", credentials=creds)
    body = {"values": values}

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        body=body,
    ).execute()


# -------- Новое: просто записать число в Excel (Google Sheets) --------


def write_number_to_sheet(spreadsheet_id: str, range_name: str, number: float):
    """
    Записывает одно число в указанную ячейку Google Sheets.

    Пример:
    write_number_to_sheet(
        "1Ge5cv6pd5mQjL56GLFFmXFy985sOAm1yf9kJeRnciQ",
        "Лист1!B2",
        777,
    )
    """
    creds = _get_creds()
    service = build("sheets", "v4", credentials=creds)

    body = {"values": [[number]]}

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        body=body,
    ).execute()
