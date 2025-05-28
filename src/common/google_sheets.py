import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from typing import List, Optional

@st.cache_resource(ttl=100_000)
def get_gsheet_client() -> gspread.Client:
    creds_info = st.secrets["google_sheets_credentials"]
    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
    )
    return gspread.authorize(creds)

def open_spreadsheet(secret_key: str) -> gspread.Spreadsheet:
    client = get_gsheet_client()
    sheet_id = st.secrets["general"][secret_key]
    return client.open_by_key(sheet_id)

def get_or_create_worksheet(
    spreadsheet: gspread.Spreadsheet,
    sheet_name: str,
    headers: Optional[List[str]] = None,
    rows: int = 1000,
    cols: int = 30
) -> gspread.Worksheet:

    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=str(rows), cols=str(cols))
        st.warning(f"Worksheet '{sheet_name}' creada.")
        if headers:
            ws.append_row(headers)
    return ws

@st.cache_data(ttl=1_800)
def load_all_records(
    secret_key: str,
    sheet_name: str,
    create_if_missing: bool = False,
    headers: Optional[List[str]] = None
) -> pd.DataFrame:
    try:
        ss = open_spreadsheet(secret_key)
        if create_if_missing:
            ws = get_or_create_worksheet(ss, sheet_name, headers=headers)
        else:
            ws = ss.worksheet(sheet_name)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Spreadsheet {secret_key} no encontrado.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error cargando '{sheet_name}': {e}")
        return pd.DataFrame()

