import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient import errors, http
import mimetypes
from io import BytesIO
import fitz  # PyMuPDF
import docx
from db_utils import save_knowledge

GOOGLE_CREDENTIALS_PATH = os.environ["GOOGLE_CREDENTIALS_PATH"]

def get_google_docs_text(document_id):
    creds = service_account.Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH)
    service = build('docs', 'v1', credentials=creds)
    doc = service.documents().get(documentId=document_id).execute()
    text = ""
    for element in doc.get("body", {}).get("content", []):
        if "paragraph" in element:
            for run in element["paragraph"].get("elements", []):
                text += run.get("textRun", {}).get("content", "")
    return text

def get_google_sheet_values(spreadsheet_id, range_name):
    creds = service_account.Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH)
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
    return result.get("values", [])

def sync_drive_folder_to_knowledge(folder_id):
    creds = service_account.Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH)
    drive_service = build('drive', 'v3', credentials=creds)

    results = drive_service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id, name, mimeType)").execute()

    files = results.get('files', [])
    known_types = {
        'application/pdf': 'pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
        'text/plain': 'txt'
    }

    for file in files:
        file_id = file['id']
        name = file['name']
        mime = file['mimeType']
        ext = known_types.get(mime)
        if not ext:
            continue

        content = ""
        request = drive_service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = http.MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        fh.seek(0)
        if ext == 'txt':
            content = fh.read().decode('utf-8', errors='ignore')
        elif ext == 'pdf':
            doc = fitz.open("pdf", fh.read())
            content = "\n".join(page.get_text() for page in doc)
        elif ext == 'docx':
            f = BytesIO(fh.read())
            d = docx.Document(f)
            content = "\n".join([p.text for p in d.paragraphs])

        save_knowledge(name, content.strip(), added_by=126204360)
