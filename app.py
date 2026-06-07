import streamlit as st
import pandas as pd
import numpy as np
import json
import io
import time
import plotly.graph_objects as go
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ==============================================================================
# CONFIGURAÇÃO DE TELA
# ==============================================================================
st.set_page_config(page_title="PREVPRIV", page_icon="📊", layout="wide")

st.markdown("""
<style>
[data-testid="stHeader"] { display: none !important; }

[data-testid="stMainBlockContainer"] {
    padding-top: 0.8rem !important;
    padding-bottom: 0.8rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    max-width: 100% !important;
}

[data-testid="stTabs"] {
    margin-top: -25px !important;
}

[data-testid="stTabPanel"] {
    padding-top: 0 !important;
    margin-top: -10px !important;
}

h1 { margin-top: -20px !important; }

#MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

st.title("PREVPRIV")

# ==============================================================================
# GOOGLE DRIVE
# ==============================================================================
@st.cache_resource
def get_drive_service():
    key_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = service_account.Credentials.from_service_account_info(
        key_dict,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

def download_excel_from_drive(file_id, sheet_name=0):
    service = get_drive_service()

    request = service.files().export_media(
        fileId=file_id,
        mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

    for tentativa in range(3):
        try:
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False

            while not done:
                _, done = downloader.next_chunk()

            fh.seek(0)
            return pd.read_excel(fh, engine='openpyxl', sheet_name=sheet_name)

        except:
            if tentativa == 2:
                raise
            time.sleep(1)

# ==============================================================================
# DADOS
# ==============================================================================
@st.cache_data(ttl=600)
def carregar_dados():
    ID = "1d4AMHX5El8JOEbgwpBVm513-ImJPFiGXrRG_2VoObTo"

    df_mov = download_excel_from_drive(ID, 'Movimentacao')
    df_inf = download_excel_from_drive(ID, 'Inf_Ativos')
    df_hist = download_excel_from_drive(ID, 'Hist_Precos')

    # 🔥 CORREÇÃO PRINCIPAL (tipo numérico)
    if 'Preco_Atual' in df_inf.columns:
        df_inf['Preco_Atual'] = (
            df_inf['Preco_Atual']
            .astype(str)
            .str.replace('R$', '', regex=False)
            .str.replace('.', '', regex=False)
            .str.replace(',', '.', regex=False)
        )
        df_inf['Preco_Atual'] = pd.to_numeric(df_inf['Preco_Atual'], errors='coerce').fillna(0)

    return df_mov, df_inf, df_hist

df_mov, df_inf, df_hist = carregar_dados()

# ==============================================================================
# ABAS
# ==============================================================================
aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Alocação"])

# ------------------------------------------------------------------------------
# RESUMO
# ------------------------------------------------------------------------------
with aba_resumo:
    st.write("Resumo mantido como está (sem alterações)")

# ------------------------------------------------------------------------------
# ALOCAÇÃO
# ------------------------------------------------------------------------------
with aba_alocacao:

    if not df_inf.empty:

        df = df_inf.copy()

        # Garantia adicional (segurança)
        df['Preco_Atual'] = pd.to_numeric(df['Preco_Atual'], errors='coerce').fillna(0)

        if 'Classificacao' not in df.columns:
            df['Classificacao'] = 'NÃO INFORMADO'

        if 'Seguimento' not in df.columns:
            df['Seguimento'] = 'NÃO INFORMADO'

        if 'Gestora' not in df.columns:
            df['Gestora'] = 'NÃO INFORMADO'

        col_esq, col_dir = st.columns([4,6])

        # =========================================================
        # ESQUERDA
        # =========================================================
        with col_esq:
            with st.container(border=True):

                df_sorted = df.sort_values(by='Preco_Atual', ascending=True)

                fig_bar_ativos = go.Figure(go.Bar(
                    x=df_sorted['Preco_Atual'],
                    y=df_sorted['Ticker'],
                    orientation='h',
                    marker_color='#1fbc74'
                ))

                fig_bar_ativos.update_layout(
                    margin=dict(l=65, r=15, t=10, b=10),
                    height=540
                )

                st.plotly_chart(fig_bar_ativos, use_container_width=True)

        # =========================================================
        # DIREITA
        # =========================================================
        with col_dir:

            col_class, col_seg = st.columns(2)


