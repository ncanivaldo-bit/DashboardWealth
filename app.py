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

h1 {
    margin-top: -20px !important;
}

#MainMenu, footer, header {
    visibility: hidden;
}
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

    return df_mov, df_inf, df_hist

df_mov, df_inf, df_hist = carregar_dados()

# ==============================================================================
# ABA
# ==============================================================================
aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Alocação"])

# ------------------------------------------------------------------------------
# RESUMO
# ------------------------------------------------------------------------------
with aba_resumo:
    st.write("Resumo carregado normalmente")

# ------------------------------------------------------------------------------
# ALOCAÇÃO (COM AJUSTES CORRETOS)
# ------------------------------------------------------------------------------
with aba_alocacao:

    if not df_inf.empty:

        df = df_inf.copy()

        if 'Classificacao' not in df.columns:
            df['Classificacao'] = 'NÃO INFORMADO'

        if 'Seguimento' not in df.columns:
            df['Seguimento'] = 'NÃO INFORMADO'

        if 'Gestora' not in df.columns:
            df['Gestora'] = 'NÃO INFORMADO'

        col1, col2 = st.columns([4,6])

        # ESQUERDA
        with col1:
            with st.container(border=True):

                df_sorted = df.sort_values(by='Preco_Atual', ascending=True)

                fig1 = go.Figure(go.Bar(
                    x=df_sorted['Preco_Atual'],
                    y=df_sorted['Ticker'],
                    orientation='h'
                ))

                fig1.update_layout(
                    height=540,
                    margin=dict(l=60, r=10, t=10, b=10)
                )

                st.plotly_chart(fig1, use_container_width=True)

        # DIREITA
        with col2:

            col_a, col_b = st.columns(2)

            # CLASSIFICAÇÃO
            with col_a:
                with st.container(border=True):

                    df_tipo = df.groupby('Classificacao')['Preco_Atual'].sum().reset_index()

                    fig2 = go.Figure(go.Pie(
                        labels=df_tipo['Classificacao'],
                        values=df_tipo['Preco_Atual'],
                        hole=0.55
                    ))

                    fig2.update_layout(
                        height=210,
                        margin=dict(l=5, r=5, t=10, b=0)
                    )

                    st.plotly_chart(fig2, use_container_width=True)

            # SEGUIMENTO
            with col_b:
                with st.container(border=True):

                    df_seg = df.groupby('Seguimento')['Preco_Atual'].sum().reset_index()

                    fig3 = go.Figure(go.Pie(
                        labels=df_seg['Seguimento'],
                        values=df_seg['Preco_Atual'],
                        hole=0.55
                    ))

                    fig3.update_layout(
                        height=210,
                        margin=dict(l=5, r=5, t=10, b=0)
                    )

                    st.plotly_chart(fig3, use_container_width=True)

            # GESTORA
            with st.container(border=True):

                df_gest = df.groupby('Gestora')['Preco_Atual'].sum().reset_index()

                fig4 = go.Figure(go.Bar(
                    x=df_gest['Preco_Atual'],
                    y=df_gest['Gestora'],
                    orientation='h'
                ))

                fig4.update_layout(
                    height=320,
                    margin=dict(l=70, r=10, t=10, b=0)
                )

                st.plotly_chart(fig4, use_container_width=True)

    else:
        st.info("Sem dados disponíveis.")
