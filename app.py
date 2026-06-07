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
# CONFIGURAÇÃO DE TELA E IDENTIDADE VISUAL
# ==============================================================================
st.set_page_config(page_title="PREVPRIV", page_icon="📊", layout="wide")

# ✅ CSS LIMPO E ESTÁVEL (SEM HACKS CONFLITANTES)
st.markdown("""
<style>
[data-testid="stHeader"] { display: none !important; }

[data-testid="stMainBlockContainer"] {
    padding-top: 0.6rem !important;
    padding-bottom: 0.8rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    max-width: 100% !important;
}

[data-testid="stTabs"] {
    margin-top: -18px !important;
    margin-bottom: 0px !important;
}

[data-testid="stTabPanel"] {
    padding-top: 0px !important;
    margin-top: -8px !important;
}

/* Título */
h1 {
    margin-top: -12px !important;
    margin-bottom: 5px !important;
    font-size: 26px !important;
    font-weight: 700 !important;
}

/* Ocultar UI nativa */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none !important; }
.viewerBadge_link__1S137 { display: none !important; }
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
        key_dict, scopes=['https://www.googleapis.com/auth/drive.readonly']
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
# MOTOR DE DADOS
# ==============================================================================
@st.cache_data(ttl=600)
def carregar_dados():
    ID = '1d4AMHX5El8JOEbgwpBVm513-ImJPFiGXrRG_2VoObTo'

    df_mov = download_excel_from_drive(ID, 'Movimentacao')
    df_inf = download_excel_from_drive(ID, 'Inf_Ativos')
    df_hist = download_excel_from_drive(ID, 'Hist_Precos')

    for df in [df_mov, df_inf, df_hist]:
        df.columns = df.columns.astype(str).str.strip()

    df_mov['Data'] = pd.to_datetime(df_mov['Data'], errors='coerce')
    df_mov['Quantidade'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor da Operação'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)

    return df_mov, df_inf, df_hist

df_mov, df_inf, df_hist = carregar_dados()

# ==============================================================================
# KPIs SIMPLES (mantive núcleo funcional)
# ==============================================================================
compras = df_mov[df_mov['Movimentação'] == 'Compra']['Valor da Operação'].sum()
vendas = df_mov[df_mov['Movimentação'] == 'Venda']['Valor da Operação'].sum()
dividendos = df_mov[df_mov['Movimentação'].isin(['Dividendo','Rendimento'])]['Valor da Operação'].sum()

patrimonio = compras - vendas
lucro = dividendos

# ==============================================================================
# INTERFACE
# ==============================================================================
aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Alocação"])

# ------------------------------------------------------------------------------
# RESUMO
# ------------------------------------------------------------------------------
with aba_resumo:

    def br(v):
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    col1, col2, col3 = st.columns(3)

    col1.metric("Patrimônio", br(patrimonio))
    col2.metric("Dividendos", br(dividendos))
    col3.metric("Lucro Total", br(lucro))

    # Gráfico simples
    df_group = df_mov.groupby(df_mov['Data'].dt.to_period('M'))['Valor da Operação'].sum().reset_index()
    df_group['Data'] = df_group['Data'].astype(str)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_group['Data'],
        y=df_group['Valor da Operação'],
        mode='lines+markers'
    ))

    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)


# ------------------------------------------------------------------------------
# ALOCAÇÃO
# ------------------------------------------------------------------------------
with aba_alocacao:

    if not df_inf.empty:
        df = df_inf.copy()

        if 'Classificacao' not in df:
            df['Classificacao'] = 'N/A'

        df_group = df.groupby('Classificacao')['Preco_Atual'].sum().reset_index()

        fig = go.Figure(go.Pie(
            labels=df_group['Classificacao'],
            values=df_group['Preco_Atual'],
            hole=0.5
        ))

        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("Sem dados disponíveis.")
