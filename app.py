import streamlit as st
import pandas as pd
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
# MOTOR PROFISSONAL DE BUSCA DE COTAÇÕES HISTÓRICAS REAIS
# ==============================================================================
@st.cache_data(ttl=86400)
def buscar_fechamentos_historicos(tickers_list, data_minima):
    df_quadro_precos = pd.DataFrame()
    
    for tk in tickers_list:
        if not tk or str(tk) == 'nan' or tk == 'SPYI11':
            continue
        try:
            # Uso do objeto Ticker + history (muito mais estável para ativos da B3)
            ticker_objeto = yf.Ticker(f"{tk}.SA")
            df_hist = ticker_objeto.history(start=data_minima, interval="1mo")
            
            if not df_hist.empty:
                # Captura a coluna de fechamento independente do case ('Close' ou 'close')
                col_fechamento = [c for c in df_hist.columns if c.lower() == 'close'][0]
                serie_preco = df_hist[col_fechamento].copy()
                
                # Alinha o índice temporal para o formato Ano-Mês
                serie_preco.index = serie_preco.index.to_period('M')
                serie_preco = serie_preco.groupby(serie_preco.index).last()
                
                df_quadro_precos[tk] = serie_preco
        except Exception:
            pass
            
    # Tratamento de preenchimento progressivo: se o mercado não abriu ou a API falhou 
    # num mês específico, ele herda o preço de mercado real do mês anterior (ffill)
    if not df_quadro_precos.empty:
        df_quadro_precos = df_quadro_precos.ffill()
        
    return df_quadro_precos

