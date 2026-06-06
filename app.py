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
# MOTOR MATRICIAL - INVESTIDO VS MERCADO HISTÓRICO
# ==============================================================================
df_portfolio_mensal = pd.DataFrame()
total_investido_kpi = 0.0
patrimonio_mercado_kpi = 0.0

try:
    ID_UNIFICADO = '1d4AMHX5El8JOEbgwpBVm513-ImJPFiGXrRG_2VoObTo'
    
    # 1. Downloads das abas do ecossistema unificado
    df_mov = download_excel_from_drive(ID_UNIFICADO, sheet_name='Movimentacao')
    df_inf = download_excel_from_drive(ID_UNIFICADO, sheet_name='Inf_Ativos')
    df_precos_historicos = download_excel_from_drive(ID_UNIFICADO, sheet_name='Hist_Precos')
    
    df_mov.columns = df_mov.columns.astype(str).str.strip()
    df_inf.columns = df_inf.columns.astype(str).str.strip()
    df_precos_historicos.columns = df_precos_historicos.columns.astype(str).str.strip()
    
    # 2. Padronização e Limpeza de chaves de cruzamento
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

    # 3. Processamento Cronológico Passo a Passo das Cotas e Custos
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
            
        # Grava a foto da carteira após este trade para cada ativo existente
        for tk, dados in carteira.items():
            historico_detalhado.append({
                'Data': data,
                'Ticker': tk,
                'Quantidade': dados['quantidade'],
                'Custo_Total': dados['custo_total']
            })
            
    # 4. Construção da Malha Mensal Resampled
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
        
        # 5. Cruzamento Matricial com o Histórico de Preços da B3
        df_consolidado = pd.merge(df_mensal_ativos, df_precos_historicos, on=['Chave_Merge', 'Ticker'], how='left')
        
        # Injeta o preço em tempo real da Inf_Ativos no mês corrente (Junho 2026)
        df_consolidado = pd.merge(df_consolidado, df_inf[['Ticker', 'Preco_Atual']], on='Ticker', how='left')
        mes_atual_chave = pd.Timestamp.now().strftime('%Y-%m')
        df_consolidado.loc[df_consolidado['Chave_Merge'] == mes_atual_chave, 'Preco_Mercado'] = df_consolidado['Preco_Atual']
        
        # Se algum ativo antigo não tiver preço no Yahoo em meses remotos, assume o custo amortizado como margem de segurança
        df_consolidado['Preco_Mercado'] = df_consolidado['Preco_Mercado'].fillna(df_consolidado['Custo_Total'] / df_consolidado['Quantidade']).fillna(0)
        
        # Calculation of point-in-time equity value
        df_consolidado['Patrimonio_Mercado_Ativo'] = df_consolidado['Quantidade'] * df_consolidado['Preco_Mercado']
        
        # Consolidação Final Agrupada por Mês
        df_portfolio_mensal = df_consolidado.groupby('Mes_Ano').agg({
            'Custo_Total': 'sum',
            'Patrimonio_Mercado_Ativo': 'sum'
        }).reset_index().sort_values('Mes_Ano')
        
        df_portfolio_mensal['Mês_Exibição'] = df_portfolio_mensal['Mes_Ano'].dt.strftime('%m/%Y')
        
        # Extração das variáveis finais de fechamento para alimentar os Cards
        total_investido_kpi = float(df_portfolio_mensal.iloc[-1]['Custo_Total'])
        patrimonio_mercado_kpi = float(df_portfolio_mensal.iloc[-1]['Patrimonio_Mercado_Ativo'])

except Exception as e:
    st.error(f"❌ Erro no cruzamento matricial de dados: {e}")

# ==============================================================================
# RENDERIZAÇÃO DA INTERFACE VISUAL
# ==============================================================================
st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Outras Análises"])

with aba_resumo:
    # Formatação Padrão BR
    def formatar_br(v): return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    str_investido = formatar_br(total_investido_kpi)
    str_patrimonio = formatar_br(patrimonio_mercado_kpi)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 140px;">
                <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Patrimônio Atual</span>
                <div style="color: #2C3E50; font-size: 24px; font-weight: 700; margin-top: 5px; margin-bottom: 5px;">{str_patrimonio}</div>
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

    # 📈 IMPRESSÃO DO GRÁFICO DUPLO DE EVOLUÇÃO PATRIMONIAL (MERCADO VS INVESTIDO)
    if not df_portfolio_mensal.empty:
        fig_evolucao = go.Figure()
        
        # Linha 1: Valor de Mercado (Verde)
        fig_evolucao.add_trace(go.Scatter(
            x=df_portfolio_mensal['Mês_Exibição'], 
            y=df_portfolio_mensal['Patrimonio_Mercado_Ativo'],
            mode='lines+markers',
            name='Valor de Mercado Real B3',
            line=dict(color='#2E8B57', width=3),
            marker=dict(size=5),
            hovertemplate='<b>Mês:</b> %{x}<br><b>Mercado:</b> R$ %{y:,.2f}<extra></extra>'
        ))
        
        # Linha 2: Total Investido (Azul Tracejado)
        fig_evolucao.add_trace(go.Scatter(
            x=df_portfolio_mensal['Mês_Exibição'], 
            y=df_portfolio_mensal['Custo_Total'],
            mode='lines+markers',
            name='Total Investido (Bolso)',
            line=dict(color='#118DFF', width=2, dash='dot'),
            marker=dict(size=5),
            hovertemplate='<b>Mês:</b> %{x}<br><b>Investido:</b> R$ %{y:,.2f}<extra></extra>'
        ))
        
        fig_evolucao.update_layout(
            title="<b>Evolução Patrimonial: Investido vs Mercado Real B3</b>",
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
        st.info("ℹ️ Aguardando dados das transações e fechamentos para plotagem do gráfico completo.")

with aba_alocacao:
    st.info("⚙️ Aba de alocação estruturada.")
