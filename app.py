import streamlit st
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

# 🎯 INJEÇÃO CSS COMPLETA: ZERANDO O VÁCUO NATIVO ENTRE AS ABAS E OS GRÁFICOS
st.markdown("""
    <style>
        /* 1. Remove a barra de cabeçalho transparente nativa */
        [data-testid="stHeader"] { display: none !important; visibility: hidden; }
        
        /* 2. Zera o recuo superior e força o preenchimento total da largura da tela */
        [data-testid="stMainBlockContainer"] {
            padding-top: 0.8rem !important;
            padding-bottom: 0.8rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 100% !important;
        }
        
        /* 3. Puxa a linha das abas para cima, colando no título PREVPRIV */
        [data-testid="stTabs"] {
            margin-top: -25px !important;
            margin-bottom: 0px !important;
        }
        
        /* 🎯 Zera o espaço invisível que o Streamlit cria embaixo da linha das abas globalmente */
        [data-testid="stTabPanel"] {
            padding-top: 0rem !important;
            margin-top: -20px !important;
        }
        
        /* 4. Cola o título "PREVPRIV" no topo absoluto do navegador */
        h1 { 
            margin-top: -25px !important; 
            margin-bottom: 5px !important; 
            font-size: 26px !important; 
            font-weight: 700 !important;
        }
        
        /* 5. Oculta os menus e botões da plataforma */
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        header { visibility: hidden; }
        .stDeployButton { display: none !important; }
        
        /* 6. Esconde o ícone do GitHub no canto superior direito */
        .viewerBadge_link__1S137 { display: none !important; }
        a.viewerBadge_link__1S137 { display: none !important; }
    </style>
""", unsafe_allow_html=True)

# Título direto no topo
st.title("PREVPRIV")

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
    df_inf['Ticker'] = df_inf['Ticker'].replace(conversao_tickers)
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
        df_consolidado = pd.merge(df_consolidado, df_inf, on='Ticker', how='left')
        
        mes_atual_chave = pd.Timestamp.now().strftime('%Y-%m')
        df_consolidado.loc[df_consolidado['Chave_Merge'] == mes_atual_chave, 'Preco_Mercado'] = df_consolidado['Preco_Atual']
        
        df_consolidado['Preco_Mercado'] = df_consolidado['Preco_Mercado'].fillna(df_consolidado['Custo_Total'] / df_consolidado['Quantidade']).fillna(0)
        df_consolidado['Patrimonio_Mercado_Ativo'] = df_consolidado['Quantidade'] * df_consolidado['Preco_Mercado']
        
        df_custodia_atual = df_consolidado[df_consolidado['Chave_Merge'] == mes_atual_chave].copy()
        df_custodia_atual = df_custodia_atual[df_custodia_atual['Quantidade'] > 0]
        
        return df_consolidado, df_custodia_atual, total_dividendos_historico, ultimo_provento_valor, ultimo_provento_mes_ano
    return pd.DataFrame(), pd.DataFrame(), 0.0, 0.0, "-"

# Execução do Motor de Raciocínio
df_consolidado, df_custodia_atual, total_dividendos, ult_provento_val, ult_provento_mes = carregar_e_processar_dados_carteira()

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
aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Alocação"])

