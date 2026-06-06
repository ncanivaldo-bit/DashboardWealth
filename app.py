import streamlit as st
import pandas as pd
import numpy as np
import json
import io
import plotly.graph_objects as go
import yfinance as yf
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Configuração de tela limpa
st.set_page_config(page_title="PREVPRIV", page_icon="📊", layout="wide")
st.title("PREVPRIV")
st.markdown("<p style='margin-bottom: -10px; font-size: 16px;'>🎯 <b>Missão:</b> Do vácuo absoluto a renda passiva sustentável</p>", unsafe_allow_html=True)

# ==============================================================================
# CONEXÃO COM O GOOGLE DRIVE
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
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_excel(fh, engine='openpyxl', sheet_name=sheet_name)

# ==============================================================================
# PROCESSAMENTO DOS DADOS - MOTOR FIEL AO COLAB ORIGINAL
# ==============================================================================
try:
    # IDs oficiais
    ID_MOV = '16GSsk9lcLnXO7YQaJmIW28mM9CrYZuJs'
    ID_INF = '1D3Nz78rVTEDMl8SOU29lXf_TMZz-sy4M'
    
    # 1. Carrega as tabelas
    df_mov = download_excel_from_drive(ID_MOV, sheet_name='Movimentação')
    df_inf = download_excel_from_drive(ID_INF, sheet_name='Inf_Ativos')
    
    df_mov.columns = df_mov.columns.astype(str).str.strip()
    df_inf.columns = df_inf.columns.astype(str).str.strip()
    
    # Tratamento de Datas e Extração do Ticker básico
    df_mov['Data'] = pd.to_datetime(df_mov['Data'], format='%d/%m/%Y', errors='coerce')
    df_mov['Ticker'] = df_mov['Produto'].astype(str).str.split(' - ').str[0].str.strip()
    
    # Unifica as mudanças históricas de Ticker
    df_mov['Ticker'] = df_mov['Ticker'].replace('MALL11', 'PMLL11')
    df_mov['Ticker'] = df_mov['Ticker'].replace('CVBI11', 'PCIP11')
    
    # Força conversão numérica segura prevenindo #REF! ou nulos
    df_mov['Quantidade'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor da Operação'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)
    df_inf['Preco_Atual'] = pd.to_numeric(df_inf['Preco_Atual'], errors='coerce').fillna(0)
    
    # Filtro cronológico idêntico ao Passo 2 do Colab
    df_trades = df_mov[df_mov['Movimentação'].isin(['Transferência - Liquidação', 'Desdobro', 'Atualização', 'COMPRA / VENDA'])].sort_values('Data').copy()
    
    carteira = {}
    historico_detalhado = []
    
    # Execução exata do laço linha por linha do Colab
    for _, row in df_trades.iterrows():
        ticker = row['Ticker']
        data = row['Data']
        mov = row['Movimentação']
        tipo = str(row['Entrada/Saída']).strip() # Credito ou Debito
        qtd = float(row['Quantidade'])
        valor = float(row['Valor da Operação'])
        
        if ticker not in carteira:
            carteira[ticker] = {'quantidade': 0.0, 'custo_total': 0.0, 'preco_medio': 0.0}
            
        if mov in ['Transferência - Liquidação', 'COMPRA / VENDA']:
            if tipo == 'Credito':
                carteira[ticker]['quantidade'] += qtd
                carteira[ticker]['custo_total'] += valor
            elif tipo == 'Debito':
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
                'Custo_Total': dados['custo_total'],
                'Preco_Medio': dados['preco_medio']
            })
            
    # 3. Agrupamento temporal do Colab ressampled por fim de mês ('ME')
    df_hist_ativos = pd.DataFrame(historico_detalhado)
    if not df_hist_ativos.empty:
        df_hist_ativos['Data'] = pd.to_datetime(df_hist_ativos['Data'])
        
        # Agrupamento e ffill idêntico ao Colab
        df_mensal_ativos = (df_hist_ativos
                            .set_index('Data')
                            .groupby('Ticker')[['Quantidade', 'Custo_Total', 'Preco_Medio']]
                            .resample('ME')
                            .last()
                            .ffill()
                            .reset_index())
        
        df_mensal_ativos['Chave_Merge'] = df_mensal_ativos['Data'].dt.strftime('%Y-%m')
        df_mensal_ativos['Mes_Ano'] = df_mensal_ativos['Data'].dt.to_period('M')
        
        # 4. BUSCA EXTERNA COM AUTO_ADJUST=FALSE DO YAHOO (O SEGREDO DA MAESTRIA)
        tickers_unicos = df_mensal_ativos['Ticker'].unique()
        precos_mercado_lista = []
        start_date = df_mensal_ativos['Data'].min().strftime('%Y-%m-%d') if not df_mensal_ativos.empty else "2023-01-01"
        
        for t in tickers_unicos:
            if not t or str(t) == 'nan' or t == 'SPYI11':
                continue
            try:
                ticker_yf = f"{t}.SA"
                acao = yf.Ticker(ticker_yf)
                # auto_adjust=False garante o preço cru original de época
                hist = acao.history(start=start_date, end="2026-06-05", auto_adjust=False)
                
                if not hist.empty:
                    hist.index = hist.index.tz_localize(None)
                    hist_mensal = hist['Close'].resample('ME').last()
                    
                    for data_ref, preco in hist_mensal.items():
                        precos_mercado_lista.append({
                            'Chave_Merge': data_ref.strftime('%Y-%m'),
                            'Ticker': t,
                            'Preco_Mercado': float(preco)
                        })
            except Exception:
                pass
                
        df_precos = pd.DataFrame(precos_mercado_lista)
        
        # 5. CRUZAMENTO DOS DADOS (MERGE)
        if not df_precos.empty:
            df_consolidado = pd.merge(df_mensal_ativos, df_precos, on=['Chave_Merge', 'Ticker'], how='left')
        else:
            df_consolidado = df_mensal_ativos.copy()
            df_consolidado['Preco_Mercado'] = np.nan
            
        # 6. LÓGICA DE PREENCHIMENTO SEGURO
        df_consolidado['Preco_Mercado'] = df_consolidado.groupby('Ticker')['Preco_Mercado'].ffill()
        df_consolidado['Preco_Mercado'] = df_consolidado['Preco_Mercado'].fillna(df_consolidado['Preco_Medio'])
        
        # 7. CÁLCULO DA EVOLUÇÃO PATRIMONIAL A MERCADO VS CUSTO
        df_consolidado['Patrimonio_Mercado'] = df_consolidado['Quantidade'] * df_consolidado['Preco_Mercado']
        
        df_portfolio_mensal = df_consolidado.groupby('Mes_Ano').agg({
            'Custo_Total': 'sum',
            'Patrimonio_Mercado': 'sum'
        }).reset_index()
        
        # Converte Period de volta para string legível para o gráfico do Plotly
        df_portfolio_mensal['Mês_Exibição'] = df_portfolio_mensal['Mes_Ano'].dt.strftime('%m/%Y')
    else:
        df_portfolio_mensal = pd.DataFrame()

    # --- DADOS DO MOMENTO ATUAL PARA OS 4 KPIS CARD ---
    carteira_kpis = {}
    for _, row in df_trades.iterrows():
        tk = row['Ticker']
        mov = row['Movimentação']
        sentido = str(row['Entrada/Saída']).strip()
        qtd = float(row['Quantidade'])
        valor_op = float(row['Valor da Operação'])
        
        if tk not in carteira_kpis:
            carteira_kpis[tk] = {'qtd': 0.0, 'custo': 0.0}
        if mov == 'Desdobro':
            carteira_kpis[tk]['qtd'] += qtd
        elif mov == 'Atualização' and tk == 'PCIP11' and qtd == 159:
            continue
        elif mov in ['Transferência - Liquidação', 'COMPRA / VENDA']:
            if sentido == 'Credito':
                carteira_kpis[tk]['qtd'] += qtd
                carteira_kpis[tk]['custo'] += valor_op
            elif sentido == 'Debito':
                if carteira_kpis[tk]['qtd'] > 0:
                    pm_at = carteira_kpis[tk]['custo'] / carteira_kpis[tk]['qtd']
                    carteira_kpis[tk]['qtd'] = max(0.0, carteira_kpis[tk]['qtd'] - qtd)
                    carteira_kpis[tk]['custo'] = carteira_kpis[tk]['qtd'] * pm_at

    linhas_kpi = []
    for tk, dados in carteira_kpis.items():
        if dados['qtd'] > 0:
            pm = dados['custo'] / dados['qtd']
            linhas_kpi.append({'Ticker': tk, 'Quantidade': dados['qtd'], 'Preço Médio Real': pm, 'Total Investido Ativo': dados['custo']})
    df_final = pd.DataFrame(linhas_kpi)
    
    df_final = pd.merge(df_final, df_inf[['Ticker', 'Preco_Atual', 'Seguimento', 'Classificacao', 'Tipo']], on='Ticker', how='left')
    df_final['Patrimônio Atual'] = df_final['Quantidade'] * df_final['Preco_Atual']

    # --- CÁLCULO GERAL DOS INDICADORES ATUAIS TRANCADOS ---
    patrimonio_total = df_final['Patrimônio Atual'].sum()
    total_investido = df_final['Total Investido Ativo'].sum()
    ganho_capital = patrimonio_total - total_investido
    
    df_prov = df_mov[df_mov['Movimentação'].isin(['Rendimento', 'Juros Sobre Capital Próprio'])].copy()
    total_dividendos = df_prov['Valor da Operação'].sum()
    lucro_total = ganho_capital + total_dividendos
    
    df_prov['AnoMes'] = df_prov['Data'].dt.to_period('M')
    if not df_prov.empty:
        ultimo_mes_valido = df_prov.sort_values('Data')['AnoMes'].iloc[-1]
        ultimo_provento_mensal = df_prov[df_prov['AnoMes'] == ultimo_mes_valido]['Valor da Operação'].sum()
        str_mes_prov = ultimo_mes_valido.strftime('%m/%Y')
    else:
        ultimo_provento_mensal = 0.0
        str_mes_prov = "-"

    rentabilidade_pct = (ganho_capital / total_investido * 100) if total_investido > 0 else 0.0

    # Formatação Padrão Brasil
    def formatar_br(v): return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    str_patrimonio = formatar_br(patrimonio_total)
    str_investido = formatar_br(total_investido)
    str_ganho_cap = formatar_br(ganho_capital)
    str_div_rec = formatar_br(total_dividendos)
    str_lucro_tot = formatar_br(lucro_total)
    str_ultimo_prov = formatar_br(ultimo_provento_mensal)
    
    cor_lucro = "#2E8B57" if lucro_total >= 0 else "#E74C3C"
    cor_ganho = "#2E8B57" if ganho_capital >= 0 else "#E74C3C"
    cor_rent = "#2E8B57" if rentabilidade_pct >= 0 else "#E74C3C"

    # ==============================================================================
    # RENDERIZAÇÃO DAS ABAS NA TELA
    # ==============================================================================
    st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
    aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Outras Análises"])
    
    with aba_resumo:
        # Linha de KPIs (Intocáveis)
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
                <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 140px;">
                    <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Patrimônio Atual</span>
                    <div style="color: #2C3E50; font-size: 24px; font-weight: 700; margin-top: 5px; margin-bottom: 5px;">{str_patrimonio}</div>
                    <div style="border-top: 1px solid #E6E8EA; padding-top: 5px; font-size: 12px; color: #7F8C8D;">
                        Total Investido: <span style="color: #34495E; font-weight:bold;">{str_investido}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown(f"""
                <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 140px;">
                    <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Lucro Total</span>
                    <div style="color: {cor_lucro}; font-size: 24px; font-weight: 700; margin-top: 5px; margin-bottom: 5px;">{str_lucro_tot}</div>
                    <div style="border-top: 1px solid #E6E8EA; padding-top: 5px; font-size: 11px; color: #7F8C8D; display: flex; justify-content: space-between;">
                        <span>Ganho Cap: <strong style="color:{cor_ganho};">{str_ganho_cap}</strong></span>
                        <span>Proventos: <strong style="color:#2E8B57;">{str_div_rec}</strong></span>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        with col3:
            st.markdown(f"""
                <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 140px;">
                    <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Último Provento Mensal</span>
                    <div style="color: #2E8B57; font-size: 24px; font-weight: 700; margin-top: 5px; margin-bottom: 5px;">{str_ultimo_prov}</div>
                    <div style="border-top: 1px solid #E6E8EA; padding-top: 5px; font-size: 12px; color: #7F8C8D;">
                        Mês Ref: <span style="color: #34495E; font-weight:bold;">{str_mes_prov}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        with col4:
            st.markdown(f"""
                <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 140px;">
                    <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Variação e Rentabilidade</span>
                    <div style="color: {cor_ganho}; font-size: 24px; font-weight: 700; margin-top: 5px; margin-bottom: 5px;">{str_ganho_cap}</div>
                    <div style="border-top: 1px solid #E6E8EA; padding-top: 5px; font-size: 12px; color: #7F8C8D;">
                        Rentabilidade: <span style="color: {cor_rent}; font-weight:bold;">{"+" if rentabilidade_pct>=0 else ""}{rentabilidade_pct:.2f}%</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)

        # ==============================================================================
        # GRÁFICOS: 60% EVOLUÇÃO MAESTRIA COLAB | 40% ROSCA COM LEG PERCENTUAL LIMPA
        # ==============================================================================
        g_col1, g_col2 = st.columns([6, 4])
        
        with g_col1:
            if not df_portfolio_mensal.empty:
                fig_lin = go.Figure()
                # Linha do Valor de Mercado Real (Verde) vinda do cruzamento de fechamentos crus do Colab
                fig_lin.add_trace(go.Scatter(
                    x=df_portfolio_mensal['Mês_Exibição'], 
                    y=df_portfolio_mensal['Patrimonio_Mercado'],
                    mode='lines+markers',
                    name='Valor de Mercado',
                    line=dict(color='#2E8B57', width=3),
                    marker=dict(size=5),
                    hovertemplate='<b>Mês:</b> %{x}<br><b>Mercado:</b> R$ %{y:,.2f}<extra></extra>'
                ))
                # Linha do Total Investido (Azul Tracejado) vinda do acúmulo cronológico puro
                fig_lin.add_trace(go.Scatter(
                    x=df_portfolio_mensal['Mês_Exibição'], 
                    y=df_portfolio_mensal['Custo_Total'],
                    mode='lines+markers',
                    name='Total Investido',
                    line=dict(color='#118DFF', width=2, dash='dot'),
                    marker=dict(size=5),
                    hovertemplate='<b>Mês:</b> %{x}<br><b>Investido:</b> R$ %{y:,.2f}<extra></extra>'
                ))
                fig_lin.update_layout(
                    title="<b>Evolução Patrimonial: Investido vs Mercado Real B3</b>",
                    title_font=dict(size=14, color='#2C3E50'),
                    margin=dict(l=40, r=20, t=40, b=30),
                    height=400,
                    hovermode='closest',
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    yaxis=dict(gridcolor='rgba(230,235,240,0.6)', tickprefix="R$ "),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_lin, width='stretch')
            else:
                st.info("Dados de evolução histórica insuficientes.")

        with g_col2:
            df_rosca = df_final.sort_values(by='Patrimônio Atual', ascending=False).copy()
            
            # Legenda Perfeita: Estritamente Ticker e a porcentagem limpa ao lado direito
            lista_legendas = []
            for _, r_f in df_rosca.iterrows():
                pct_mi = (r_f['Patrimônio Atual'] / patrimonio_total) * 100 if patrimonio_total > 0 else 0.0
                lista_legendas.append(f"{r_f['Ticker']} ({pct_mi:.1f}%)")
            
            fig_pie = go.Figure()
            fig_pie.add_trace(go.Pie(
                labels=lista_legendas, 
                values=df_rosca['Patrimônio Atual'],
                hole=0.5,
                textinfo='none', 
                hovertemplate='<b>Ativo:</b> %{label}<extra></extra>'
            ))
            fig_pie.update_layout(
                title="<b>Distribuição e Peso dos Ativos</b>",
                title_font=dict(size=14, color='#2C3E50'),
                margin=dict(l=10, r=10, t=40, b=10),
                height=400,
                paper_bgcolor='rgba(0,0,0,0)',
                showlegend=True,
                legend=dict(
                    orientation="v", 
                    yanchor="middle", 
                    y=0.5, 
                    xanchor="left", 
                    x=1.02,
                    font=dict(size=11)
                )
            )
            st.plotly_chart(fig_pie, width='stretch')

    with aba_alocacao:
        st.info("Esta aba está pronta para receber o GPS de Rebalanceamento Estratégico nos próximos passos.")
        
except Exception as e:
    st.error(f"❌ Erro no processamento: {e}")
