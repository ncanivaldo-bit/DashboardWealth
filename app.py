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

# Configuração básica de tela
st.set_page_config(page_title="PREVPRIV", layout="wide")

# Conexão direta com o Google Drive
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
            while done is False:
                status, done = downloader.next_chunk()
            fh.seek(0)
            return pd.read_excel(fh, engine='openpyxl', sheet_name=sheet_name)
        except Exception as e:
            if tentativa == 2:
                raise e
            time.sleep(1)

# Motor de dados original
try:
    ID_UNIFICADO = '1d4AMHX5El8JOEbgwpBVm513-ImJPFiGXrRG_2VoObTo'
    
    df_mov = download_excel_from_drive(ID_UNIFICADO, sheet_name='Movimentacao')
    df_inf = download_excel_from_drive(ID_UNIFICADO, sheet_name='Inf_Ativos')
    df_precos_historicos = download_excel_from_drive(ID_UNIFICADO, sheet_name='Hist_Precos')
    
    df_mov.columns = df_mov.columns.astype(str).str.strip()
    df_inf.columns = df_inf.columns.astype(str).str.strip()
    df_precos_historicos.columns = df_precos_historicos.columns.astype(str).str.strip()
    
    df_mov['Ticker'] = df_mov['Ticker'].astype(str).str.strip()
    df_inf['Ticker'] = df_inf['Ticker'].astype(str).str.strip()
    df_precos_historicos['Ticker'] = df_precos_historicos['Ticker'].astype(str).str.strip()
    
    conversao_tickers = {"MALL11": "PMLL11", "CVBI11": "PCIP11"}
    df_mov['Ticker'] = df_mov['Ticker'].replace(conversao_tickers)
    df_precos_historicos['Ticker'] = df_precos_historicos['Ticker'].replace(conversao_tickers)
    
    df_mov['Quantidade_Num'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor_Operacao_Num'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)
    df_mov['Data_Datetime'] = pd.to_datetime(df_mov['Data'], format='%Y-%m-%d', errors='coerce')
    if df_mov['Data_Datetime'].isna().all():
        df_mov['Data_Datetime'] = pd.to_datetime(df_mov['Data'], format='%d/%m/%Y', errors='coerce')

    df_inf['Preco_Atual'] = pd.to_numeric(df_inf['Preco_Atual'], errors='coerce').fillna(0)
    df_precos_historicos['Preco_Mercado'] = pd.to_numeric(df_precos_historicos['Preco_Mercado'], errors='coerce').fillna(0)
    df_precos_historicos['Chave_Merge'] = df_precos_historicos['Chave_Merge'].astype(str).str.strip()

    eventos_custodia = ['Compra', 'Venda', 'Desdobro']
    df_trades = df_mov[df_mov['Movimentação'].isin(eventos_custodia)].sort_values('Data_Datetime').copy()
    
    carteira = {}
    historico_detalhado = []
    
    for _, row in df_trades.iterrows():
        ticker = row['Ticker']
        data = row['Data_Datetime']
        mov = row['Movimentação']
        qtd = float(row['Quantidade_Num'])
        valor = float(row['Valor_Operacao_Num'])
        
        if pd.isna(data):
            continue
            
        if ticker not in carteira:
            carteira[ticker] = {'quantidade': 0.0, 'custo_total': 0.0, 'preco_medio': 0.0}
            
        if mov == 'Compra':
            carteira[ticker]['quantidade'] += qtd
            carteira[ticker]['custo_total'] += valor
        elif mov == 'Venda':
            if carteira[ticker]['quantidade'] > 0:
                qtd_venda = min(qtd, carteira[ticker]['quantidade'])
                carteira[ticker]['custo_total'] -= qtd_venda * carteira[ticker]['preco_medio']
            carteira[ticker]['quantidade'] -= qtd
        elif mov == 'Desdobro':
            carteira[ticker]['quantidade'] += qtd
            
        if carteira[ticker]['quantidade'] > 0:
            carteira[ticker]['preco_medio'] = carteira[ticker]['custo_total'] / carteira[ticker]['quantidade']
        else:
            carteira[ticker]['quantidade'] = 0.0
            carteira[ticker]['custo_total'] = 0.0
            carteira[ticker]['preco_medio'] = 0.0
            
        for tk, dados in carteira.items():
            historico_detalhado.append({
                'Data': data,
                'Ticker': tk,
                'Quantidade': dados['quantidade'],
                'Custo_Total': dados['custo_total']
            })
            
    df_hist_ativos = pd.DataFrame(historico_detalhado)
    if not df_hist_ativos.empty:
        df_hist_ativos['Data'] = pd.to_datetime(df_hist_ativos['Data'])
        df_mensal_ativos = (df_hist_ativos
                            .set_index('Data')
                            .groupby('Ticker')[['Quantidade', 'Custo_Total']]
                            .resample('ME')
                            .last()
                            .ffill()
                            .reset_index())
        
        df_mensal_ativos.loc[df_mensal_ativos['Quantidade'] <= 0, 'Custo_Total'] = 0.0
        df_mensal_ativos['Chave_Merge'] = df_mensal_ativos['Data'].dt.strftime('%Y-%m')
        df_mensal_ativos['Mes_Ano'] = df_mensal_ativos['Data'].dt.to_period('M')
        df_mensal_ativos['Ano_Str'] = df_mensal_ativos['Data'].dt.strftime('%Y')
        
        df_consolidado = pd.merge(df_mensal_ativos, df_precos_historicos, on=['Chave_Merge', 'Ticker'], how='left')
        df_consolidado = pd.merge(df_consolidado, df_inf[['Ticker', 'Preco_Atual', 'Tipo']], on='Ticker', how='left')
        
        mes_atual_chave = pd.Timestamp.now().strftime('%Y-%m')
        df_consolidado.loc[df_consolidado['Chave_Merge'] == mes_atual_chave, 'Preco_Mercado'] = df_consolidado['Preco_Atual']
        
        df_consolidado['Preco_Mercado'] = df_consolidado['Preco_Mercado'].fillna(df_consolidado['Custo_Total'] / df_consolidado['Quantidade']).fillna(0)
        df_consolidado['Patrimonio_Mercado_Ativo'] = df_consolidado['Quantidade'] * df_consolidado['Preco_Mercado']
        
        df_custodia_atual = df_consolidado[df_consolidado['Chave_Merge'] == mes_atual_chave].copy()
        df_custodia_atual = df_custodia_atual[df_custodia_atual['Quantidade'] > 0]

except Exception as e:
    st.error(f"❌ Erro no motor de cálculo: {e}")

# ==============================================================================
# RENDERIZAÇÃO DA INTERFACE VISUAL LIMPA (SEM ADORNOS)
# ==============================================================================

# 🏢 LINHA DE CONTROLE SUPERIOR (Cópia exata da sua imagem de referência)
col_titulo, col_vazio, col_filtro = st.columns([6, 3, 3])

with col_titulo:
    st.markdown("<h2 style='margin: 0; color:#FFFFFF; font-size: 24px; font-weight: 500;'>Evolução do Patrimônio</h2>", unsafe_allow_html=True)

with col_filtro:
    anos_disponiveis = ["Desde o início"] + sorted(list(df_consolidado['Ano_Str'].unique()), reverse=True)
    filtro_ano = st.selectbox("Período", options=anos_disponiveis, index=0, label_visibility="collapsed")

st.markdown("<br>", unsafe_allow_html=True)

# Filtro de data aplicado à evolução
df_filtrado_grafico = df_consolidado.copy()
if filtro_ano != "Desde o início":
    df_filtrado_grafico = df_filtrado_grafico[df_filtrado_grafico['Ano_Str'] == filtro_ano]

# 🏁 GRID GRÁFICOS LADO A LADO NA PROPORÇÃO CRUA 60% / 40%
col_esq_barras, col_dir_rosca = st.columns([6, 4])

with col_esq_barras:
    if not df_filtrado_grafico.empty:
        df_totais_mensais = df_filtrado_grafico.groupby('Mes_Ano').agg({
            'Custo_Total': 'sum',
            'Patrimonio_Mercado_Ativo': 'sum'
        }).reset_index().sort_values('Mes_Ano')
        
        df_totais_mensais['Mês_Exibição'] = df_totais_mensais['Mes_Ano'].dt.strftime('%m/%Y')
        df_totais_mensais['Valor_Aplicado'] = df_totais_mensais['Custo_Total']
        df_totais_mensais['Ganho_de_Capital'] = df_totais_mensais['Patrimonio_Mercado_Ativo'] - df_totais_mensais['Custo_Total']

        fig_barras = go.Figure()
        
        # Barra 1: Valor aplicado (Verde Médio)
        fig_barras.add_trace(go.Bar(
            x=df_totais_mensais['Mês_Exibição'], 
            y=df_totais_mensais['Valor_Aplicado'],
            name='Valor aplicado',
            marker_color='#1fbc74', 
            hovertemplate='<b>Aplicado:</b> R$ %{y:,.2f}<extra></extra>'
        ))
        
        # Barra 2: Ganho de Capital (Verde Claro empilhado relativo)
        fig_barras.add_trace(go.Bar(
            x=df_totais_mensais['Mês_Exibição'], 
            y=df_totais_mensais['Ganho_de_Capital'],
            name='Ganho de Capital',
            marker_color='#7ee0b3',
            hovertemplate='<b>Ganho Cap:</b> R$ %{y:,.2f}<extra></extra>'
        ))
        
        fig_barras.update_layout(
            margin=dict(l=40, r=10, t=10, b=10),
            height=310, # Achatado
            barmode='relative',
            bargap=0.2,
            hovermode='x unified',
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            yaxis=dict(gridcolor='rgba(230,235,240,0.15)', tickprefix="R$ "),
            xaxis=dict(gridcolor='rgba(0,0,0,0)', type='category'),
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_barras, use_container_width=True)

with col_dir_rosca:
    if not df_custodia_atual.empty:
        df_rosca = df_custodia_atual.sort_values(by='Patrimonio_Mercado_Ativo', ascending=False).copy()
        
        labels_legendas = []
        total_mercado_rosca = df_rosca['Patrimonio_Mercado_Ativo'].sum()
        for _, row_r in df_rosca.iterrows():
            pct = (row_r['Patrimonio_Mercado_Ativo'] / total_mercado_rosca) * 100 if total_mercado_rosca > 0 else 0.0
            labels_legendas.append(f"<b>{row_r['Ticker']}</b> ({pct:.1f}%)")
        
        fig_pie = go.Figure()
        fig_pie.add_trace(go.Pie(
            labels=labels_legendas, 
            values=df_rosca['Patrimonio_Mercado_Ativo'],
            hole=0.55,
            domain=dict(x=[0.0, 0.65]), # Zoom reduzido para dar respiro
            textinfo='none',
            hovertemplate='<b>Ativo:</b> %{label}<br><b>Valor:</b> R$ %{value:,.2f}<extra></extra>'
        ))
        
        fig_pie.update_layout(
            margin=dict(l=0, r=0, t=10, b=10),
            height=310,
            paper_bgcolor='rgba(0,0,0,0)',
            showlegend=True,
            legend=dict(
                orientation="v", 
                yanchor="middle", 
                y=0.5, 
                xanchor="left", 
                x=0.70,
                font=dict(size=11, color="#FFFFFF")
            )
        )
        st.plotly_chart(fig_pie, use_container_width=True)
