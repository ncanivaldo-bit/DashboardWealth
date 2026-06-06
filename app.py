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
# CONFIGURAÇÃO DE TELA E IDENTIDADE VISUAL
# ==============================================================================
st.set_page_config(page_title="PREVPRIV", page_icon="📊", layout="wide")
st.title("PREVPRIV")
st.markdown("<p style='margin-bottom: -10px; font-size: 16px;'>🎯 <b>Missão:</b> Do vácuo absoluto a renda passiva sustentável</p>", unsafe_allow_html=True)

# ==============================================================================
# CONEXÃO DIRETA COM O GOOGLE DRIVE
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
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_excel(fh, engine='openpyxl', sheet_name=sheet_name)

# ==============================================================================
# MOTOR DE CÁLCULO PREVPRIV - EVOLUÇÃO DO VALOR INVESTIDO
# ==============================================================================
df_portfolio_mensal = pd.DataFrame()
total_investido_kpi = 0.0

try:
    ID_MOV = '1JJPFCTWORXmTBJB3KdtKK-LRf-3A8XIAESWRiOX-G4E' # Movimentação
    
    # 1. Carga bruta e limpeza de cabeçalhos
    df_mov = download_excel_from_drive(ID_MOV, sheet_name=0)
    df_mov.columns = df_mov.columns.astype(str).str.strip()
    
    # 2. Extração e conversão limpa de Tickers
    df_mov['Ticker_Base'] = df_mov['Produto'].astype(str).str.split(' - ').str[0].str.strip()
    conversao_tickers = {"MALL11": "PMLL11", "CVBI11": "PCIP11"}
    df_mov['Ticker_Base'] = df_mov['Ticker_Base'].replace(conversao_tickers)
    
    # 3. Tipagem e tratamento numérico
    df_mov['Quantidade_Num'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor_Operacao_Num'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)
    df_mov['Data_Datetime'] = pd.to_datetime(df_mov['Data'], format='%d/%m/%Y', errors='coerce')
    
    # 4. Isolar eventos de modificação de patrimônio (Bolsa + CDB)
    df_trades = df_mov[df_mov['Movimentação'].isin(['Transferência - Liquidação', 'COMPRA / VENDA'])].sort_values('Data_Datetime').copy()
    
    # 5. Algoritmo Cronológico de Fluxo de Caixa Investido
    carteira = {}
    historico_financeiro = []
    
    for _, row in df_trades.iterrows():
        ticker = row['Ticker_Base']
        data = row['Data_Datetime']
        tipo = str(row['Entrada/Saída']).strip()
        qtd = float(row['Quantidade_Num'])
        valor = float(row['Valor_Operacao_Num'])
        
        if pd.isna(data):
            continue
            
        if ticker not in carteira:
            carteira[ticker] = {'quantidade': 0.0, 'custo_total': 0.0, 'preco_medio': 0.0}
            
        if tipo == 'Credito':
            carteira[ticker]['quantidade'] += qtd
            carteira[ticker]['custo_total'] += valor
        elif tipo == 'Debito':
            if carteira[ticker]['quantidade'] > 0:
                qtd_venda = min(qtd, carteira[ticker]['quantidade'])
                carteira[ticker]['custo_total'] -= qtd_venda * carteira[ticker]['preco_medio']
            carteira[ticker]['quantidade'] -= qtd
            
        # Recalculo do preço médio dinâmico
        if carteira[ticker]['quantidade'] > 0:
            carteira[ticker]['preco_medio'] = carteira[ticker]['custo_total'] / carteira[ticker]['quantidade']
        else:
            carteira[ticker]['quantidade'] = 0.0
            carteira[ticker]['custo_total'] = 0.0
            carteira[ticker]['preco_medio'] = 0.0
            
        # Guarda o total do bolso investido acumulado neste exato segundo da história
        historico_financeiro.append({
            'Data': data,
            'Custo_Acumulado': sum(d['custo_total'] for d in carteira.values())
        })
        
    # 6. Agrupamento mensal consolidado para o gráfico
    df_hist = pd.DataFrame(historico_financeiro)
    if not df_hist.empty:
        df_hist['AnoMes'] = df_hist['Data'].dt.to_period('M')
        df_portfolio_mensal = df_hist.groupby('AnoMes').last().reset_index()
        df_portfolio_mensal['Mês_Exibição'] = df_portfolio_mensal['AnoMes'].dt.strftime('%m/%Y')
        
        # Captura o valor final atualizado para alimentar o Cartão de KPI
        total_investido_kpi = float(df_portfolio_mensal.iloc[-1]['Custo_Acumulado'])

except Exception as e:
    st.error(f"❌ Erro no processamento do gráfico de evolução: {e}")

# ==============================================================================
# RENDERIZAÇÃO DA INTERFACE VISUAL
# ==============================================================================
st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Outras Análises"])

with aba_resumo:
    # Formatação padrão Real Brasileiro para o Card do Investido
    str_investido = f"R$ {total_investido_kpi:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 140px;">
                <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Patrimônio Atual</span>
                <div style="color: #2C3E50; font-size: 24px; font-weight: 700; margin-top: 5px; margin-bottom: 5px;">R$ 0,00</div>
                <div style="border-top: 1px solid #E6E8EA; padding-top: 5px; font-size: 12px; color: #7F8C8D;">
                    Total Investido: <span style="color: #118DFF; font-weight:bold;">{str_investido}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 140px;">
                <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Lucro Total</span>
                <div style="color: #2E8B57; font-size: 24px; font-weight: 700; margin-top: 5px; margin-bottom: 5px;">R$ 0,00</div>
                <div style="border-top: 1px solid #E6E8EA; padding-top: 5px; font-size: 11px; color: #7F8C8D; display: flex; justify-content: space-between;">
                    <span>Ganho Cap: <strong style="color:#2E8B57;">R$ 0,00</strong></span>
                    <span>Proventos: <strong style="color:#2E8B57;">R$ 0,00</strong></span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 140px;">
                <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Último Provento Mensal</span>
                <div style="color: #2E8B57; font-size: 24px; font-weight: 700; margin-top: 5px; margin-bottom: 5px;">R$ 0,00</div>
                <div style="border-top: 1px solid #E6E8EA; padding-top: 5px; font-size: 12px; color: #7F8C8D;">
                    Mês Ref: <span style="color: #34495E; font-weight:bold;">-</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 140px;">
                <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Variação e Rentabilidade</span>
                <div style="color: #2E8B57; font-size: 24px; font-weight: 700; margin-top: 5px; margin-bottom: 5px;">R$ 0,00</div>
                <div style="border-top: 1px solid #E6E8EA; padding-top: 5px; font-size: 12px; color: #7F8C8D;">
                    Rentabilidade: <span style="color: #2E8B57; font-weight:bold;">0.00%</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)

    # GRÁFICO INTERATIVO DE EVOLUÇÃO DO VALOR INVESTIDO
    if not df_portfolio_mensal.empty:
        fig_evolucao = go.Figure()
        fig_evolucao.add_trace(go.Scatter(
            x=df_portfolio_mensal['Mês_Exibição'], 
            y=df_portfolio_mensal['Custo_Acumulado'],
            mode='lines+markers',
            name='Total Investido (Bolso)',
            line=dict(color='#118DFF', width=3),
            marker=dict(size=6),
            hovertemplate='<b>Mês:</b> %{x}<br><b>Investido:</b> R$ %{y:,.2f}<extra></extra>'
        ))
        
        fig_evolucao.update_layout(
            title="<b>Evolução Histórica do Capital Investido Acumulado</b>",
            title_font=dict(size=15, color='#2C3E50'),
            margin=dict(l=50, r=30, t=50, b=40),
            height=400,
            hovermode='x unified',
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            yaxis=dict(gridcolor='rgba(230,235,240,0.6)', tickprefix="R$ "),
            xaxis=dict(gridcolor='rgba(230,235,240,0.3)', type='category'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_evolucao, use_container_width=True)
    else:
        st.info("Aguardando dados históricos para plotagem.")

with aba_alocacao:
    st.info("⚙️ Aba de alocação estruturada.")
