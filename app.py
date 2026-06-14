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

# ==============================================================================
# 1. CONFIGURAÇÃO DE TELA E IDENTIDADE VISUAL
# ==============================================================================
st.set_page_config(page_title="PREVPRIV", page_icon="📊", layout="wide")

st.markdown("""
    <style>
        /* Trava de zoom acidental no telemóvel */
        * { touch-action: manipulation; }
        
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
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        header { visibility: hidden; }
        .stDeployButton { display: none !important; }
    </style>
""", unsafe_allow_html=True)

st.title("PREVPRIV")

# ==============================================================================
# 2. CONEXÃO DIRETA COM O GOOGLE DRIVE
# ==============================================================================
@st.cache_resource
def get_drive_service():
    if "GCP_SERVICE_ACCOUNT" in st.secrets:
        key_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        creds = service_account.Credentials.from_service_account_info(
            key_dict, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        return build('drive', 'v3', credentials=creds)
    else:
        st.error("🚨 Credenciais GCP_SERVICE_ACCOUNT não encontradas no st.secrets.")
        st.stop()

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
# 3. MOTOR DE RACIOCÍNIO - MÓDULOS DE TRANSFORMAÇÃO (ETL)
# ==============================================================================
def calcular_historico_posicoes(df_trades):
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
        
    return pd.DataFrame(historico_detalhado)

def extrair_kpis_proventos(df_mov):
    termos_proventos = ['Dividendo', 'JCP', 'Rendimento', 'Provento']
    df_proventos = df_mov[df_mov['Movimentação'].isin(termos_proventos)].copy()
    
    total_dividendos_historico = float(df_proventos['Valor da Operação'].sum()) if not df_proventos.empty else 0.0
    ultimo_provento_valor = 0.0
    ultimo_provento_mes_ano = "-"
    
    if not df_proventos.empty and not df_proventos['Data_Datetime'].isna().all():
        df_proventos['AnoMes'] = df_proventos['Data_Datetime'].dt.to_period('M')
        proventos_por_mes = df_proventos.groupby('AnoMes')['Valor da Operação'].sum().sort_index()
        if not proventos_por_mes.empty:
            ultimo_provento_valor = float(proventos_por_mes.iloc[-1])
            ultimo_provento_mes_ano = proventos_por_mes.index[-1].strftime('%m/%Y')
            
    return total_dividendos_historico, ultimo_provento_valor, ultimo_provento_mes_ano

# ==============================================================================
# 4. FUNÇÕES GLOBAIS DE FORMATAÇÃO
# ==============================================================================
def formatar_br(v):
    prefixo = "-" if v < 0 else ""
    return f"{prefixo}R$ {abs(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
def formatar_pct(v):
    prefixo = "+" if v > 0 else ""
    return f"{prefixo}{v:.2f}%".replace('.', ',')

# ==============================================================================
# 5. ORQUESTRAÇÃO DE DADOS (CACHEADA)
# ==============================================================================
@st.cache_data(ttl=600, show_spinner=False)
def orquestrar_pipeline_carteira():
    ID_UNIFICADO = '1d4AMHX5El8JOEbgwpBVm513-ImJPFiGXrRG_2VoObTo'
    
    df_mov = download_excel_from_drive(ID_UNIFICADO, sheet_name='Movimentacao')
    df_inf = download_excel_from_drive(ID_UNIFICADO, sheet_name='Inf_Ativos')
    df_precos_historicos = download_excel_from_drive(ID_UNIFICADO, sheet_name='Hist_Precos')
    
    # 🎯 NOVO: Busca Inteligente pelas Metas Setoriais na Planilha (lidando com possíveis variações de nome)
    df_metricas = pd.DataFrame()
    for aba_alvo in ['Mtericas', 'Metricas', 'seguimento']:
        try:
            df_metricas = download_excel_from_drive(ID_UNIFICADO, sheet_name=aba_alvo)
            if not df_metricas.empty:
                break
        except:
            continue
    
    for df in [df_mov, df_inf, df_precos_historicos]:
        df.columns = df.columns.astype(str).str.strip()
        if 'Ticker' in df.columns:
            df['Ticker'] = df['Ticker'].astype(str).str.strip()

    df_precos_historicos['Chave_Merge'] = df_precos_historicos['Chave_Merge'].astype(str).str.strip()
    
    conversao_tickers = {"MALL11": "PMLL11", "CVBI11": "PCIP11", "BOML": "BPML11"}
    df_mov['Ticker'] = df_mov['Ticker'].replace(conversao_tickers)
    df_inf['Ticker'] = df_inf['Ticker'].replace(conversao_tickers)
    df_precos_historicos['Ticker'] = df_precos_historicos['Ticker'].replace(conversao_tickers)
    
    df_mov['Quantidade_Num'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor_Operacao_Num'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)
    df_mov['Data_Datetime'] = pd.to_datetime(df_mov['Data'], format='%Y-%m-%d', errors='coerce')
    if df_mov['Data_Datetime'].isna().all():
        df_mov['Data_Datetime'] = pd.to_datetime(df_mov['Data'], format='%d/%m/%Y', errors='coerce')

    df_inf['Preco_Atual'] = pd.to_numeric(df_inf['Preco_Atual'], errors='coerce').fillna(0)
    df_precos_historicos['Preco_Mercado'] = pd.to_numeric(df_precos_historicos['Preco_Mercado'], errors='coerce')

    eventos_custodia = ['Compra', 'Venda', 'Desdobro']
    df_trades = df_mov[df_mov['Movimentação'].isin(eventos_custodia)].sort_values('Data_Datetime').copy()
    
    df_hist_ativos = calcular_historico_posicoes(df_trades)
    total_dividendos, ult_provento_val, ult_provento_mes = extrair_kpis_proventos(df_mov)
    
    if not df_hist_ativos.empty:
        df_hist_ativos['Data'] = pd.to_datetime(df_hist_ativos['Data'])
        
        data_atual = pd.Timestamp.now().normalize()
        linhas_extensao = []
        for tk in df_hist_ativos['Ticker'].unique():
            df_tk = df_hist_ativos[df_hist_ativos['Ticker'] == tk]
            if not df_tk.empty:
                ultimo_registro = df_tk.iloc[-1].copy()
                ultimo_registro['Data'] = data_atual
                linhas_extensao.append(ultimo_registro)
                
        df_hist_ext = pd.concat([df_hist_ativos, pd.DataFrame(linhas_extensao)], ignore_index=True)
        df_hist_ext = df_hist_ext.sort_values(by=['Data', 'Ticker'])
        
        df_mensal_ativos = (df_hist_ext
                            .set_index('Data')
                            .groupby('Ticker')[['Quantidade', 'Custo_Total']]
                            .resample('ME')
                            .last()
                            .ffill()
                            .reset_index())
        
        df_mensal_ativos.loc[df_mensal_ativos['Quantidade'] <= 0, 'Custo_Total'] = 0.0
        df_mensal_ativos['Chave_Merge'] = df_mensal_ativos['Data'].dt.strftime('%Y-%m')
        df_mensal_ativos['Mes_Ano'] = df_mensal_ativos['Data'].dt.to_period('M')
        
        df_consolidado = pd.merge(df_mensal_ativos, df_precos_historicos, on=['Chave_Merge', 'Ticker'], how='left')
        
        df_consolidado['Preco_Mercado'] = df_consolidado['Preco_Mercado'].replace(0, np.nan)
        df_consolidado = df_consolidado.sort_values(by=['Data', 'Ticker'])
        df_consolidado['Preco_Mercado'] = df_consolidado.groupby('Ticker')['Preco_Mercado'].ffill()
        
        df_consolidado = pd.merge(df_consolidado, df_inf, on='Ticker', how='left')
        
        mes_atual_chave = pd.Timestamp.now().strftime('%Y-%m')
        df_consolidado.loc[df_consolidado['Chave_Merge'] == mes_atual_chave, 'Preco_Mercado'] = df_consolidado['Preco_Atual']
        
        df_consolidado['Preco_Mercado'] = df_consolidado['Preco_Mercado'].fillna(df_consolidado['Custo_Total'] / df_consolidado['Quantidade']).fillna(0)
        df_consolidado['Patrimonio_Mercado_Ativo'] = df_consolidado['Quantidade'] * df_consolidado['Preco_Mercado']
        
        df_custodia_atual = df_consolidado[df_consolidado['Chave_Merge'] == mes_atual_chave].copy()
        df_custodia_atual = df_custodia_atual[df_custodia_atual['Quantidade'] > 0]
        
        for col in ['Classificacao', 'Seguimento', 'Gestora']:
            if col not in df_custodia_atual.columns: 
                df_custodia_atual[col] = 'NÃO INFORMADO'
            df_custodia_atual[col] = df_custodia_atual[col].fillna('NÃO INFORMADO').astype(str).str.upper()
        
        return df_mov, df_consolidado, df_custodia_atual, total_dividendos, ult_provento_val, ult_provento_mes, df_metricas
        
    return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 0.0, 0.0, "-", pd.DataFrame()

# ==============================================================================
# 6. EXECUÇÃO DA INTERFACE VISUAL
# ==============================================================================

PLOTLY_CONFIG_MOBILE = {'displayModeBar': False, 'scrollZoom': False}

try:
    with st.spinner('A sincronizar custódia com a nuvem...'):
        df_mov, df_consolidado, df_custodia_atual, total_dividendos, ult_provento_val, ult_provento_mes, df_metricas = orquestrar_pipeline_carteira()
except Exception as e:
    st.error("⚠️ Falha ao sincronizar com a base de dados. Verifique a sua ligação.")
    st.stop()

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

aba_resumo, aba_exposicao, aba_proventos, aba_rebalanceamento = st.tabs([
    "📝 Resumo", "📊 Exposição", "💰 Proventos", "⚖️ Rebalanceamento"
])

# ==============================================================================
# ABA 1: RESUMO
# ==============================================================================
with aba_resumo:
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
            
            fig_linhas.update_layout(margin=dict(l=45, r=10, t=25, b=10), height=315, hovermode='x unified', dragmode=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis=dict(gridcolor='rgba(230,235,240,0.6)', tickprefix="R$ ", tickformat="~s", nticks=6), xaxis=dict(gridcolor='rgba(0,0,0,0)', type='category'), legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5))
            st.plotly_chart(fig_linhas, use_container_width=True, config=PLOTLY_CONFIG_MOBILE)

    with col_bloco_direito:
        with st.container(border=True):
            st.markdown("<h3 style='margin:0; padding-top:4px; padding-bottom:5px; color:#2C3E50; font-size:19px; font-weight:600;'>Alocação</h3>", unsafe_allow_html=True)
            
            df_sunburst = df_custodia_atual.copy()
            texto_raiz = f"Carteira<br>{formatar_br(patrimonio_mercado_kpi)}"
            df_sunburst['Raiz'] = texto_raiz
            
            fig_p = px.sunburst(
                df_sunburst,
                path=['Raiz', 'Classificacao', 'Seguimento', 'Ticker'],
                values='Patrimonio_Mercado_Ativo'
            )
            
            if fig_p.data and fig_p.data[0].ids is not None:
                cores_fatias = []
                for id_str in fig_p.data[0].ids:
                    depth = str(id_str).count('/')
                    if depth == 0:
                        cores_fatias.append('#1D4E5B')
                    elif depth == 1:
                        cores_fatias.append('#3A7385')
                    elif depth == 2:
                        cores_fatias.append('#87B6C4')
                    else:
                        cores_fatias.append('#C2E2EB')
                
                fig_p.update_traces(marker=dict(
                    colors=cores_fatias,
                    line=dict(color='#1D4E5B', width=1.5)
                ))
            
            fig_p.update_layout(
                margin=dict(l=10, r=10, t=10, b=10), 
                height=315, 
                paper_bgcolor='rgba(0,0,0,0)',
                dragmode=False
            )
            
            fig_p.update_traces(
                textinfo="label+percent root",
                hovertemplate='<b>%{label}</b><br>Patrimônio: R$ %{value:,.2f}<extra></extra>'
            )
            
            st.plotly_chart(fig_p, use_container_width=True, config=PLOTLY_CONFIG_MOBILE)

# ==============================================================================
# ABA 2: EXPOSIÇÃO
# ==============================================================================
with aba_exposicao:
    if not df_custodia_atual.empty:
        df_analise = df_custodia_atual.copy()

        col_esq, col_meio, col_dir = st.columns([3, 4, 3])
        
        ALTURA_PILARES = 440 
        OVERHEAD_STREAMLIT = 74 
        ALTURA_ROSCAS = (ALTURA_PILARES - OVERHEAD_STREAMLIT) / 2
        
        with col_esq:
            with st.container(border=True):
                st.markdown("<h4 style='margin:0; padding-bottom:4px; color:#2C3E50; font-size:14px; font-weight:600; text-transform:uppercase;'>1. Exposição por Ativo</h4>", unsafe_allow_html=True)
                df_ativos_sorted = df_analise.sort_values(by='Patrimonio_Mercado_Ativo', ascending=True)
                
                fig_bar_ativos = go.Figure(go.Bar(
                    x=df_ativos_sorted['Patrimonio_Mercado_Ativo'], y=df_ativos_sorted['Ticker'],
                    orientation='h', marker_color='#1fbc74',
                    hovertemplate='<b>Ativo:</b> %{y}<br><b>Patrimônio:</b> R$ %{x:,.2f}<extra></extra>'
                ))
                fig_bar_ativos.update_layout(
                    margin=dict(l=55, r=10, t=10, b=10), height=ALTURA_PILARES, dragmode=False,
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(gridcolor='rgba(230,235,240,0.6)', tickprefix="R$ ", tickformat="~s"),
                    yaxis=dict(type='category', dtick=1, tickfont=dict(size=10))
                )
                st.plotly_chart(fig_bar_ativos, use_container_width=True, config=PLOTLY_CONFIG_MOBILE)

        with col_meio:
            with st.container(border=True):
                st.markdown("<h4 style='margin:0; padding-bottom:2px; color:#2C3E50; font-size:13px; font-weight:600; text-transform:uppercase;'>2. Classificação</h4>", unsafe_allow_html=True)
                df_g_tipo = df_analise.groupby('Classificacao')['Patrimonio_Mercado_Ativo'].sum().reset_index().sort_values(by='Patrimonio_Mercado_Ativo', ascending=False)
                
                fig_t = go.Figure(go.Pie(
                    labels=df_g_tipo['Classificacao'], values=df_g_tipo['Patrimonio_Mercado_Ativo'], hole=0.55,
                    textinfo='label+percent', textposition='inside', insidetextorientation='horizontal',
                    hovertemplate='<b>Classe:</b> %{label}<br><b>Patrimônio:</b> R$ %{value:,.2f}<extra></extra>'
                ))
                fig_t.update_layout(margin=dict(l=5, r=5, t=5, b=0), height=ALTURA_ROSCAS, dragmode=False, paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
                st.plotly_chart(fig_t, use_container_width=True, config=PLOTLY_CONFIG_MOBILE)
                
            with st.container(border=True):
                st.markdown("<h4 style='margin:0; padding-bottom:2px; color:#2C3E50; font-size:13px; font-weight:600; text-transform:uppercase;'>3. Seguimento</h4>", unsafe_allow_html=True)
                df_g_seg = df_analise.groupby('Seguimento')['Patrimonio_Mercado_Ativo'].sum().reset_index().sort_values(by='Patrimonio_Mercado_Ativo', ascending=False)
                
                fig_s = go.Figure(go.Pie(
                    labels=df_g_seg['Seguimento'], values=df_g_seg['Patrimonio_Mercado_Ativo'], hole=0.55,
                    textinfo='label+percent', textposition='inside', insidetextorientation='horizontal',
                    hovertemplate='<b>Seguimento:</b> %{label}<br><b>Patrimônio:</b> R$ %{value:,.2f}<extra></extra>'
                ))
                fig_s.update_layout(margin=dict(l=5, r=5, t=5, b=0), height=ALTURA_ROSCAS, dragmode=False, paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
                st.plotly_chart(fig_s, use_container_width=True, config=PLOTLY_CONFIG_MOBILE)

        with col_dir:
            with st.container(border=True):
                st.markdown("<h4 style='margin:0; padding-bottom:4px; color:#2C3E50; font-size:14px; font-weight:600; text-transform:uppercase;'>4. Exposição por Gestora</h4>", unsafe_allow_html=True)
                df_g_gest = df_analise.groupby('Gestora')['Patrimonio_Mercado_Ativo'].sum().reset_index().sort_values(by='Patrimonio_Mercado_Ativo', ascending=True)
                
                fig_bar_gest = go.Figure(go.Bar(
                    x=df_g_gest['Patrimonio_Mercado_Ativo'], y=df_g_gest['Gestora'],
                    orientation='h', marker_color='#118DFF',
                    hovertemplate='<b>Gestora:</b> %{y}<br><b>Patrimônio:</b> R$ %{x:,.2f}<extra></extra>'
                ))
                fig_bar_gest.update_layout(
                    margin=dict(l=75, r=10, t=10, b=10), height=ALTURA_PILARES, dragmode=False,
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(gridcolor='rgba(230,235,240,0.6)', tickprefix="R$ ", tickformat="~s"),
                    yaxis=dict(type='category', dtick=1, tickfont=dict(size=10))
                )
                st.plotly_chart(fig_bar_gest, use_container_width=True, config=PLOTLY_CONFIG_MOBILE)
    else:
        st.info("ℹ️ Nenhum dado de custódia disponível para gerar o raio-x de exposição.")

# ==============================================================================
# ABA 3: PROVENTOS
# ==============================================================================
with aba_proventos:
    st.markdown("<h3 style='margin:0; padding-top:4px; color:#2C3E50; font-size:22px; font-weight:600;'>Módulo de Renda Passiva</h3>", unsafe_allow_html=True)
    
    termos_proventos = ['Dividendo', 'JCP', 'Rendimento', 'Provento']
    df_prov_detalhe = df_mov[df_mov['Movimentação'].isin(termos_proventos)].copy()
    
    if not df_prov_detalhe.empty:
        media_mensal_prov = total_dividendos / max(len(df_prov_detalhe['Data_Datetime'].dt.to_period('M').unique()), 1)
        yoc_medio = (total_dividendos / total_investido_kpi * 100) if total_investido_kpi > 0 else 0.0
        yield_ultimo_mensal = (ult_provento_val / total_investido_kpi * 100) if total_investido_kpi > 0 else 0.0
        
        cp1, cp2, cp3 = st.columns(3)
        
        with cp1:
            st.markdown(f"""
                <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 10px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 110px; max-height: 110px;">
                    <span style="color: #5D6D7E; font-size: 14px; font-weight: bold; text-transform: uppercase;">Último Provento Recebido</span>
                    <div style="color: #2E8B57; font-size: 27px; font-weight: 700; margin-top: 1px; margin-bottom: 1px; letter-spacing: -0.5px;">{formatar_br(ult_provento_val)}</div>
                    <div style="border-top: 1px solid #E6E8EA; padding-top: 4px; font-size: 13px; color: #7F8C8D; display: flex; justify-content: space-between;">
                        <div>
                            <span style="font-size: 12px; color: #7F8C8D; text-transform: uppercase;">Representação/Aporte:</span>
                            <strong style="color: #2E8B57;">{yield_ultimo_mensal:.2f}% do inv.</strong>
                        </div>
                        <div style="text-align: right;">
                            <span style="font-size: 12px; color: #7F8C8D; text-transform: uppercase;">Ref:</span>
                            <strong style="color: #34495E;">{ult_provento_mes}</strong>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
        with cp2:
            st.markdown(f"""
                <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 10px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 110px; max-height: 110px;">
                    <span style="color: #5D6D7E; font-size: 14px; font-weight: bold; text-transform: uppercase;">Total de Proventos Históricos</span>
                    <div style="color: #2C3E50; font-size: 27px; font-weight: 700; margin-top: 1px; margin-bottom: 1px; letter-spacing: -0.5px;">{formatar_br(total_dividendos)}</div>
                    <div style="border-top: 1px solid #E6E8EA; padding-top: 4px; font-size: 13px; color: #7F8C8D; display: flex; justify-content: space-between;">
                        <div>
                            <span style="font-size: 12px; color: #7F8C8D; text-transform: uppercase;">Yield on Cost Médio:</span>
                            <strong style="color: #118DFF;">{yoc_medio:.2f}% Amort.</strong>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
        with cp3:
            st.markdown(f"""
                <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 10px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 110px; max-height: 110px;">
                    <span style="color: #5D6D7E; font-size: 14px; font-weight: bold; text-transform: uppercase;">Média Mensal de Caixa</span>
                    <div style="color: #2C3E50; font-size: 27px; font-weight: 700; margin-top: 1px; margin-bottom: 1px; letter-spacing: -0.5px;">{formatar_br(media_mensal_prov)}</div>
                    <div style="border-top: 1px solid #E6E8EA; padding-top: 4px; font-size: 13px; color: #7F8C8D; display: flex; justify-content: space-between;">
                        <div>
                            <span style="font-size: 12px; color: #7F8C8D; text-transform: uppercase;">Meses com Histórico:</span>
                            <strong style="color: #34495E;">{len(df_prov_detalhe['Data_Datetime'].dt.to_period('M').unique())} meses</strong>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
        col_graf_esq, col_graf_dir = st.columns([6, 4])
        
        with col_graf_esq:
            with st.container(border=True):
                st.markdown("<h4 style='margin:0; padding-bottom:5px; font-size:15px; color:#2C3E50;'>Evolução de Caixa Mensal (Proventos)</h4>", unsafe_allow_html=True)
                df_prov_detalhe['Mes_Ano_Str'] = df_prov_detalhe['Data_Datetime'].dt.strftime('%m/%Y')
                df_cron_prov = df_prov_detalhe.groupby('Data_Datetime').agg({'Valor_Operacao_Num':'sum'}).resample('ME').sum().reset_index()
                df_cron_prov['Mês'] = df_cron_prov['Data_Datetime'].dt.strftime('%m/%Y')
                
                fig_bar_prov = go.Figure(go.Bar(
                    x=df_cron_prov['Mês'], y=df_cron_prov['Valor_Operacao_Num'],
                    marker_color='#2E8B57',
                    hovertemplate='<b>Mês:</b> %{x}<br><b>Provento:</b> R$ %{y:,.2f}<extra></extra>'
                ))
                fig_bar_prov.update_layout(margin=dict(l=40, r=10, t=10, b=10), height=260, dragmode=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis=dict(gridcolor='rgba(230,235,240,0.6)', tickprefix="R$ "))
                st.plotly_chart(fig_bar_prov, use_container_width=True, config=PLOTLY_CONFIG_MOBILE)
                
        with col_graf_dir:
            with st.container(border=True):
                st.markdown("<h4 style='margin:0; padding-bottom:5px; font-size:15px; color:#2C3E50;'>Top Pagadores da Carteira (Acumulado)</h4>", unsafe_allow_html=True)
                df_ranking_ativos = df_prov_detalhe.groupby('Ticker')['Valor_Operacao_Num'].sum().reset_index().sort_values(by='Valor_Operacao_Num', ascending=True).tail(5)
                
                fig_rank = go.Figure(go.Bar(
                    x=df_ranking_ativos['Valor_Operacao_Num'], y=df_ranking_ativos['Ticker'],
                    orientation='h', marker_color='#FFD700',
                    hovertemplate='<b>Ativo:</b> %{y}<br><b>Total Pago:</b> R$ %{x:,.2f}<extra></extra>'
                ))
                fig_rank.update_layout(margin=dict(l=55, r=10, t=10, b=10), height=260, dragmode=False, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis=dict(gridcolor='rgba(230,235,240,0.6)', tickprefix="R$ "))
                st.plotly_chart(fig_rank, use_container_width=True, config=PLOTLY_CONFIG_MOBILE)
    else:
        st.info("ℹ️ Nenhuma movimentação de dividendos ou rendimentos mapeada na aba Movimentacao.")

# ==============================================================================
# ABA 4: REBALANCEAMENTO
# ==============================================================================
with aba_rebalanceamento:
    st.markdown("<h3 style='margin:0; padding-top:4px; color:#2C3E50; font-size:22px; font-weight:600;'>Grade de Rebalanceamento Estratégico</h3>", unsafe_allow_html=True)
    
    if not df_custodia_atual.empty:
        df_rebal_seg = df_custodia_atual.groupby('Seguimento', as_index=False)['Patrimonio_Mercado_Ativo'].sum()
        df_rebal_seg['% Atual'] = (df_rebal_seg['Patrimonio_Mercado_Ativo'] / patrimonio_mercado_kpi) * 100.0
        
        # 🎯 AJUSTE DE METAS: Importa dinamicamente as metas setoriais salvas no Google Drive
        if not df_metricas.empty:
            df_metricas.columns = df_metricas.columns.astype(str).str.strip()
            col_seg = next((c for c in df_metricas.columns if 'seguimento' in c.lower() or 'classe' in c.lower()), df_metricas.columns[0])
            col_meta = next((c for c in df_metricas.columns if 'meta' in c.lower() or '%' in c.lower()), df_metricas.columns[1])
            
            dict_metas = {}
            for _, row in df_metricas.iterrows():
                k = str(row[col_seg]).strip().upper()
                v = str(row[col_meta]).replace(',', '.').replace('%', '').strip()
                try:
                    val = float(v)
                    # Caso a percentagem esteja salva na planilha como decimal (ex: 0.20 em vez de 20%)
                    if val < 1.5 and val > 0: val = val * 100 
                    dict_metas[k] = val
                except:
                    pass
            df_rebal_seg['Meta (%)'] = df_rebal_seg['Seguimento'].map(dict_metas).fillna(0.0)
        else:
            # Fallback seguro caso a aba Metricas não exista
            df_rebal_seg['Meta (%)'] = 100.0 / len(df_rebal_seg)
        
        st.markdown("<p style='color:#7F8C8D; font-size:14px; margin-bottom:10px;'>1. Comece definindo as Metas Alvo (%) para os seus Seguimentos:</p>", unsafe_allow_html=True)
        
        df_painel_interativo = st.data_editor(
            df_rebal_seg,
            column_config={
                "Seguimento": st.column_config.TextColumn("Seguimento", disabled=True),
                "Patrimonio_Mercado_Ativo": st.column_config.NumberColumn("Patrimônio Atual", format="R$ %,.2f", disabled=True),
                "% Atual": st.column_config.NumberColumn("% Atual", format="%.2f%%", disabled=True),
                "Meta (%)": st.column_config.NumberColumn("Sua Meta (%)", min_value=0.0, max_value=100.0, format="%.2f%%")
            },
            hide_index=True,
            use_container_width=True
        )
        
        st.markdown("<br><p style='color:#7F8C8D; font-size:14px; margin-bottom:10px;'>2. Diagnóstico de Aportes Mapeado Diretamente por Ativo (Ticker):</p>", unsafe_allow_html=True)
        
        df_ativos_rebal = df_custodia_atual.copy()
        df_ativos_rebal['Preco_Medio'] = np.where(df_ativos_rebal['Quantidade'] > 0, df_ativos_rebal['Custo_Total'] / df_ativos_rebal['Quantidade'], 0)
        df_ativos_rebal['Variacao_Pct'] = np.where(df_ativos_rebal['Preco_Medio'] > 0, (df_ativos_rebal['Preco_Mercado'] / df_ativos_rebal['Preco_Medio']) - 1, 0)
        
        df_ativos_rebal = df_ativos_rebal.merge(df_painel_interativo[['Seguimento', 'Meta (%)']], on='Seguimento', how='left')
        
        df_ativos_rebal['Qtd_Ativos_Seg'] = df_ativos_rebal.groupby('Seguimento')['Ticker'].transform('count')
        df_ativos_rebal['Meta_Ativo_Pct'] = df_ativos_rebal['Meta (%)'] / df_ativos_rebal['Qtd_Ativos_Seg']
        df_ativos_rebal['Meta_Ativo_Val'] = (df_ativos_rebal['Meta_Ativo_Pct'] / 100.0) * patrimonio_mercado_kpi
        
        df_ativos_rebal['Diferenca_Val'] = df_ativos_rebal['Meta_Ativo_Val'] - df_ativos_rebal['Patrimonio_Mercado_Ativo']
        
        # 🎯 AJUSTE DE SINALIZAÇÃO DO REBALANCEAMENTO (Queda Brusca e Realização de Lucro)
        def processar_acao(row):
            var = row['Variacao_Pct']
            abaixo_meta = row['Patrimonio_Mercado_Ativo'] < row['Meta_Ativo_Val']
            abaixo_pm = row['Preco_Mercado'] <= row['Preco_Medio']
            
            if var <= -0.10:
                return "QUEDA BRUSCA"
            elif var >= 0.20:
                return "VENDER"
            elif abaixo_meta and abaixo_pm:
                return "🛒 COMPRAR"
            else:
                return "🛡️ AGUARDAR"

        df_ativos_rebal['Ação Sugerida'] = df_ativos_rebal.apply(processar_acao, axis=1)
        
        df_ativos_rebal['% Atual Ativo'] = (df_ativos_rebal['Patrimonio_Mercado_Ativo'] / patrimonio_mercado_kpi) * 100.0
        
        df_exibicao = df_ativos_rebal[['Ticker', 'Seguimento', 'Preco_Medio', 'Preco_Mercado', 'Variacao_Pct', '% Atual Ativo', 'Meta_Ativo_Pct', 'Diferenca_Val', 'Ação Sugerida']].copy()
        
        df_exibicao['Preço Médio'] = df_exibicao['Preco_Medio'].apply(formatar_br)
        df_exibicao['Preço Atual'] = df_exibicao['Preco_Mercado'].apply(formatar_br)
        df_exibicao['Variação'] = df_exibicao['Variacao_Pct'].apply(lambda x: f"{x*100:.2f}%".replace('.', ','))
        df_exibicao['% Atual'] = df_exibicao['% Atual Ativo'].apply(lambda x: f"{x:.2f}%".replace('.', ','))
        df_exibicao['Meta Ideal'] = df_exibicao['Meta_Ativo_Pct'].apply(lambda x: f"{x:.2f}%".replace('.', ','))
        
        df_exibicao['Aporte Recomendado'] = df_exibicao['Diferenca_Val'].apply(lambda x: formatar_br(x) if x > 0 else "R$ 0,00")
        
        df_exibicao = df_exibicao[['Ticker', 'Seguimento', 'Preço Médio', 'Preço Atual', 'Variação', '% Atual', 'Meta Ideal', 'Aporte Recomendado', 'Ação Sugerida']]
        
        st.dataframe(
            df_exibicao.sort_values(by=['Seguimento', 'Ticker']),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("ℹ️ Sem posições ativas em custódia para gerar matriz de rebalanceamento.")
