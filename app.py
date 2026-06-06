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

# Injeção CSS apenas para esconder os elementos internos da plataforma
st.markdown("""
    <style>
        /* Esconde o ícone do GitHub no canto superior direito */
        .viewerBadge_link__1S137 { display: none !important; }
        a.viewerBadge_link__1S137 { display: none !important; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        header { visibility: hidden; }
        .stDeployButton { display: none !important; }
    </style>
""", unsafe_allow_html=True)

st.title("PREVPRIV")
st.markdown("<p style='margin-bottom: -10px; font-size: 16px;'>🎯 <b>Missão:</b> Do vácuo absoluto a renda passiva sustentável</p>", unsafe_allow_html=True)

# ==============================================================================
# CONEXÃO DIRETA COM O GOOGLE DRIVE (Com proteção de Retry)
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
            while done is False:
                status, done = downloader.next_chunk()
            fh.seek(0)
            return pd.read_excel(fh, engine='openpyxl', sheet_name=sheet_name)
        except Exception as e:
            if tentativa == 2:
                raise e
            time.sleep(1)

# ==============================================================================
# MOTOR MATRICIAL - PROCESSAMENTO DOS DADOS CACHEADO
# ==============================================================================
@st.cache_data(ttl=600)
def carregar_e_processar_dados_carteira():
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

    # 1. Isolamento e Cálculo Cronológico de Custódia
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
            
    # 2. Extração de Dividendos Totais e Cálculo do Último Mês Pago
    termos_proventos = ['Dividendo', 'JCP', 'Rendimento', 'Provento']
    df_proventos = df_mov[df_mov['Movimentação'].isin(termos_proventos)].copy()
    total_dividendos_historico = float(df_proventos['Valor da Operação'].sum())
    
    ultimo_provento_valor = 0.0
    ultimo_provento_mes_ano = "-"
    if not df_proventos.empty and not df_proventos['Data_Datetime'].isna().all():
        df_proventos['AnoMes'] = df_proventos['Data_Datetime'].dt.to_period('M')
        proventos_por_mes = df_proventos.groupby('AnoMes')['Valor da Operação'].sum().sort_index()
        if not proventos_por_mes.empty:
            ultimo_provento_valor = float(proventos_por_mes.iloc[-1])
            ultimo_provento_mes_ano = proventos_por_mes.index[-1].strftime('%m/%Y')

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
        df_consolidado['Tipo'] = df_consolidado['Tipo'].fillna('OUTROS')
        
        df_custodia_atual = df_consolidado[df_consolidado['Chave_Merge'] == mes_atual_chave].copy()
        df_custodia_atual = df_custodia_atual[df_custodia_atual['Quantidade'] > 0]
        
        return df_consolidado, df_custodia_atual, total_dividendos_historico, ultimo_provento_valor, ultimo_provento_mes_ano
    return pd.DataFrame(), pd.DataFrame(), 0.0, 0.0, "-"

# Execução do Motor de Inteligência
df_consolidado, df_custodia_atual, total_dividendos, ult_provento_val, ult_provento_mes = carregar_e_processar_dados_carteira()

# Inicialização das variáveis matemáticas dos cards
total_investido_kpi = 0.0
patrimonio_mercado_kpi = 0.0
ganho_capital_kpi = 0.0
lucro_total_kpi = 0.0
variacao_carteira_pct = 0.0
rentabilidade_total_pct = 0.0

if not df_custodia_atual.empty:
    total_investido_kpi = float(df_custodia_atual['Custo_Total'].sum())
    patrimonio_mercado_kpi = float(df_custodia_atual['Patrimonio_Mercado_Ativo'].sum())
    ganho_capital_kpi = patrimonio_mercado_kpi - total_investido_kpi
    lucro_total_kpi = ganho_capital_kpi + total_dividendos
    
    if total_investido_kpi > 0:
        variacao_carteira_pct = (patrimonio_mercado_kpi / total_investido_kpi - 1) * 100
        rentabilidade_total_pct = ((patrimonio_mercado_kpi + total_dividendos) / total_investido_kpi - 1) * 100

# ==============================================================================
# RENDERIZAÇÃO DA INTERFACE VISUAL
# ==============================================================================
st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Outras Análises"])

with aba_resumo:
    def formatar_br(v):
        prefixo = "-" if v < 0 else ""
        return f"{prefixo}R$ {abs(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        
    def formatar_pct(v):
        prefixo = "+" if v > 0 else ""
        return f"{prefixo}{v:.2f}%".replace('.', ',')

    color_lucro = "#2E8B57" if lucro_total_kpi >= 0 else "#CD5C5C"
    color_ganho = "#2E8B57" if ganho_capital_kpi >= 0 else "#CD5C5C"
    color_var = "#2E8B57" if variacao_carteira_pct >= 0 else "#CD5C5C"
    color_rent = "#2E8B57" if rentabilidade_total_pct >= 0 else "#CD5C5C"
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 140px;">
                <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Patrimônio Atual</span>
                <div style="color: #2C3E50; font-size: 24px; font-weight: 700; margin-top: 5px; margin-bottom: 5px;">{formatar_br(patrimonio_mercado_kpi)}</div>
                <div style="border-top: 1px solid #E6E8EA; padding-top: 5px; font-size: 11px; color: #7F8C8D; display: flex; justify-content: space-between; align-items: center;">
                    <span>Total Investido: <strong style="color: #118DFF;">{formatar_br(total_investido_kpi)}</strong></span>
                    <span>Var: <strong style="color: {color_var}; font-size: 12px;">{formatar_pct(variacao_carteira_pct)}</strong></span>
                </div>
