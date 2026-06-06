import streamlit as st
import pandas as pd
import numpy as np
import json
import io
import plotly.graph_objects as go
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Configuração de tela limpa padrão do painel PREVPRIV
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
# PROCESSAMENTO DOS DADOS - MOTOR RECALIBRADO VIA ENGENHARIA REVERSA
# ==============================================================================
try:
    ID_MOV = '1JJPFCTWORXmTBJB3KdtKK-LRf-3A8XIAESWRiOX-G4E' # Movimentação
    ID_INF = '1FcBDlaArTQrkYdmDFbqbwObl5qmPy8K2sxxiE0RE8QE' # Inf_Ativos
    
    df_mov = download_excel_from_drive(ID_MOV, sheet_name=0) 
    df_inf = download_excel_from_drive(ID_INF, sheet_name=0) 
    df_precos_historicos = download_excel_from_drive(ID_INF, sheet_name='Hist_Precos')
    
    df_mov.columns = df_mov.columns.astype(str).str.strip()
    df_inf.columns = df_inf.columns.astype(str).str.strip()
    df_precos_historicos.columns = df_precos_historicos.columns.astype(str).str.strip()
    
    col_inf_ticker = [c for c in df_inf.columns if c.lower() == 'ticker'][0]
    col_inf_preco = [c for c in df_inf.columns if 'preco_atual' in c.lower() or 'preço atual' in c.lower()][0]

    col_data = 'Data'
    col_movimentacao = 'Movimentação'
    col_produto = 'Produto'
    col_quantidade = 'Quantidade'
    col_valor = 'Valor da Operação'
    col_sentido = 'Entrada/Saída'

    df_inf['Preco_Atual'] = pd.to_numeric(df_inf[col_inf_preco], errors='coerce').fillna(0)
    df_inf['Ticker'] = df_inf[col_inf_ticker].astype(str).str.strip()
    
    df_mov['Data_Datetime'] = pd.to_datetime(df_mov[col_data], format='%d/%m/%Y', errors='coerce')
    df_mov['Ticker'] = df_mov[col_produto].astype(str).str.split(' - ').str[0].str.strip()
    
    # Padronização de Tickers
    df_mov['Ticker'] = df_mov['Ticker'].replace('MALL11', 'PMLL11')
    df_mov['Ticker'] = df_mov['Ticker'].replace('CVBI11', 'PCIP11')
    
    df_mov['Quantidade_Num'] = pd.to_numeric(df_mov[col_quantidade], errors='coerce').fillna(0)
    df_mov['Valor_Num'] = pd.to_numeric(df_mov[col_valor], errors='coerce').fillna(0)
    df_precos_historicos['Preco_Mercado'] = pd.to_numeric(df_precos_historicos['Preco_Mercado'], errors='coerce').fillna(0)

    # --- 1. CÁLCULO SOBERANO DA FOTO ATUAL (Idêntico ao Card que funciona) ---
    df_trades_total = df_mov[df_mov[col_movimentacao].isin(['Transferência - Liquidação', 'Desdobro', 'Atualização', 'COMPRA / VENDA'])].copy()
    
    carteira_atual = {}
    for _, row in df_trades_total.iterrows():
        tk = row['Ticker']
        mov = row[col_movimentacao]
        tipo = str(row[col_sentido]).strip()
        qtd = float(row['Quantidade_Num'])
        valor = float(row['Valor_Num'])
        
        if tk not in carteira_atual:
            carteira_atual[tk] = {'quantidade': 0.0, 'custo_total': 0.0}
            
        if mov in ['Transferência - Liquidação', 'COMPRA / VENDA']:
            if tipo == 'Credito':
                carteira_atual[tk]['quantidade'] += qtd
                carteira_atual[tk]['custo_total'] += valor
            elif tipo == 'Debito':
                if carteira_atual[tk]['quantidade'] > 0:
                    p_medio = carteira_atual[tk]['custo_total'] / carteira_atual[tk]['quantidade']
                    carteira_atual[tk]['custo_total'] -= min(qtd, carteira_atual[tk]['quantidade']) * p_medio
                carteira_atual[tk]['quantidade'] -= qtd
        elif mov == 'Desdobro':
            carteira_atual[tk]['quantidade'] += qtd

    # Monta a tabela de KPIs de hoje com precisão absoluta
    linhas_kpi = []
    for tk, dados in carteira_atual.items():
        if dados['quantidade'] > 0:
            linhas_kpi.append({
                'Ticker': tk, 
                'Quantidade_Atual': dados['quantidade'], 
                'Total Investido Ativo': dados['custo_total']
            })
    df_final_custodia = pd.DataFrame(linhas_kpi)
    df_final = pd.merge(df_final_custodia, df_inf[['Ticker', 'Preco_Atual', 'Seguimento', 'Classificacao', 'Tipo']], on='Ticker', how='left')
    df_final['Patrimônio Atual'] = df_final['Quantidade_Atual'] * df_final['Preco_Atual']

    patrimonio_total = df_final['Patrimônio Atual'].sum()
    total_investido = df_final['Total Investido Ativo'].sum()
    ganho_capital = patrimonio_total - total_investido

    # --- 2. ENGENHARIA REVERSA PARA CRIAÇÃO DO GRÁFICO HISTÓRICO ---
    df_trades_total['Mes_Ano'] = df_trades_total['Data_Datetime'].dt.to_period('M')
    meses_historicos = sorted(df_trades_total['Mes_Ano'].dropna().unique())
    
    lista_evolucao_mensal = []
    
    # Copia o estado final absoluto (Presente)
    carteira_loop = {tk: dados['quantidade'] for tk, dados in carteira_atual.items()}
    custo_loop = {tk: dados['custo_total'] for tk, dados in carteira_atual.items()}
    
    # Varre a linha do tempo de trás para frente (Do mês mais recente para o mais antigo)
    for mes in reversed(meses_historicos):
        chave_mes = mes.strftime('%Y-%m')
        
        # Salva a foto consolidada do mês antes de regredir as operações dele
        for tk in carteira_loop.keys():
            if carteira_loop[tk] > 0:
                lista_evolucao_mensal.append({
                    'Mes_Ano': mes,
                    'Chave_Merge': chave_mes,
                    'Ticker': tk,
                    'Quantidade': carteira_loop[tk],
                    'Custo_Total': custo_loop[tk]
                })
        
        # Pega as operações que aconteceram estritamente NESTE mês para desfazê-las na regressão
        ops_do_mes = df_trades_total[df_trades_total['Mes_Ano'] == mes]
        for _, row in ops_do_mes.iterrows():
            tk = row['Ticker']
            mov = row[col_movimentacao]
            tipo = str(row[col_sentido]).strip()
            qtd = float(row['Quantidade_Num'])
            valor = float(row['Valor_Num'])
            
            if tk in carteira_loop:
                if mov in ['Transferência - Liquidação', 'COMPRA / VENDA']:
                    if tipo == 'Credito': # Se foi uma compra, regredindo no tempo nós tiramos o saldo e o custo
                        carteira_loop[tk] -= qtd
                        custo_loop[tk] -= valor
                    elif tipo == 'Debito': # Se foi uma venda, regredindo no tempo nós devolvemos o saldo
                        carteira_loop[tk] += qtd
                        # O custo volta estimado baseado no último ponto conhecido
                        if carteira_loop[tk] > 0:
                            custo_loop[tk] += valor
                elif mov == 'Desdobro':
                    carteira_loop[tk] -= qtd

    df_evolucao_bruta = pd.DataFrame(lista_evolucao_mensal)
    
    if not df_evolucao_bruta.empty:
        # Cruza com os preços históricos do Yahoo (Aba Hist_Precos)
        df_consolidado = pd.merge(df_evolucao_bruta, df_precos_historicos, on=['Chave_Merge', 'Ticker'], how='left')
        
        # Caso o Yahoo falhe em algum mês antigo, calcula o preço médio da época como proteção
        df_consolidado['Preco_Medio_Epoca'] = df_consolidado['Custo_Total'] / df_consolidado['Quantidade']
        df_consolidado['Preco_Mercado'] = df_consolidado['Preco_Mercado'].fillna(df_consolidado['Preco_Medio_Epoca']).fillna(0)
        
        df_consolidado['Patrimonio_Mercado'] = df_consolidado['Quantidade'] * df_consolidado['Preco_Mercado']
        
        # Agrupa por mês para gerar as duas linhas perfeitas do gráfico
        df_portfolio_mensal = df_consolidado.groupby('Mes_Ano').agg({
            'Custo_Total': 'sum',
            'Patrimonio_Mercado': 'sum'
        }).reset_index().sort_values('Mes_Ano')
        
        df_portfolio_mensal['Mês_Exibição'] = df_portfolio_mensal['Mes_Ano'].dt.strftime('%m/%Y')
        
        # Garante matematicamente e por decreto que o último ponto seja RIGOROSAMENTE igual ao card
        df_portfolio_mensal.iloc[-1, df_portfolio_mensal.columns.get_loc('Custo_Total')] = total_investido
        df_portfolio_mensal.iloc[-1, df_portfolio_mensal.columns.get_loc('Patrimonio_Mercado')] = patrimonio_total
    else:
        df_portfolio_mensal = pd.DataFrame()

    # --- CÁLCULO DE PROVENTOS ---
    df_prov = df_mov[df_mov[col_movimentacao].isin(['Rendimento', 'Juros Sobre Capital Próprio'])].copy()
    df_prov['Valor_Num'] = pd.to_numeric(df_prov[col_valor], errors='coerce').fillna(0)
    total_dividendos = df_prov['Valor_Num'].sum()
    lucro_total = ganho_capital + total_dividendos
    
    df_prov['AnoMes'] = pd.to_datetime(df_prov[col_data], errors='coerce').dt.to_period('M')
    if not df_prov.empty:
        ultimo_mes_valido = df_prov.sort_values('AnoMes')['AnoMes'].iloc[-1]
        ultimo_provento_mensal = df_prov[df_prov['AnoMes'] == ultimo_mes_valido]['Valor_Num'].sum()
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
    # RENDERIZAÇÃO DA INTERFACE
    # ==============================================================================
    st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
    aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Outras Análises"])
    
    with aba_resumo:
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

        # Gráficos paralelos
        g_col1, g_col2 = st.columns([6, 4])
        
        with g_col1:
            if not df_portfolio_mensal.empty:
                fig_lin = go.Figure()
                fig_lin.add_trace(go.Scatter(
                    x=df_portfolio_mensal['Mês_Exibição'], 
                    y=df_portfolio_mensal['Patrimonio_Mercado'],
                    mode='lines+markers',
                    name='Valor de Mercado',
                    line=dict(color='#2E8B57', width=3),
                    marker=dict(size=5),
                    hovertemplate='<b>Mês:</b> %{x}<br><b>Mercado:</b> R$ %{y:,.2f}<extra></extra>'
                ))
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
    st.error(f"❌ Erro no processamento do painel: {e}")
