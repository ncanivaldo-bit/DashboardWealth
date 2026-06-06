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
# CONEXÃO COM O GOOGLE DRIVE (Ajustada para Google Sheets Nativos)
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
    
    # Como as planilhas agora são nativas do Google Sheets, usamos export_media
    # para convertê-las em formato de tabela na memória de forma ultra estável
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
# PROCESSAMENTO DOS DADOS - MOTOR DA MAESTRIA DO COLAB
# ==============================================================================
try:
    # 📝 SEUS NOVOS IDS OFICIAIS DO GOOGLE SHEETS NATIVO
    ID_MOV = '1jb-uqvlTQ7j07p7akDjYiXew1387VKipXch72x755vM' # Planilha Movimentação
    ID_INF = '1FcBDlaArTQrkYdmDFbqbwObl5qmPy8K2sxxiE0RE8QE' # Planilha Inf_Ativos
    
    # 1. Carrega as tabelas direto do ecossistema nativo
    df_mov = download_excel_from_drive(ID_MOV, sheet_name=0) # Primeira aba de movimentações
    df_inf = download_excel_from_drive(ID_INF, sheet_name=0) # Primeira aba de informações estáticas
    
    # Download da nova aba de preços históricos que o script do Colab gerou
    df_precos_historicos = download_excel_from_drive(ID_INF, sheet_name='Hist_Precos')
    
    # Limpeza preventiva de cabeçalhos
    df_mov.columns = df_mov.columns.astype(str).str.strip()
    df_inf.columns = df_inf.columns.astype(str).str.strip()
    df_precos_historicos.columns = df_precos_historicos.columns.astype(str).str.strip()
    
    # 2. Tratamento de Datas e Extração do Ticker básico
    df_mov['Data'] = pd.to_datetime(df_mov['Data'], format='%d/%m/%Y', errors='coerce')
    df_mov['Ticker'] = df_mov['Produto'].astype(str).str.split(' - ').str[0].str.strip()
    
    # Unifica as mudanças históricas de Ticker (MALL e CVBI)
    df_mov['Ticker'] = df_mov['Ticker'].replace('MALL11', 'PMLL11')
    df_mov['Ticker'] = df_mov['Ticker'].replace('CVBI11', 'PCIP11')
    
    # Força conversão numérica segura contra strings inválidas
    df_mov['Quantidade'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor da Operação'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)
    df_inf['Preco_Atual'] = pd.to_numeric(df_inf['Preco_Atual'], errors='coerce').fillna(0)
    df_precos_historicos['Preco_Mercado'] = pd.to_numeric(df_precos_historicos['Preco_Mercado'], errors='coerce').fillna(0)
    
    # 3. Processamento de Custódia e Evolução Cronológica do Portfólio
    df_trades = df_mov[df_mov['Movimentação'].isin(['Transferência - Liquidação', 'Desdobro', 'Atualização', 'COMPRA / VENDA'])].sort_values('Data').copy()
    
    carteira = {}
    historico_detalhado = []
    
    # Execução do laço cronológico idêntico ao do Colab para montar o histórico de saldos
    for _, row in df_trades.iterrows():
        ticker = row['Ticker']
        data = row['Data']
        mov = row['Movimentação']
        tipo = str(row['Entrada/Saída']).strip()
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
            
    # Agrupamento mensal resampled por fim de mês ('ME') do Colab
    df_hist_ativos = pd.DataFrame(historico_detalhado)
    if not df_hist_ativos.empty:
        df_hist_ativos['Data'] = pd.to_datetime(df_hist_ativos['Data'])
        
        df_mensal_ativos = (df_hist_ativos
                            .set_index('Data')
                            .groupby('Ticker')[['Quantidade', 'Custo_Total', 'Preco_Medio']]
                            .resample('ME')
                            .last()
                            .ffill()
                            .reset_index())
        
        # Filtro de segurança contra preenchimento fantasma de ativos já encerrados
        df_mensal_ativos.loc[df_mensal_ativos['Quantidade'] <= 0, 'Custo_Total'] = 0.0
        
        df_mensal_ativos['Chave_Merge'] = df_mensal_ativos['Data'].dt.strftime('%Y-%m')
        df_mensal_ativos['Mes_Ano'] = df_mensal_ativos['Data'].dt.to_period('M')
        
        # 4. CRUZAMENTO COM A BASE HISTÓRICA DO DRIVE
        if not df_precos_historicos.empty:
            df_consolidado = pd.merge(df_mensal_ativos, df_precos_historicos, on=['Chave_Merge', 'Ticker'], how='left')
        else:
            df_consolidado = df_mensal_ativos.copy()
            df_consolidado['Preco_Mercado'] = np.nan
            
        # Lógica de preenchimento de segurança do Colab (ffill e fallback para o Preço Médio)
        df_consolidado['Preco_Mercado'] = df_consolidado.groupby('Ticker')['Preco_Mercado'].ffill()
        df_consolidado['Preco_Mercado'] = df_consolidado['Preco_Mercado'].fillna(df_consolidado['Preco_Medio'])
        
        # 5. Cálculo final da evolução de mercado
        df_consolidado['Patrimonio_Mercado'] = df_consolidado['Quantidade'] * df_consolidado['Preco_Mercado']
        
        df_portfolio_mensal = df_consolidado.groupby('Mes_Ano').agg({
            'Custo_Total': 'sum',
            'Patrimonio_Mercado': 'sum'
        }).reset_index()
        
        df_portfolio_mensal['Mês_Exibição'] = df_portfolio_mensal['Mes_Ano'].dt.strftime('%m/%Y')
    else:
        df_portfolio_mensal = pd.DataFrame()

    # --- CÁLCULO DOS CARDS DE KPI (MOMENTO ATUAL REAL) ---
    linhas_kpi = []
    for tk, dados in carteira.items():
        if dados['quantidade'] > 0:
            linhas_kpi.append({
                'Ticker': tk, 
                'Quantidade': dados['quantidade'], 
                'Preço Médio Real': dados['preco_medio'], 
                'Total Investido Ativo': dados['custo_total']
            })
    df_final = pd.DataFrame(linhas_kpi)
    
    df_final = pd.merge(df_final, df_inf[['Ticker', 'Preco_Atual', 'Seguimento', 'Classificacao', 'Tipo']], on='Ticker', how='left')
    df_final['Patrimônio Atual'] = df_final['Quantidade'] * df_final['Preco_Atual']

    # Indicadores absolutos trancados nos cards
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

    # Estilização padrão monetário Brasil
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
        # Linha de KPIs (Intacta e Perfeita)
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
        # GRÁFICOS: 60% EVOLUÇÃO DO COLAB REAL | 40% ROSCA COM LEGENDA DE PERCENTUAIS
        # ==============================================================================
        g_col1, g_col2 = st.columns([6, 4])
        
        with g_col1:
            if not df_portfolio_mensal.empty:
                fig_lin = go.Figure()
                # Linha Verde de Mercado com os fechamentos históricos crus da nova aba
                fig_lin.add_trace(go.Scatter(
                    x=df_portfolio_mensal['Mês_Exibição'], 
                    y=df_portfolio_mensal['Patrimonio_Mercado'],
                    mode='lines+markers',
                    name='Valor de Mercado',
                    line=dict(color='#2E8B57', width=3),
                    marker=dict(size=5),
                    hovertemplate='<b>Mês:</b> %{x}<br><b>Mercado:</b> R$ %{y:,.2f}<extra></extra>'
                ))
                # Linha Azul de Investimento Total Acumulado Puro
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
            
            # Legenda de Canto: Estritamente Ticker e Percentual limpo
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
