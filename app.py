import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA
# ==============================================================================
st.set_page_config(page_title="Dashboard Wealth | PREVPRIV", page_icon="📊", layout="wide")
st.title("PREVPRIV: Dashboard Wealth")
st.markdown("🎯 **Missão:** Do vácuo absoluto a renda passiva sustentável")
st.divider()

# ==============================================================================
# LIGAÇÃO SEGURA AO GOOGLE DRIVE (A sua Automação)
# ==============================================================================
@st.cache_resource
def get_drive_service():
    # Lê a chave secreta que você guardou no painel do Streamlit
    key_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = service_account.Credentials.from_service_account_info(
        key_dict, scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    return build('drive', 'v3', credentials=creds)

def download_excel_from_drive(file_id, sheet_name=0):
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_excel(fh, engine='openpyxl', sheet_name=sheet_name)

# ==============================================================================
# MOTOR DE DADOS
# ==============================================================================
@st.cache_data(ttl=3600) # O site guarda os dados e atualiza-se sozinho
def carregar_dados():
    # Os IDs extraídos dos seus links
    ID_INF = '16GSsk9lcLnXO7YQaJmIW28mM9CrYZuJs'
    ID_METRICAS = '1D3Nz78rVTEDMl8SOU29lXf_TMZz-sy4M'
    ID_MOV = '1TLXXzLqLYDJXDO8H7i1Qfk8tNReXPzFy'
    
    # Faz o download instantâneo da versão mais recente do Drive
    df_inf = download_excel_from_drive(ID_INF)
    df_meta_seg = download_excel_from_drive(ID_METRICAS, sheet_name='Seguimento')
    df_meta_tipo = download_excel_from_drive(ID_METRICAS, sheet_name='Tipo')
    df_mov = download_excel_from_drive(ID_MOV)
    
    # --- PROCESSAMENTO DOS SEUS ATIVOS ---
    # Proventos
    df_prov = df_mov[df_mov['Movimentação'].isin(['Rendimento', 'Juros Sobre Capital Próprio'])].copy()
    df_prov['Ticker'] = df_prov['Produto'].str.split(' - ').str[0].str.strip()
    df_prov['Data'] = pd.to_datetime(df_prov['Data'], format='%d/%m/%Y', errors='coerce')
    df_prov['Valor da Operação'] = pd.to_numeric(df_prov['Valor da Operação'].astype(str).str.replace('-', '0').str.replace(',', '.'), errors='coerce').fillna(0)
    df_ultimo_prov = df_prov.sort_values('Data').groupby('Ticker')['Valor da Operação'].last().reset_index()
    df_ultimo_prov.rename(columns={'Valor da Operação': 'Ultimo_Provento'}, inplace=True)
    
    # Posição Atual e Preço Médio
    df_carteira = df_mov[df_mov['Movimentação'].isin(['Transferência - Liquidação', 'Compra', 'Venda'])].copy()
    df_carteira['Ticker'] = df_carteira['Produto'].str.split(' - ').str[0].str.strip()
    df_carteira['Quantidade'] = pd.to_numeric(df_carteira['Quantidade'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
    df_carteira['Valor da Operação'] = pd.to_numeric(df_carteira['Valor da Operação'].astype(str).str.replace('-', '').str.replace(',', '.'), errors='coerce').fillna(0)
    
    df_consolidado = df_carteira.groupby('Ticker').agg({'Quantidade': 'sum', 'Valor da Operação': 'sum'}).reset_index()
    df_consolidado['Preco_Medio'] = df_consolidado['Valor da Operação'] / df_consolidado['Quantidade']
    df_consolidado = df_consolidado[df_consolidado['Quantidade'] > 0]
    
    return df_consolidado, df_inf, df_meta_seg, df_meta_tipo, df_ultimo_prov

# Carrega tudo usando a inteligência acima
df_atual, df_inf, df_meta_seg, df_meta_tipo, df_ultimo_prov = carregar_dados()

df_alocacao = pd.merge(df_atual, df_inf, on='Ticker', how='left')
df_alocacao[['Classificacao', 'Tipo', 'Seguimento', 'Gestora']] = df_alocacao[['Classificacao', 'Tipo', 'Seguimento', 'Gestora']].fillna('Não Classificado')
df_alocacao['Patrimonio_Mercado'] = df_alocacao['Quantidade'] * df_alocacao['Preco_Atual']
total_patrimonio = df_alocacao['Patrimonio_Mercado'].sum()

# ==============================================================================
# NAVEGAÇÃO E GRÁFICOS
# ==============================================================================
aba1, aba2 = st.tabs(["📊 Visão Global (Raio-X)", "⚙️ Operações e Rebalanceamento"])

with aba1:
    st.header("Análise de Risco e Composição")
    
    df_ativo = df_alocacao.groupby('Ticker')['Patrimonio_Mercado'].sum().reset_index().sort_values(by='Patrimonio_Mercado', ascending=True)
    df_ativo['Percentual_Texto'] = (df_ativo['Patrimonio_Mercado'] / total_patrimonio * 100).apply(lambda x: f"{x:.1f}%".replace('.', ','))
    df_ativo['Valor_Texto'] = df_ativo['Patrimonio_Mercado'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
    
    df_gestora = df_alocacao.groupby('Gestora')['Patrimonio_Mercado'].sum().reset_index().sort_values(by='Patrimonio_Mercado', ascending=True)
    df_gestora['Percentual_Texto'] = (df_gestora['Patrimonio_Mercado'] / total_patrimonio * 100).apply(lambda x: f"{x:.1f}%".replace('.', ','))
    df_gestora['Valor_Texto'] = df_gestora['Patrimonio_Mercado'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))

    # PAINEL 1
    fig1 = make_subplots(rows=1, cols=2, specs=[[{'type':'xy'}, {'type':'domain'}]], subplot_titles=['<b>Alocação por Ativo</b>', '<b>Papel vs Tijolo</b>'], column_widths=[0.6, 0.4], horizontal_spacing=0.15)
    fig1.add_trace(go.Bar(y=df_ativo['Ticker'], x=df_ativo['Patrimonio_Mercado'], orientation='h', text=df_ativo['Percentual_Texto'], textposition='outside', marker_color='#118DFF', customdata=df_ativo['Valor_Texto'], hovertemplate='<b>Ativo:</b> %{y}<br><b>Exposição:</b> %{customdata}<br><b>Peso:</b> %{text}<extra></extra>'), row=1, col=1)
    fig1.add_trace(go.Pie(labels=df_alocacao['Classificacao'], values=df_alocacao['Patrimonio_Mercado'], hole=0.5, marker=dict(colors=['#5D6D7E', '#5DADE2']), textinfo='label+percent', textposition='auto'), row=1, col=2)
    fig1.update_layout(height=max(500, len(df_ativo) * 25), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
    fig1.update_xaxes(tickprefix="R$ ", gridcolor='rgba(200,200,200,0.2)', row=1, col=1)
    
    st.plotly_chart(fig1, use_container_width=True)
    
    # PAINEL 2
    st.divider()
    fig2 = make_subplots(rows=1, cols=2, specs=[[{'type':'domain'}, {'type':'xy'}]], subplot_titles=['<b>Por Segmento</b>', '<b>Risco por Gestora</b>'], column_widths=[0.4, 0.6], horizontal_spacing=0.15)
    fig2.add_trace(go.Pie(labels=df_alocacao['Seguimento'], values=df_alocacao['Patrimonio_Mercado'], hole=0.5, marker=dict(colors=px.colors.qualitative.Set2), textinfo='label+percent', textposition='auto'), row=1, col=1)
    fig2.add_trace(go.Bar(y=df_gestora['Gestora'], x=df_gestora['Patrimonio_Mercado'], orientation='h', text=df_gestora['Percentual_Texto'], textposition='outside', marker_color='#2C3E50', customdata=df_gestora['Valor_Texto'], hovertemplate='<b>Gestora:</b> %{y}<br><b>Exposição:</b> %{customdata}<br><b>Peso:</b> %{text}<extra></extra>'), row=1, col=2)
    fig2.update_layout(height=max(400, len(df_gestora) * 30), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
    fig2.update_xaxes(tickprefix="R$ ", gridcolor='rgba(200,200,200,0.2)', row=1, col=2)
    
    st.plotly_chart(fig2, use_container_width=True)

with aba2:
    st.header("GPS de Rebalanceamento")
    
    df_tabela = pd.merge(df_alocacao, df_ultimo_prov, on='Ticker', how='left').fillna(0)
    df_tabela['Variacao_Pct'] = ((df_tabela['Preco_Atual'] / df_tabela['Preco_Medio']) - 1) * 100
    df_tabela = pd.merge(df_tabela, df_meta_seg, on='Seguimento', how='left').fillna(0)
    
    df_tabela['Qtd_Ativos_No_Seg'] = df_tabela.groupby('Seguimento')['Ticker'].transform('count')
    df_tabela['Meta_Do_Ativo'] = df_tabela['Meta'] / df_tabela['Qtd_Ativos_No_Seg']
    df_tabela['Valor_Alvo_RS'] = df_tabela['Meta_Do_Ativo'] * total_patrimonio
    df_tabela['Aporte_Necessario'] = df_tabela['Valor_Alvo_RS'] - df_tabela['Patrimonio_Mercado']
    df_tabela = df_tabela.sort_values(by='Aporte_Necessario', ascending=False)
    
    def f_rs(v): return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    df_tabela['Acao_Str'] = df_tabela['Aporte_Necessario'].apply(lambda x: f"Comprar {f_rs(abs(x))}" if x > 0 else f"Excesso {f_rs(abs(x))}")
    df_tabela['Variacao_Str'] = df_tabela['Variacao_Pct'].apply(lambda x: f"+{abs(x):.2f}%".replace('.', ',') if x >= 0 else f"-{abs(x):.2f}%".replace('.', ','))
    
    cor_padrao, cor_vd, cor_vm = '#2C3E50', '#2E8B57', '#E74C3C'
    cores_var = [cor_vd if v >= 0 else cor_vm for v in df_tabela['Variacao_Pct']]
    cores_acao = [cor_vd if v > 0 else cor_vm for v in df_tabela['Aporte_Necessario']]
    
    matriz_cores = [[cor_padrao]*len(df_tabela), [cor_padrao]*len(df_tabela), [cor_padrao]*len(df_tabela), [cor_padrao]*len(df_tabela), [cor_padrao]*len(df_tabela), [cor_padrao]*len(df_tabela), cores_acao, cores_var, [cor_padrao]*len(df_tabela)]
    
    fig_tab = go.Figure(data=[go.Table(
        columnwidth=[60, 50, 90, 90, 90, 90, 130, 80, 90],
        header=dict(values=['<b>Ativo</b>', '<b>Cotas</b>', '<b>Preço Médio</b>', '<b>Cotação Atual</b>', '<b>Saldo Atual</b>', '<b>Saldo Ideal</b>', '<b>Ordem (Meta)</b>', '<b>Variação (%)</b>', '<b>Últ. Provento</b>'], fill_color='#2C3E50', align='center', font=dict(color='white', size=13)),
        cells=dict(
            values=[df_tabela['Ticker'], df_tabela['Quantidade'], df_tabela['Preco_Medio'].apply(f_rs), df_tabela['Preco_Atual'].apply(f_rs), df_tabela['Patrimonio_Mercado'].apply(f_rs), df_tabela['Valor_Alvo_RS'].apply(f_rs), df_tabela['Acao_Str'], df_tabela['Variacao_Str'], df_tabela['Ultimo_Provento'].apply(lambda x: f_rs(x) if x>0 else "-")],
            fill_color=[['#F5F7FA', 'white'] * (len(df_tabela) // 2 + 1)],
            align=['center', 'center', 'right', 'right', 'right', 'right', 'center', 'center', 'right'],
            font=dict(color=matriz_cores, size=12), height=30
        )
    )])
    fig_tab.update_layout(margin=dict(t=10, b=0, l=0, r=0), height=min(800, 100 + (len(df_tabela) * 30)))
    
    st.plotly_chart(fig_tab, use_container_width=True)
