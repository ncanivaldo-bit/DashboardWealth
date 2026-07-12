import streamlit as st
import pandas as pd
import numpy as np
import json
import io
import time
import plotly.graph_objects as go
import plotly.express as px
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Configuração Básica
st.set_page_config(page_title="PREVPRIV", page_icon="📊", layout="wide")

# CSS Simplificado apenas para esconder logos, sem margens negativas que quebram o app
st.markdown("""
    <style>
        #MainMenu, footer, header, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton { 
            visibility: hidden !important; display: none !important; 
        }
        [data-testid="stViewerBadge"], .viewerBadge_container { display: none !important; }
    </style>
""", unsafe_allow_html=True)

st.title("PREVPRIV")

# (Mantenha as suas funções de get_drive_service, download_excel_from_drive, 
# calcular_historico_posicoes, extrair_kpis_proventos, formatar_br, etc., exatamente como estão)

# --- INÍCIO DA CORREÇÃO NA ABA DE RESUMO ---
# Substitua o bloco de resumo anterior por este, sem o div de margem negativa
with aba_resumo:
    # ... [seu código de cores] ...
    
    col1, col2, col3, col4 = st.columns(4)
    # [Use as mesmas colunas, mas remova o "margin-bottom: 15px" dos divs se o erro persistir]
    
    # Exemplo de como deve ficar um dos cards, limpo:
    with col1:
        st.markdown(f"""
            <div style="border: 1px solid #ccc; border-radius: 8px; padding: 10px;">
                <span style="font-size: 14px; font-weight: bold;">Patrimônio Atual</span>
                <div style="font-size: 24px; font-weight: bold;">{formatar_br(patrimonio_mercado_kpi)}</div>
            </div>
        """, unsafe_allow_html=True)
    # ... [Repita para col2, col3, col4] ...

    # REMOVA A LINHA: st.markdown('<div style="margin-top: -15px;">', unsafe_allow_html=True)
    # Ela é a causadora do seu erro NotFoundError.
    
    col_bloco_esquerdo, col_bloco_direito = st.columns([6, 4])
    # ... [resto do seu código] ...
