import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ==============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA
# ==============================================================================
st.set_page_config(page_title="Dashboard Wealth | PREVPRIV", page_icon="📊", layout="wide")
st.title("PREVPRIV: Dashboard Wealth")
st.markdown("🎯 **Missão:** Do vácuo absoluto a renda passiva sustentável")
st.divider()

# ==============================================================================
# 2. LIGAÇÃO SEGURA AO GOOGLE DRIVE
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
# 3. MOTOR DE DADOS E PROCESSAMENTO (A ESSÊNCIA DO COLAB)
# ==============================================================================
@st.cache_data(ttl=1800)
def carregar_e_processar_dados():
    # IDs das suas planilhas
    ID_MOV = '16GSsk9lcLnXO7YQaJmIW28mM9CrYZuJs'
    ID_INF = '1D3Nz78rVTEDMl8SOU29lXf_TMZz-sy4M'
    ID_METRICAS = '1TLXXzLqLYDJXDO8H7i1Qfk8tNReXPzFy'
    
    # 3.1 Informação dos Ativos (Preço Atual, Segmento, Tipo, etc.)
    df_inf = download_excel_from_drive(ID_INF)
    df_inf.columns = df_inf.columns.astype(str).str.strip()
    
    # Limpeza da coluna de Preço Atual vindos da planilha Inf_ativos
    if 'Preco_Atual' in df_inf.columns:
        df_inf['Preco_Atual'] = df_inf['Preco_Atual'].astype(str).str.replace('R$', '', regex=False).str.strip()
        df_inf['Preco_Atual'] = df_inf['Preco_Atual'].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        df_inf['Preco_Atual'] = pd.to_numeric(df_inf['Preco_Atual'], errors='coerce').fillna(0)
    
    # 3.2 Metas (Busca inteligente de abas)
    todas_abas_metricas = download_excel_from_drive(ID_METRICAS, sheet_name=None)
    nomes_abas = list(todas_abas_metricas.keys())
    aba_seg = next((aba for aba in nomes_abas if 'seg' in aba.lower()), nomes_abas[0])
    aba_tipo = next((aba for aba in nomes_abas if 'tipo' in aba.lower()), nomes_abas[-1])
    df_meta_seg = todas_abas_metricas[aba_seg]
    df_meta_tipo = todas_abas_metricas[aba_tipo]
    
    df_meta_seg.columns = df_meta_seg.columns.astype(str).str.strip()
    df_meta_tipo.columns = df_meta_tipo.columns.astype(str).str.strip()
    
    # 3.3 Movimentações (Aba real do AppSheet)
    todas_abas_mov = download_excel_from_drive(ID_MOV, sheet_name=None)
    df_mov = None
    for aba, df_temp in todas_abas_mov.items():
        df_temp.columns = df_temp.columns.astype(str).str.strip()
        if 'Movimentação' in df_temp.columns:
            df_mov = df_temp
            break
    if df_mov is None:
        df_mov = list(todas_abas_mov.values())[0]
        df_mov.columns = df_mov.columns.astype(str).str.strip()
        
    # Tratamento rigoroso das colunas com base no arquivo real enviado
    df_mov['Data'] = pd.to_datetime(df_mov['Data'], errors='coerce')
    df_mov['Ticker'] = df_mov['Produto'].astype(str).str.split(' - ').str[0].str.strip()
    df_mov['Quantidade'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor Líquido'] = pd.to_numeric(df_mov['Valor Líquido'], errors='coerce').fillna(0)
    df_mov['Valor da Operação'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)
    
    # 3.4 CÁLCULO DE PREÇO MÉDIO HISTÓRICO REAIS (COMPRA vs VENDA)
    df_trades = df_mov[df_mov['Movimentação'].isin(['Compra', 'Venda', 'Transferência - Liquidação'])].sort_values('Data').copy()
    
    carteira_calculada = {}
    for _, row in df_trades.iterrows():
        tk = row['Ticker']
        mov = row['Movimentação']
        qtd = row['Quantidade']
        v_liquido = abs(row['Valor Líquido']) if row['Valor Líquido'] != 0 else abs(row['Valor da Operação'])
        
        if tk not in carteira_calculada:
            carteira_calculada[tk] = {'qtd': 0.0, 'custo_total': 0.0}
            
        if mov == 'Compra' or (mov == 'Transferência - Liquidação' and qtd > 0):
            carteira_calculada[tk]['qtd'] += qtd
            carteira_calculada[tk]['custo_total'] += v_liquido
        elif mov == 'Venda' or (mov == 'Transferência - Liquidação' and qtd < 0):
            # Na venda reduz proporcionalmente a quantidade mantendo o preço médio estável
            pm_atual = carteira_calculada[tk]['custo_total'] / carteira_calculada[tk]['qtd'] if carteira_calculada[tk]['qtd'] > 0 else 0
            qtd_venda = abs(qtd)
            carteira_calculada[tk]['qtd'] = max(0.0, carteira_calculada[tk]['qtd'] - qtd_venda)
            carteira_calculada[tk]['custo_total'] = carteira_calculada[tk]['qtd'] * pm_atual

    # Transforma o dicionário calculado em DataFrame limpo
    linhas_carteira = []
    for tk, dados in carteira_calculada.items():
        if dados['qtd'] > 0:
            pm = dados['custo_total'] / dados['qtd']
            linhas_carteira.append({'Ticker': tk, 'Quantidade': dados['qtd'], 'Preco_Medio': pm})
            
    df_posicao_atual = pd.DataFrame(linhas_carteira) if linhas_carteira else pd.DataFrame(columns=['Ticker', 'Quantidade', 'Preco_Medio'])

    # 3.5 Processamento do Último Provento Recebido
    df_prov = df_mov[df_mov['Movimentação'].isin(['Rendimento', 'Juros Sobre Capital Próprio'])].copy()
    df_ultimo_prov = pd.DataFrame(columns=['Ticker', 'Ultimo_Provento'])
    if not df_prov.empty:
        df_ultimo_prov = df_prov.sort_values('Data').groupby('Ticker')['Valor da Operação'].last().reset_index()
        df_ultimo_prov.rename(columns={'Valor da Operação': 'Ultimo_Provento'}, inplace=True)

    # 3.6 RECONSTRUÇÃO DA EVOLUÇÃO PATRIMONIAL HISTÓRICA MÊS A MÊS
    df_mov['AnoMes'] = df_mov['Data'].dt.to_period('M')
    meses_historicos = sorted(df_mov['AnoMes'].dropna().unique())
    
    historico_patrimonio = []
    for am in meses_historicos:
        df_ate_o_mes = df_mov[df_mov['AnoMes'] <= am].copy()
        
        # Filtra compras/vendas até aquele mês específico
        df_trades_mes = df_ate_o_mes[df_ate_o_mes['Movimentação'].isin(['Compra', 'Venda', 'Transferência - Liquidação'])]
        
        saldo_mes = {}
        for _, r in df_trades_mes.iterrows():
            t = r['Ticker']
            m = r['Movimentação']
            q = r['Quantidade']
            if t not in saldo_mes: saldo_mes[t] = 0.0
            if m == 'Compra' or (m == 'Transferência - Liquidação' and q > 0):
                saldo_mes[t] += q
            elif m == 'Venda' or (m == 'Transferência - Liquidação' and q < 0):
                saldo_mes[t] -= abs(q)
                
        # Calcula o valor total investido somando as posições com base nas cotações da época ou atuais
        total_do_mes = 0.0
        for t, qtd in saldo_mes.items():
            if qtd > 0:
                preco = df_inf[df_inf['Ticker'] == t]['Preco_Atual'].values
                preco_atual_ref = preco[0] if len(preco) > 0 else 0.0
                total_do_mes += qtd * preco_atual_ref
                
        if total_do_mes > 0:
            historico_patrimonio.append({'Mês': str(am), 'Patrimônio': total_do_mes})
            
    df_evolucao = pd.DataFrame(historico_patrimonio) if historico_patrimonio else pd.DataFrame(columns=['Mês', 'Patrimônio'])

    return df_posicao_atual, df_inf, df_meta_seg, df_meta_tipo, df_ultimo_prov, df_evolucao

# Carrega os dados processados pela inteligência reabilitada
df_atual, df_inf, df_meta_seg, df_meta_tipo, df_ultimo_prov, df_evolucao = carregar_e_processar_dados()

# Cruzamentos Finais
df_alocacao = pd.merge(df_atual, df_inf, on='Ticker', how='left')
df_alocacao[['Classificacao', 'Tipo', 'Seguimento', 'Gestora']] = df_alocacao[['Classificacao', 'Tipo', 'Seguimento', 'Gestora']].fillna('Não Classificado')
df_alocacao['Patrimonio_Mercado'] = df_alocacao['Quantidade'] * df_alocacao['Preco_Atual']
total_patrimonio = df_alocacao['Patrimonio_Mercado'].sum()

# ==============================================================================
# 4. NAVEGAÇÃO E GRÁFICOS (FRONTEND RESTAURADO)
# ==============================================================================
aba1, aba2, aba3 = st.tabs(["📊 Visão Global (Raio-X)", "📈 Evolução Patrimonial", "⚙️ Operações e Rebalanceamento"])

with aba1:
    st.header("Análise de Risco e Composição da Carteira")
    
    df_ativo = df_alocacao.groupby('Ticker')['Patrimonio_Mercado'].sum().reset_index().sort_values(by='Patrimonio_Mercado', ascending=True)
    df_ativo['Percentual_Texto'] = (df_ativo['Patrimonio_Mercado'] / total_patrimonio * 100).apply(lambda x: f"{x:.1f}%".replace('.', ','))
    df_ativo['Valor_Texto'] = df_ativo['Patrimonio_Mercado'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
    
    df_gestora = df_alocacao.groupby('Gestora')['Patrimonio_Mercado'].sum().reset_index().sort_values(by='Patrimonio_Mercado', ascending=True)
    df_gestora['Percentual_Texto'] = (df_gestora['Patrimonio_Mercado'] / total_patrimonio * 100).apply(lambda x: f"{x:.1f}%".replace('.', ','))
    df_gestora['Valor_Texto'] = df_gestora['Patrimonio_Mercado'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))

    # Painel da Linha 1: Ativos e Divisão Tipo (Papel vs Tijolo)
    fig1 = make_subplots(rows=1, cols=2, specs=[[{'type':'xy'}, {'type':'domain'}]], subplot_titles=['<b>Alocação por Ativo</b>', '<b>Composição: Tipo</b>'], column_widths=[0.6, 0.4], horizontal_spacing=0.15)
    fig1.add_trace(go.Bar(y=df_ativo['Ticker'], x=df_ativo['Patrimonio_Mercado'], orientation='h', text=df_ativo['Percentual_Texto'], textposition='outside', marker_color='#118DFF', customdata=df_ativo['Valor_Texto'], hovertemplate='<b>Ativo:</b> %{y}<br><b>Exposição:</b> %{customdata}<br><b>Peso:</b> %{text}<extra></extra>'), row=1, col=1)
    fig1.add_trace(go.Pie(labels=df_alocacao['Classificacao'], values=df_alocacao['Patrimonio_Mercado'], hole=0.5, marker=dict(colors=['#5D6D7E', '#5DADE2', '#34495E']), textinfo='label+percent', textposition='auto'), row=1, col=2)
    fig1.update_layout(height=max(500, len(df_ativo) * 28), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
    fig1.update_xaxes(tickprefix="R$ ", gridcolor='rgba(200,200,200,0.2)', row=1, col=1)
    
    st.plotly_chart(fig1, use_container_width=True)
    st.divider()
    
    # Painel da Linha 2: Segmento e Gestoras
    fig2 = make_subplots(rows=1, cols=2, specs=[[{'type':'domain'}, {'type':'xy'}]], subplot_titles=['<b>Alocação por Segmento</b>', '<b>Concentração por Gestora</b>'], column_widths=[0.4, 0.6], horizontal_spacing=0.15)
    fig2.add_trace(go.Pie(labels=df_alocacao['Seguimento'], values=df_alocacao['Patrimonio_Mercado'], hole=0.5, marker=dict(colors=px.colors.qualitative.Set2), textinfo='label+percent', textposition='auto'), row=1, col=1)
    fig2.add_trace(go.Bar(y=df_gestora['Gestora'], x=df_gestora['Patrimonio_Mercado'], orientation='h', text=df_gestora['Percentual_Texto'], textposition='outside', marker_color='#2C3E50', customdata=df_gestora['Valor_Texto'], hovertemplate='<b>Gestora:</b> %{y}<br><b>Exposição:</b> %{customdata}<br><b>Peso:</b> %{text}<extra></extra>'), row=1, col=2)
    fig2.update_layout(height=max(400, len(df_gestora) * 32), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
    fig2.update_xaxes(tickprefix="R$ ", gridcolor='rgba(200,200,200,0.2)', row=1, col=2)
    
    st.plotly_chart(fig2, use_container_width=True)

with aba2:
    st.header("📈 Evolução Histórica do Patrimônio Líquido")
    if not df_evolucao.empty:
        fig_line = px.line(df_evolucao, x='Mês', y='Patrimônio', markers=True, text=df_evolucao['Patrimônio'].apply(lambda x: f"R$ {x:,.0f}".replace(',', '.')), title='<b>Evolução Mensal Acumulada</b> (Cotação Atual)')
        fig_line.update_traces(line_color='#2E8B57', line_width=3, marker=dict(size=8), textposition='top center')
        fig_line.update_layout(plot_bgcolor='rgba(0,0,0,0)', yaxis=dict(tickprefix="R$ ", gridcolor='rgba(200,200,200,0.2)'), xaxes=dict(gridcolor='rgba(200,200,200,0.2)'), height=500)
        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("Ainda não há dados históricos suficientes para gerar o gráfico de evolução.")

with aba3:
    st.header("GPS de Rebalanceamento Estratégico")
    
    df_tabela = pd.merge(df_alocacao, df_ultimo_prov, on='Ticker', how='left').fillna(0)
    # Variação: Percentual de distância entre preço médio e preço atual de mercado
    df_tabela['Variacao_Pct'] = ((df_tabela['Preco_Atual'] / df_tabela['Preco_Medio']) - 1) * 100
    df_tabela = pd.merge(df_tabela, df_meta_seg, on='Seguimento', how='left').fillna(0)
    
    df_tabela['Qtd_Ativos_No_Seg'] = df_tabela.groupby('Seguimento')['Ticker'].transform('count')
    df_tabela['Meta_Do_Ativo'] = df_tabela['Meta'] / df_tabela['Qtd_Ativos_No_Seg']
    df_tabela['Valor_Alvo_RS'] = df_tabela['Meta_Do_Ativo'] * total_patrimonio
    df_tabela['Aporte_Necessario'] = df_tabela['Valor_Alvo_RS'] - df_tabela['Patrimonio_Mercado']
    df_tabela = df_tabela.sort_values(by='Aporte_Necessario', ascending=False)
    
    def f_rs(v): return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    df_tabela['Acao_Str'] = df_tabela['Aporte_Necessario'].apply(lambda x: f"Comprar {f_rs(abs(x))}" if x > 0 else f"Excesso {f_rs(abs(x))}")
    df_tabela['Variacao_Str'] = df_tabela['Variacao_Pct'].apply(lambda x: f"+{abs(x):.2f}%".replace('.', ',') if x >= 0 else f"-{abs(x):.2f}%".replace('.', ','))
    
    cor_padrao, cor_vd, cor_vm = '#2C3E50', '#2E8B57', '#E74C3C'
    cores_var = [cor_vd if v >= 0 else cor_vm for v in df_tabela['Variacao_Pct']]
    cores_acao = [cor_vd if v > 0 else cor_vm for v in df_tabela['Aporte_Necessario']]
    
    matriz_cores = [
        [cor_padrao]*len(df_tabela), [cor_padrao]*len(df_tabela), [cor_padrao]*len(df_tabela), 
        [cor_padrao]*len(df_tabela), [cor_padrao]*len(df_tabela), [cor_padrao]*len(df_tabela), 
        cores_acao, cores_var, [cor_padrao]*len(df_tabela)
    ]
    
    fig_tab = go.Figure(data=[go.Table(
        columnwidth=[65, 50, 90, 90, 95, 95, 140, 85, 90],
        header=dict(values=['<b>Ativo</b>', '<b>Cotas</b>', '<b>Preço Médio</b>', '<b>Cotação Atual</b>', '<b>Saldo Atual</b>', '<b>Saldo Ideal</b>', '<b>Ordem (Meta)</b>', '<b>Variação (%)</b>', '<b>Últ. Provento</b>'], fill_color='#2C3E50', align='center', font=dict(color='white', size=13)),
        cells=dict(
            values=[
                df_tabela['Ticker'], df_tabela['Quantidade'], df_tabela['Preco_Medio'].apply(f_rs), 
                df_tabela['Preco_Atual'].apply(f_rs), df_tabela['Patrimonio_Mercado'].apply(f_rs), 
                df_tabela['Valor_Alvo_RS'].apply(f_rs), df_tabela['Acao_Str'], 
                df_tabela['Variacao_Str'], df_tabela['Ultimo_Provento'].apply(lambda x: f_rs(x) if x>0 else "-")
            ],
            fill_color=[['#F5F7FA', 'white'] * (len(df_tabela) // 2 + 1)],
            align=['center', 'center', 'right', 'right', 'right', 'right', 'center', 'center', 'right'],
            font=dict(color=matriz_cores, size=12), height=30
        )
    )])
    fig_tab.update_layout(margin=dict(t=10, b=0, l=0, r=0), height=min(800, 100 + (len(df_tabela) * 30)))
    
    st.plotly_chart(fig_tab, use_container_width=True)
