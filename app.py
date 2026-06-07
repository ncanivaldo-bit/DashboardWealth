import streamlit as st
import pandas as pd
import numpy as np
import json
import io
import plotly.graph_objects as go
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ==============================================================================
# CONFIGURAÇÃO DE TELA E CSS (TRAVA DE ESPAÇAMENTO 7PX)
# ==============================================================================
st.set_page_config(page_title="PREVPRIV", page_icon="📊", layout="wide")

st.markdown("""
    <style>
        [data-testid="stHeader"] { display: none !important; }
        [data-testid="stMainBlockContainer"] { padding: 0.8rem 1rem !important; max-width: 100% !important; }
        [data-testid="stTabs"] { margin-top: -25px !important; }
        [data-testid="stTabPanel"] { padding-top: 0rem !important; margin-top: -35px !important; }
        h1 { margin-top: -25px !important; font-size: 26px !important; font-weight: 700 !important; }
        #MainMenu, footer, header { visibility: hidden; }
    </style>
""", unsafe_allow_html=True)

st.title("PREVPRIV")

# ==============================================================================
# MOTOR DE DADOS (CORRIGIDO E ROBUSTO)
# ==============================================================================
@st.cache_resource
def get_drive_service():
    key_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = service_account.Credentials.from_service_account_info(key_dict, scopes=['https://www.googleapis.com/auth/drive.readonly'])
    return build('drive', 'v3', credentials=creds)

def download_excel(file_id, sheet_name):
    service = get_drive_service()
    request = service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done: _, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_excel(fh, engine='openpyxl', sheet_name=sheet_name)

@st.cache_data(ttl=600)
def carregar_dados_completos():
    ID = '1d4AMHX5El8JOEbgwpBVm513-ImJPFiGXrRG_2VoObTo'
    df_mov = download_excel(ID, 'Movimentacao')
    df_inf = download_excel(ID, 'Inf_Ativos')
    
    # Limpeza básica
    df_inf.columns = df_inf.columns.astype(str).str.strip()
    df_mov.columns = df_mov.columns.astype(str).str.strip()
    
    # 🎯 CORREÇÃO DO TYPERROR: Forçar conversão antes do groupby
    df_inf['Preco_Atual'] = pd.to_numeric(df_inf['Preco_Atual'], errors='coerce').fillna(0)
    
    # Garantir colunas de texto
    for col in ['Classificacao', 'Seguimento', 'Gestora', 'Ticker']:
        if col not in df_inf.columns: df_inf[col] = 'NÃO INFORMADO'
        df_inf[col] = df_inf[col].fillna('NÃO INFORMADO').astype(str).str.upper()
        
    return df_inf, df_mov

df_inf, df_mov = carregar_dados_completos()

# ==============================================================================
# RENDERIZAÇÃO
# ==============================================================================
aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Alocação"])

with aba_alocacao:
    if not df_inf.empty:
        col_esq, col_dir = st.columns([4, 6])
        
        with col_esq:
            with st.container(border=True):
                st.markdown("<h4 style='margin:0; padding-bottom:4px;'>1. Exposição por Ativo</h4>", unsafe_allow_html=True)
                fig_ativos = go.Figure(go.Bar(
                    x=df_inf['Preco_Atual'], y=df_inf['Ticker'], orientation='h', marker_color='#1fbc74'
                ))
                fig_ativos.update_layout(height=440, margin=dict(l=65, r=15, t=10, b=10), yaxis=dict(type='category', dtick=1, tickfont=dict(size=10)))
                st.plotly_chart(fig_ativos, use_container_width=True)

        with col_dir:
            c1, c2 = st.columns(2)
            with c1:
                with st.container(border=True):
                    st.markdown("<h4 style='margin:0; padding-bottom:2px;'>2. Classificação</h4>", unsafe_allow_html=True)
                    df_g = df_inf.groupby('Classificacao')['Preco_Atual'].sum().reset_index()
                    fig_c = go.Figure(go.Pie(labels=df_g['Classificacao'], values=df_g['Preco_Atual'], hole=0.55, textinfo='label+percent'))
                    fig_c.update_layout(margin=dict(l=5, r=5, t=5, b=0), height=200, showlegend=False)
                    st.plotly_chart(fig_c, use_container_width=True)
            with c2:
                with st.container(border=True):
                    st.markdown("<h4 style='margin:0; padding-bottom:2px;'>3. Seguimento</h4>", unsafe_allow_html=True)
                    df_s = df_inf.groupby('Seguimento')['Preco_Atual'].sum().reset_index()
                    fig_s = go.Figure(go.Pie(labels=df_s['Seguimento'], values=df_s['Preco_Atual'], hole=0.55, textinfo='label+percent'))
                    fig_s.update_layout(margin=dict(l=5, r=5, t=5, b=0), height=200, showlegend=False)
                    st.plotly_chart(fig_s, use_container_width=True)

            # 🎯 ESPAÇAMENTO DE 6PX ENTRE GRÁFICOS (Recuo negativo de -22px puxando para cima)
            st.markdown('<div style="margin-top: -22px;"></div>', unsafe_allow_html=True)
            
            with st.container(border=True):
                st.markdown("<h4 style='margin:0; padding-bottom:4px;'>4. Exposição por Gestora</h4>", unsafe_allow_html=True)
                df_ge = df_inf.groupby('Gestora')['Preco_Atual'].sum().reset_index()
                fig_g = go.Figure(go.Bar(x=df_ge['Preco_Atual'], y=df_ge['Gestora'], orientation='h', marker_color='#118DFF'))
                # Ajuste de altura e margens internas para ele subir e ocupar o espaço
                fig_g.update_layout(margin=dict(l=75, r=15, t=0, b=5), height=330, yaxis=dict(type='category'))
                st.plotly_chart(fig_g, use_container_width=True)
