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
# 4. ORQUESTRAÇÃO DE DADOS (CACHEADA)
# ==============================================================================
@st.cache_data(ttl=600, show_spinner=False)
def orquestrar_pipeline_carteira():
    ID_UNIFICADO = '1d4AMHX5El8JOEbgwpBVm513-ImJPFiGXrRG_2VoObTo'
    
    df_mov = download_excel_from_drive(ID_UNIFICADO, sheet_name='Movimentacao')
    df_inf = download_excel_from_drive(ID_UNIFICADO, sheet_name='Inf_Ativos')
    df_precos_historicos = download_excel_from_drive(ID_UNIFICADO, sheet_name='Hist_Precos')
    
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
    df_precos_historicos['Preco_Mercado'] = pd.to_numeric(df_precos_historicos['Preco_Mercado'], errors='coerce').fillna(0)

    eventos_custodia = ['Compra', 'Venda', 'Desdobro']
    df_trades = df_mov[df_mov['Movimentação'].isin(eventos_custodia)].sort_values('Data_Datetime').copy()
    
    df_hist_ativos = calcular_historico_posicoes(df_trades)
    total_dividendos, ult_provento_val, ult_provento_mes = extrair_kpis_proventos(df_mov)
    
    if not df_hist_ativos.empty:
        df_hist_ativos['Data'] = pd.to_datetime(df_hist_ativos['Data'])
        
        # Extensão da linha do tempo para preservar ativos estáticos (Jan/2025)
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
        
        return df_consolidado, df_custodia_atual, total_dividendos, ult_provento_val, ult_provento_mes
        
    return pd.DataFrame(), pd.DataFrame(), 0.0, 0.0, "-"

# ==============================================================================
# 5. EXECUÇÃO DA INTERFACE VISUAL
# ==============================================================================

PLOTLY_CONFIG_MOBILE = {'displayModeBar': False, 'scrollZoom': False}

try:
    with st.spinner('A sincronizar custódia com a nuvem...'):
        df_consolidado, df_custodia_atual, total_dividendos, ult_provento_val, ult_provento_mes = orquestrar_pipeline_carteira()
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

aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Alocação"])

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
            
            # 🎯 Embutindo o valor total no centro (formatação idêntica à imagem)
            texto_raiz = f"Carteira<br>{formatar_br(patrimonio_mercado_kpi)}"
            df_sunburst['Raiz'] = texto_raiz
            
            fig_p = px.sunburst(
                df_sunburst,
                path=['Raiz', 'Classificacao', 'Seguimento', 'Ticker'],
                values='Patrimonio_Mercado_Ativo'
            )
            
            # 🎯 ENGENHARIA DE CORES POR PROFUNDIDADE (Efeito Degradê Monocromático)
            if fig_p.data and fig_p.data[0].ids is not None:
                cores_fatias = []
                for id_str in fig_p.data[0].ids:
                    # A profundidade é dada pela quantidade de barras (/) no ID da hierarquia
                    depth = str(id_str).count('/')
                    if depth == 0:
                        cores_fatias.append('#264D59') # Nível 0: Centro Escuro (Carteira)
                    elif depth == 1:
                        cores_fatias.append('#438292') # Nível 1: Classes (Tijolo, Papel)
                    elif depth == 2:
                        cores_fatias.append('#8EBEC9') # Nível 2: Seguimentos (Shopping, Logístico)
                    else:
                        cores_fatias.append('#C6E0E5') # Nível 3: Tickers mais claros na borda externa
                
                fig_p.update_traces(marker=dict(colors=cores_fatias))
            
            fig_p.update_layout(
                margin=dict(l=10, r=10, t=10, b=10), 
                height=315, 
                paper_bgcolor='rgba(0,0,0,0)',
                dragmode=False
            )
            
            # Força o percentual no anel externo e o nome da fatia
            fig_p.update_traces(
                textinfo="label+percent root",
                hovertemplate='<b>%{label}</b><br>Patrimônio: R$ %{value:,.2f}<extra></extra>'
            )
            
            st.plotly_chart(fig_p, use_container_width=True, config=PLOTLY_CONFIG_MOBILE)

# ------------------------------------------------------------------------------
# ⚙️ ABA 2: CENTRAL DE ALOCAÇÃO
# ------------------------------------------------------------------------------
with aba_alocacao:
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
        st.info("ℹ️ Nenhum dado de custódia disponível para gerar o raio-x de alocação.")
