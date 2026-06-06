import streamlit as st
import pandas as pd
import json
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

st.set_page_config(page_title="PREVPRIV (Diagnóstico 2)", page_icon="📊", layout="wide")
st.title("PREVPRIV - Diagnóstico de Colunas (Movimentação)")

@st.cache_resource
def get_drive_service():
    key_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = service_account.Credentials.from_service_account_info(
        key_dict, scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

def download_excel_from_drive(file_id, sheet_name=0):
    service = get_drive_service()
    request = service.files().export_media(
        fileId=file_id, 
        mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_excel(fh, engine='openpyxl', sheet_name=sheet_name)

try:
    # Seu ID oficial da planilha de Movimentação convertida
    ID_MOV = '1jb-uqvlTQ7j07p7akDjYiXew1387VKipXch72x755vM'
    df_mov = download_excel_from_drive(ID_MOV, sheet_name=0)
    
    st.write("### 🔍 Colunas encontradas na sua planilha REAL de Movimentação:")
    colunas_reais = list(df_mov.columns)
    st.write(colunas_reais)
    
    st.write("### 📄 Primeiras linhas do arquivo para conferência:")
    st.dataframe(df_mov.head(3))

except Exception as e:
    st.error(f"Erro ao tentar ler o arquivo de movimentações: {e}")
