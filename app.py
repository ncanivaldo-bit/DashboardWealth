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
# MOTOR MATRICIAL - PROCESSAMENTO DOS DADOS
# ==============================================================================
try:
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
        
        # Foto atual estática para os cartões
        df_custodia_atual = df_consolidado[df_consolidado['Chave_Merge'] == mes_atual_chave].copy()
        df_custodia_atual = df_custodia_atual[df_custodia_atual['Quantidade'] > 0]
        
        total_investido_kpi = float(df_custodia_atual['Custo_Total'].sum())
        patrimonio_market_kpi = float(df_custodia_atual['Patrimonio_Mercado_Ativo'].sum())

except Exception as e:
    st.error(f"❌ Erro crítico no motor de cálculo: {e}")

# ==============================================================================
# RENDERIZAÇÃO DA INTERFACE VISUAL
# ==============================================================================
st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Outras Análises"])

with aba_resumo:
    def formatar_br(v): return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; box-shadow: 1px 1px 3px rgba(0,0,0,0.03); min-height: 140px;">
                <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Patrimônio Atual</span>
                <div style="color: #2C3E50; font-size: 24px; font-weight: 700; margin-top: 5px; margin-bottom: 5px;">{formatar_br(patrimonio_market_kpi)}</div>
                <div style="border-top: 1px solid #E6E8EA; padding-top: 5px; font-size: 12px; color: #7F8C8D;">
                    Total Investido: <span style="color: #118DFF; font-weight:bold;">{formatar_br(total_investido_kpi)}</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; min-height: 140px;"><span style="color: #5D6D7E; font-size: 12px; font-weight: bold;">LUCRO TOTAL</span><div style="color: #2E8B57; font-size: 24px; font-weight: 700; margin-top: 5px;">R$ 0,00</div></div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; min-height: 140px;"><span style="color: #5D6D7E; font-size: 12px; font-weight: bold;">ÚLTIMO PROVENTO</span><div style="color: #2E8B57; font-size: 24px; font-weight: 700; margin-top: 5px;">R$ 0,00</div></div>""", unsafe_allow_html=True)
    with col4:
        st.markdown(f"""<div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #F8F9FA; min-height: 140px;"><span style="color: #5D6D7E; font-size: 12px; font-weight: bold;">RENTABILIDADE</span><div style="color: #2E8B57; font-size: 24px; font-weight: 700; margin-top: 5px;">0.00%</div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 🏢 1. LINHA DE CONTROLE SUPERIOR (CÓPIA EXATA DA DISTRIBUIÇÃO DA IMAGEM image_d53147.png)
    # Coluna 1 segura o título à esquerda, a 2 cria o vácuo central e a 3 empurra o seletor para a extremidade direita.
    col_titulo_grafico, col_espacador, col_filtro_tempo = st.columns([5, 4, 3])
    
    with col_titulo_grafico:
        st.markdown("<h3 style='margin: 0; padding-top: 5px; color:#2C3E50; font-size: 22px; font-weight: 600;'>Evolução do Patrimônio</h3>", unsafe_allow_html=True)
        
    with col_filtro_tempo:
        anos_disponiveis = ["Desde o início"] + sorted(list(df_consolidado['Ano_Str'].unique()), reverse=True)
        filtro_ano = st.selectbox("Período", options=anos_disponiveis, index=0, label_visibility="collapsed")

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    # Processamento do corte temporal baseado no seletor da ponta direita
    df_filtrado_grafico = df_consolidado.copy()
    if filtro_ano != "Desde o início":
        df_filtrado_grafico = df_filtrado_grafico[df_filtrado_grafico['Ano_Str'] == filtro_ano]

    # 🏁 2. GRID GRÁFICO DIVIDIDO EM 60% / 40% COM CARD BORDERS Independentes
    col_grafico_barra, col_grafico_rosca = st.columns([6, 4])

    with col_grafico_barra:
        st.markdown("""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #FFFFFF; box-shadow: 1px 1px 3px rgba(0,0,0,0.02); min-height: 385px;">
                <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Histórico Real Consolidado</span>
                <div style="margin-top: 15px;"></div>
        """, unsafe_allow_html=True)
        
        if not df_filtrado_grafico.empty:
            df_totais_mensais = df_filtrado_grafico.groupby('Mes_Ano').agg({
                'Custo_Total': 'sum',
                'Patrimonio_Mercado_Ativo': 'sum'
            }).reset_index().sort_values('Mes_Ano')
            
            df_totais_mensais['Mês_Exibição'] = df_totais_mensais['Mes_Ano'].dt.strftime('%m/%Y')
            df_totais_mensais['Valor_Aplicado'] = df_totais_mensais['Custo_Total']
            df_totais_mensais['Ganho_de_Capital'] = df_totais_mensais['Patrimonio_Mercado_Ativo'] - df_totais_mensais['Custo_Total']

            fig_barras = go.Figure()
            fig_barras.add_trace(go.Bar(
                x=df_totais_mensais['Mês_Exibição'], 
                y=df_totais_mensais['Valor_Aplicado'],
                name='Valor aplicado',
                marker_color='#1fbc74', 
                hovertemplate='<b>Aplicado:</b> R$ %{y:,.2f}<extra></extra>'
            ))
            fig_barras.add_trace(go.Bar(
                x=df_totais_mensais['Mês_Exibição'], 
                y=df_totais_mensais['Ganho_de_Capital'],
                name='Ganho de Capital',
                marker_color='#7ee0b3',
                hovertemplate='<b>Ganho Cap:</b> R$ %{y:,.2f}<extra></extra>'
            ))
            
            fig_barras.update_layout(
                margin=dict(l=40, r=10, t=10, b=10),
                height=300,
                barmode='relative',
                bargap=0.2,
                hovermode='x unified',
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(gridcolor='rgba(230,235,240,0.6)', tickprefix="R$ "),
                xaxis=dict(gridcolor='rgba(230,235,240,0.3)', type='category'),
                legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig_barras, use_container_width=True)
        else:
            st.warning("⚠️ Sem dados para este período.")
            
        st.markdown("</div>", unsafe_allow_html=True)

    with col_grafico_rosca:
        # 🎯 CONTEXTUALIZAÇÃO: O filtro de tipo de ativo agora mora dentro da moldura da rosca para limpar o topo
        st.markdown("""
            <div style="border: 1px solid #E6E8EA; border-radius: 8px; padding: 15px; background-color: #FFFFFF; box-shadow: 1px 1px 3px rgba(0,0,0,0.02); min-height: 385px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                    <span style="color: #5D6D7E; font-size: 12px; font-weight: bold; text-transform: uppercase;">Distribuição Atual</span>
                </div>
        """, unsafe_allow_html=True)
        
        # Filtro de ativos enclausurado de forma discreta na rosca
        tipos_disponiveis = ["Todos os tipos"] + sorted(list(df_consolidado['Tipo'].unique()))
        filtro_tipo = st.selectbox("Filtro Interno Tipo", options=tipos_disponiveis, index=0, label_visibility="collapsed")
        
        df_rosca_filtrada = df_custodia_atual.copy()
        if filtro_tipo != "Todos os tipos":
            df_rosca_filtrada = df_rosca_filtrada[df_rosca_filtrada['Tipo'] == filtro_tipo]
            
        if not df_rosca_filtrada.empty:
            df_rosca = df_rosca_filtrada.sort_values(by='Patrimonio_Mercado_Ativo', ascending=False).copy()
            
            labels_legendas = []
            total_mercado_rosca = df_rosca['Patrimonio_Mercado_Ativo'].sum()
            for _, row_r in df_rosca.iterrows():
                pct = (row_r['Patrimonio_Mercado_Ativo'] / total_mercado_rosca) * 100 if total_mercado_rosca > 0 else 0.0
                labels_legendas.append(f"<b>{row_r['Ticker']}</b> ({pct:.1f}%)")
            
            fig_pie = go.Figure()
            fig_pie.add_trace(go.Pie(
                labels=labels_legendas, 
                values=df_rosca['Patrimonio_Mercado_Ativo'],
                hole=0.55,
                domain=dict(x=[0.0, 0.70]),
                textinfo='none',
                hovertemplate='<b>Ativo:</b> %{label}<br><b>Valor:</b> R$ %{value:,.2f}<extra></extra>'
            ))
            
            fig_pie.update_layout(
                margin=dict(l=0, r=0, t=10, b=10),
                height=280,
                paper_bgcolor='rgba(0,0,0,0)',
                showlegend=True,
                legend=dict(
                    orientation="v", 
                    yanchor="middle", 
                    y=0.5, 
                    xanchor="left", 
                    x=0.75,
                    font=dict(size=10)
                )
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("ℹ️ Sem alocações nesta classe.")
            
        st.markdown("</div>", unsafe_allow_html=True)

with aba_alocacao:
    st.info("⚙️ Aba de alocação estruturada.")
