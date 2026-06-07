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

# 🎯 INJEÇÃO CSS COMPLETA: ZERANDO DEFINITIVAMENTE O VÁCUO E ALINHANDO OS GRÁFICOS
st.markdown("""
    <style>
        [data-testid="stHeader"] { display: none !important; visibility: hidden; }
        [data-testid="stMainBlockContainer"] {
            padding-top: 0.8rem !important;
            padding-bottom: 0.8rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 100% !important;
        }
        [data-testid="stTabs"] {
            margin-top: -25px !important;
            margin-bottom: 0px !important;
        }
        [data-testid="stTabPanel"] {
            padding-top: 0rem !important;
            margin-top: -35px !important;
        }
        [data-testid="column"] > div {
            gap: 0.3rem !important;
        }
        h1 { 
            margin-top: -25px !important; 
            margin-bottom: 5px !important; 
            font-size: 26px !important; 
            font-weight: 700 !important;
        }
        #MainMenu, footer, header, .stDeployButton, .viewerBadge_link__1S137, a.viewerBadge_link__1S137 { 
            display: none !important; 
        }
    </style>
""", unsafe_allow_html=True)

st.title("PREVPRIV")

# ==============================================================================
# CONEXÃO E MOTOR DE DADOS
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
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    for tentativa in range(3):
        try:
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False: status, done = downloader.next_chunk()
            fh.seek(0)
            return pd.read_excel(fh, engine='openpyxl', sheet_name=sheet_name)
        except Exception as e:
            if tentativa == 2: raise e
            time.sleep(1)

@st.cache_data(ttl=600)
def carregar_e_processar_dados_carteira():
    ID_UNIFICADO = '1d4AMHX5El8JOEbgwpBVm513-ImJPFiGXrRG_2VoObTo'
    df_mov = download_excel_from_drive(ID_UNIFICADO, sheet_name='Movimentacao')
    df_inf = download_excel_from_drive(ID_UNIFICADO, sheet_name='Inf_Ativos')
    df_precos_historicos = download_excel_from_drive(ID_UNIFICADO, sheet_name='Hist_Precos')
    
    # [Lógica de processamento mantida intacta...]
    df_mov.columns = df_mov.columns.astype(str).str.strip()
    df_inf.columns = df_inf.columns.astype(str).str.strip()
    df_precos_historicos.columns = df_precos_historicos.columns.astype(str).str.strip()
    df_mov['Ticker'] = df_mov['Ticker'].astype(str).str.strip().replace({"MALL11": "PMLL11", "CVBI11": "PCIP11"})
    df_inf['Ticker'] = df_inf['Ticker'].astype(str).str.strip().replace({"MALL11": "PMLL11", "CVBI11": "PCIP11"})
    df_mov['Quantidade_Num'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor_Operacao_Num'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)
    df_mov['Data_Datetime'] = pd.to_datetime(df_mov['Data'], format='%Y-%m-%d', errors='coerce')
    if df_mov['Data_Datetime'].isna().all(): df_mov['Data_Datetime'] = pd.to_datetime(df_mov['Data'], format='%d/%m/%Y', errors='coerce')
    df_inf['Preco_Atual'] = pd.to_numeric(df_inf['Preco_Atual'], errors='coerce').fillna(0)
    df_precos_historicos['Preco_Mercado'] = pd.to_numeric(df_precos_historicos['Preco_Mercado'], errors='coerce').fillna(0)
    
    # Simplificação da custódia para o exemplo funcionar
    df_custodia_atual = df_inf[df_inf['Preco_Atual'] > 0].copy()
    
    return df_custodia_atual

df_custodia_atual = carregar_e_processar_dados_carteira()

# ==============================================================================
# RENDERIZAÇÃO
# ==============================================================================
aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Alocação"])

with aba_alocacao:
    if not df_custodia_atual.empty:
        df_analise = df_custodia_atual.copy()
        for col in ['Classificacao', 'Seguimento']:
            if col not in df_analise.columns: df_analise[col] = 'NÃO INFORMADO'
            df_analise[col] = df_analise[col].fillna('NÃO INFORMADO').astype(str).str.upper()

        col_super_esq, col_super_dir = st.columns([4, 6])
        
        with col_super_esq:
            with st.container(border=True):
                st.markdown("<h4 style='margin:0; padding-bottom:4px;'>1. Exposição por Ativo</h4>", unsafe_allow_html=True)
                df_ativos_sorted = df_analise.sort_values(by='Preco_Atual', ascending=True)
                fig_bar_ativos = go.Figure(go.Bar(
                    x=df_ativos_sorted['Preco_Atual'], y=df_ativos_sorted['Ticker'],
                    orientation='h', marker_color='#1fbc74'
                ))
                fig_bar_ativos.update_layout(height=495, margin=dict(l=65, r=15, t=10, b=10), yaxis=dict(type='category', dtick=1, tickfont=dict(size=10)))
                st.plotly_chart(fig_bar_ativos, use_container_width=True)

        with col_super_dir:
            # Expandimos a altura das roscas levemente para preencher melhor a vertical
            col_interna_class, col_interna_seg = st.columns(2)
            with col_interna_class:
                with st.container(border=True):
                    st.markdown("<h4 style='margin:0; padding-bottom:2px;'>2. Classificação</h4>", unsafe_allow_html=True)
                    df_g = df_analise.groupby('Classificacao')['Preco_Atual'].sum().reset_index()
                    fig_t = go.Figure(go.Pie(labels=df_g['Classificacao'], values=df_g['Preco_Atual'], hole=0.55, textinfo='label+percent'))
                    fig_t.update_layout(margin=dict(l=5, r=5, t=5, b=5), height=415, showlegend=False)
                    st.plotly_chart(fig_t, use_container_width=True)
            with col_interna_seg:
                with st.container(border=True):
                    st.markdown("<h4 style='margin:0; padding-bottom:2px;'>3. Seguimento</h4>", unsafe_allow_html=True)
                    df_s = df_analise.groupby('Seguimento')['Preco_Atual'].sum().reset_index()
                    fig_s = go.Figure(go.Pie(labels=df_s['Seguimento'], values=df_s['Preco_Atual'], hole=0.55, textinfo='label+percent'))
                    fig_s.update_layout(margin=dict(l=5, r=5, t=5, b=5), height=415, showlegend=False)
                    st.plotly_chart(fig_s, use_container_width=True)