# ==============================================================================
# PROCESSAMENTO DOS DADOS DO DRIVE E CÁLCULO PATRIMONIAL
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
    
    # 2. Tratamento de Datas e Extração do Ticker
    df_mov['Data'] = pd.to_datetime(df_mov['Data'], format='%d/%m/%Y', errors='coerce')
    df_mov['Ticker'] = df_mov['Produto'].astype(str).str.split(' - ').str[0].str.strip()
    
    df_mov['Ticker'] = df_mov['Ticker'].replace('MALL11', 'PMLL11')
    df_mov['Ticker'] = df_mov['Ticker'].replace('CVBI11', 'PCIP11')
    
    df_mov['Quantidade'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor da Operação'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)
    df_inf['Preco_Atual'] = pd.to_numeric(df_inf['Preco_Atual'], errors='coerce').fillna(0)
    
    # 3. Processamento Cronológico de Custódia
    df_trades = df_mov[df_mov['Movimentação'].isin(['Transferência - Liquidação', 'Desdobro', 'Atualização'])].sort_values('Data').copy()
    df_trades['AnoMes'] = df_trades['Data'].dt.to_period('M')
    
    data_inicio_string = df_trades['Data'].min().strftime('%Y-%m-%d') if not df_trades.empty else "2023-01-01"
    lista_todos_tickers = df_trades['Ticker'].dropna().unique().tolist()
    
    # Baixa a tabela com os preços REAIS de fechamento da história
    df_precos_reais_api = buscar_fechamentos_historicos(lista_todos_tickers, data_inicio_string)
    
    carteira_corrente = {}
    meses_historicos = sorted(df_trades['AnoMes'].dropna().unique())
    historico_pontos = []
    
    for am in meses_historicos:
        df_mes = df_trades[df_trades['AnoMes'] == am]
        
        for _, row in df_mes.iterrows():
            tk = row['Ticker']
            mov = row['Movimentação']
            sentido = str(row['Entrada/Saída']).strip()
            qtd = float(row['Quantidade'])
            valor_op = float(row['Valor da Operação'])
            
            if tk not in carteira_corrente:
                carteira_corrente[tk] = {'qtd': 0.0, 'custo': 0.0}
                
            if mov == 'Desdobro':
                carteira_corrente[tk]['qtd'] += qtd
            elif mov == 'Atualização' and tk == 'PCIP11' and qtd == 159:
                continue
            elif mov == 'Transferência - Liquidação':
                if sentido == 'Credito':
                    carteira_corrente[tk]['qtd'] += qtd
                    carteira_corrente[tk]['custo'] += valor_op
                elif sentido == 'Debito':
                    if carteira_corrente[tk]['qtd'] > 0:
                        pm_proporcional = carteira_corrente[tk]['custo'] / carteira_corrente[tk]['qtd']
                        carteira_corrente[tk]['qtd'] = max(0.0, carteira_corrente[tk]['qtd'] - qtd)
                        carteira_corrente[tk]['custo'] = carteira_corrente[tk]['qtd'] * pm_proporcional
                        
        # CÁLCULO PATRIMONIAL DO MÊS CORRIGIDO
        investido_no_mes = 0.0
        mercado_no_mes = 0.0
        
        for tk, dados in carteira_corrente.items():
            if dados['qtd'] > 0:
                investido_no_mes += dados['custo']
                
                # Tenta resgatar o preço real da bolsa daquele mês
                preco_real_fechamento = 0.0
                if not df_precos_reais_api.empty and am in df_precos_reais_api.index:
                    if tk in df_precos_reais_api.columns:
                        preco_real_fechamento = float(df_precos_reais_api.loc[am, tk])
                
                # Se não houver histórico na API para aquele mês específico de jeito nenhum,
                # aí sim aplicamos o Preço Médio como último recurso
                if pd.isna(preco_real_fechamento) or preco_real_fechamento <= 0:
                    preco_real_fechamento = dados['custo'] / dados['qtd']
                    
                mercado_no_mes += dados['qtd'] * preco_real_fechamento
                
        if investido_no_mes > 0:
            historico_pontos.append({
                'Mês': am.strftime('%m/%Y'),
                'Total Investido': investido_no_mes,
                'Valor de Mercado': mercado_no_mes
            })
            
    df_evolucao = pd.DataFrame(historico_pontos)

    # 4. Consolidação Atual para KPIs e Rosca
    linhas_finais = []
    for tk, dados in carteira_corrente.items():
        if dados['qtd'] > 0:
            pm = dados['custo'] / dados['qtd']
            linhas_finais.append({'Ticker': tk, 'Quantidade': dados['qtd'], 'Preço Médio Real': pm, 'Total Investido Ativo': dados['custo']})
    df_final = pd.DataFrame(linhas_finais)
    
    df_final = pd.merge(df_final, df_inf[['Ticker', 'Preco_Atual', 'Seguimento', 'Classificacao', 'Tipo']], on='Ticker', how='left')
    df_final['Patrimônio Atual'] = df_final['Quantidade'] * df_final['Preco_Atual']

    # --- CÁLCULO DOS VALORES GLOBAIS ATUAIS ---
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

    # --- ESTILIZAÇÃO DE STRINGS MENSAGENS ---
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
    # RENDERIZAÇÃO DAS ABAS
    # ==============================================================================
    st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
    aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Outras Análises"])
    
    with aba_resumo:
        # Linha de KPIs (Totalmente Trancada e Intacta)
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
        # GRÁFICOS RECONSTRUÍDOS (60% / 40%)
        # ==============================================================================
        g_col1, g_col2 = st.columns([6, 4])
        
        with g_col1:
            if not df_evolucao.empty:
                fig_lin = go.Figure()
                # Linha do Valor de Mercado Real (Verde)
                fig_lin.add_trace(go.Scatter(
                    x=df_evolucao['Mês'], 
                    y=df_evolucao['Valor de Mercado'],
                    mode='lines+markers',
                    name='Valor de Mercado (Preço Real)',
                    line=dict(color='#2E8B57', width=3),
                    marker=dict(size=5),
                    hovertemplate='<b>Mês:</b> %{x}<br><b>Mercado:</b> R$ %{y:,.2f}<extra></extra>'
                ))
                # Linha do Total Investido (Azul Tracejado)
                fig_lin.add_trace(go.Scatter(
                    x=df_evolucao['Mês'], 
                    y=df_evolucao['Total Investido'],
                    mode='lines+markers',
                    name='Total Investido (Custo)',
                    line=dict(color='#118DFF', width=2, dash='dot'),
                    marker=dict(size=5),
                    hovertemplate='<b>Mês:</b> %{x}<br><b>Investido:</b> R$ %{y:,.2f}<extra></extra>'
                ))
                fig_lin.update_layout(
                    title="<b>Evolução Patrimonial Real: Custo vs Mercado B3</b>",
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
