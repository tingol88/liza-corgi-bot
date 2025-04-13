import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

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