# ------------------------------------------------------------------------------
# 📝 ABA 1: RESUMO (AJUSTADA: AGORA SOBE COLADA NA LINHA DAS ABAS EM 7PX)
# ------------------------------------------------------------------------------
with aba_resumo:
    # 🎯 NOVO: Puxa o bloco de KPIs e gráficos para cima na aba Resumo
    st.markdown("<div style='margin-top: -18px;'></div>", unsafe_allow_html=True)

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
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 10px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 110px; max-height: 110px;">
                <span style="color: #5D6D7E; font-size: 14px; font-weight: bold; text-transform: uppercase;">Patrimônio Atual</span>
                <div style="color: #2C3E50; font-size: 27px; font-weight: 700; margin-top: 1px; margin-bottom: 1px; letter-spacing: -0.5px;">{formatar_br(patrimonio_mercado_kpi)}</div>
                <div style="border-top: 1px solid #E6E8EA; padding-top: 4px; font-size: 13px; color: #7F8C8D; display: flex; justify-content: space-between;">
                    <div>
                        <span style="font-size: 12px; color: #7F8C8D; text-transform: uppercase;">Investido:</span>
                        <strong style="color: #118DFF;">{formatar_br(total_investido_kpi)}</strong>
                    </div>
                    <div style="text-align: right;">
                        <span style="font-size: 12px; color: #7F8C8D; text-transform: uppercase;">Var:</span>
                        <strong style="color: {color_var};">{formatar_pct(variacao_carteira_pct)}</strong>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.markdown(f"""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 10px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 110px; max-height: 110px;">
                <span style="color: #5D6D7E; font-size: 14px; font-weight: bold; text-transform: uppercase;">Lucro total</span>
                <div style="color: #2C3E50; font-size: 27px; font-weight: 700; margin-top: 1px; margin-bottom: 1px; letter-spacing: -0.5px;">{formatar_br(lucro_total_kpi)}</div>
                <div style="border-top: 1px solid #E6E8EA; padding-top: 4px; font-size: 13px; color: #7F8C8D; display: flex; justify-content: space-between;">
                    <div>
                        <span style="font-size: 12px; color: #7F8C8D; text-transform: uppercase;">G. Cap:</span>
                        <strong style="color: {color_ganho};">{formatar_br(ganho_capital_kpi)}</strong>
                    </div>
                    <div style="text-align: right;">
                        <span style="font-size: 12px; color: #7F8C8D; text-transform: uppercase;">Prov:</span>
                        <strong style="color: #2E8B57;">{formatar_br(total_dividendos)}</strong>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    with col3:
        st.markdown(f"""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 10px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 110px; max-height: 110px;">
                <span style="color: #5D6D7E; font-size: 14px; font-weight: bold; text-transform: uppercase;">Último Provento Mensal</span>
                <div style="color: #2E8B57; font-size: 27px; font-weight: 700; margin-top: 1px; margin-bottom: 1px; letter-spacing: -0.5px;">{formatar_br(ult_provento_val)}</div>
                <div style="border-top: 1px solid #E6E8EA; padding-top: 4px; font-size: 13px; color: #7F8C8D; display: flex; justify-content: space-between;">
                    <div>
                        <span style="font-size: 12px; color: #7F8C8D; text-transform: uppercase;">Mês de Ref:</span>
                        <strong style="color: #34495E;">{ult_provento_mes}</strong>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    with col4:
        st.markdown(f"""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 10px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 110px; max-height: 110px;">
                <span style="color: #5D6D7E; font-size: 14px; font-weight: bold; text-transform: uppercase;">Rentabilidade Total</span>
                <div style="color: {color_rent}; font-size: 27px; font-weight: 700; margin-top: 1px; margin-bottom: 1px; letter-spacing: -0.5px;">{formatar_pct(rentabilidade_total_pct)}</div>
                <div style="border-top: 1px solid #E6E8EA; padding-top: 4px; font-size: 13px; color: #7F8C8D; display: flex; justify-content: space-between;">
                    <div>
                        <span style="font-size: 12px; color: #7F8C8D; text-transform: uppercase;">Resultado Com:</span>
                        <strong style="color: {color_ganho};">{formatar_br(ganho_capital_kpi)}</strong>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

    # Margem inversa puxa o bloco de gráficos para cima comprimindo o vão com os cartões
    st.markdown('<div style="margin-top: -24px;">', unsafe_allow_html=True)
    col_bloco_esquerdo, col_bloco_direito = st.columns([6, 4])

    with col_bloco_esquerdo:
        with st.container(border=True):
            st.markdown("<h3 style='margin:0; padding-top:4px; color:#2C3E50; font-size:19px; font-weight:600;'>Evolução do Patrimônio</h3>", unsafe_allow_html=True)
            df_totais_mensais = df_consolidado.groupby('Mes_Ano').agg({'Custo_Total':'sum', 'Patrimonio_Mercado_Ativo':'sum'}).reset_index()
            df_totais_mensais['Mês_Exibição'] = df_totais_mensais['Mes_Ano'].dt.strftime('%m/%Y')
            
            fig_linhas = go.Figure()
            fig_linhas.add_trace(go.Scatter(x=df_totais_mensais['Mês_Exibição'], y=df_totais_mensais['Patrimonio_Mercado_Ativo'], mode='lines+markers', name='Patrimônio Atual', line=dict(color='#1fbc74', width=3), marker=dict(size=6), fill='tozeroy', fillcolor='rgba(31, 188, 116, 0.06)'))
            fig_linhas.add_trace(go.Scatter(x=df_totais_mensais['Mês_Exibição'], y=df_totais_mensais['Custo_Total'], mode='lines', name='Total Investido', line=dict(color='#118DFF', width=2, dash='dot')))
            fig_linhas.update_layout(margin=dict(l=45, r=10, t=25, b=10), height=260, hovermode='x unified', plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis=dict(gridcolor='rgba(230,235,240,0.6)', tickprefix="R$ ", tickformat="~s", nticks=6), xaxis=dict(gridcolor='rgba(0,0,0,0)', type='category'), legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5))
            st.plotly_chart(fig_linhas, use_container_width=True)

    with col_bloco_direito:
        with st.container(border=True):
            st.markdown("<h3 style='margin:0; padding-top:4px; color:#2C3E50; font-size:19px; font-weight:600;'>Alocação Ativos</h3>", unsafe_allow_html=True)
            df_rosca = df_custodia_atual.sort_values(by='Patrimonio_Mercado_Ativo', ascending=False).copy()
            fig_p = go.Figure(go.Pie(labels=df_rosca['Ticker'], values=df_rosca['Patrimonio_Mercado_Ativo'], hole=0.55, textinfo='none'))
            fig_p.update_layout(margin=dict(l=0, r=0, t=10, b=10), height=260, paper_bgcolor='rgba(0,0,0,0)', showlegend=True, legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=0.68, font=dict(size=10)))
            st.plotly_chart(fig_p, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# ⚙️ ABA 2: CENTRAL DE ALOCAÇÃO
# ------------------------------------------------------------------------------
with aba_alocacao:
    st.markdown("<div style='margin-top: -18px;'></div>", unsafe_allow_html=True)
    
    if not df_custodia_atual.empty:
        df_analise = df_custodia_atual.copy()
        
        if 'Classificacao' not in df_analise.columns: df_analise['Classificacao'] = 'NÃO INFORMADO'
        if 'Seguimento' not in df_analise.columns: df_analise['Seguimento'] = 'NÃO INFORMADO'
        if 'Gestora' not in df_analise.columns: df_analise['Gestora'] = 'NÃO INFORMADO'
            
        df_analise['Classificacao'] = df_analise['Classificacao'].fillna('NÃO INFORMADO').astype(str).str.upper()
        df_analise['Seguimento'] = df_analise['Seguimento'].fillna('NÃO INFORMADO').astype(str).str.upper()
        df_analise['Gestora'] = df_analise['Gestora'].fillna('NÃO INFORMADO').astype(str).str.upper()

        col_super_esq, col_super_dir = st.columns([4, 6])
        
        # ==============================================================================
        # COLUNA DA ESQUERDA (40%): RANKING DE ATIVOS (height=540px)
        # ==============================================================================
        with col_super_esq:
            with st.container(border=True):
                st.markdown("<h4 style='margin:0; padding-bottom:4px; color:#2C3E50; font-size:15px; font-weight:600; text-transform:uppercase;'>1. Exposição por Ativo (Ranking Geral)</h4>", unsafe_allow_html=True)
                df_ativos_sorted = df_analise.sort_values(by='Patrimonio_Mercado_Ativo', ascending=True)
                
                fig_bar_ativos = go.Figure(go.Bar(
                    x=df_ativos_sorted['Patrimonio_Mercado_Ativo'], y=df_ativos_sorted['Ticker'],
                    orientation='h', marker_color='#1fbc74',
                    hovertemplate='<b>Ativo:</b> %{y}<br>
