import streamlit as st
import pandas as pd
import json
import io
import plotly.graph_objects as go
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
# PROCESSAMENTO DOS DADOS (MÉTODO COLAB RESTAURADO COM HISTÓRICO REAL DE ÉPOCA)
# ==============================================================================
try:
    # IDs oficiais
    ID_MOV = '16GSsk9lcLnXO7YQaJmIW28mM9CrYZuJs'
    ID_INF = '1D3Nz78rVTEDMl8SOU29lXf_TMZz-sy4M'
    
    # 1. Carrega as tabelas
    df_mov = download_excel_from_drive(ID_MOV, sheet_name='Movimentação')
    df_inf = download_excel_from_drive(ID_INF, sheet_name='Inf_Ativos')
    
    # Limpeza profunda de cabeçalhos (Evita o erro crítico do Streamlit)
    df_mov.columns = df_mov.columns.astype(str).str.strip()
    df_inf.columns = df_inf.columns.astype(str).str.strip()
    
    # 2. Tratamento de Datas e Extração do Ticker
    df_mov['Data'] = pd.to_datetime(df_mov['Data'], format='%d/%m/%Y', errors='coerce')
    df_mov['Ticker'] = df_mov['Produto'].astype(str).str.split(' - ').str[0].str.strip()
    
    # Unifica as mudanças históricas de Ticker
    df_mov['Ticker'] = df_mov['Ticker'].replace('MALL11', 'PMLL11')
    df_mov['Ticker'] = df_mov['Ticker'].replace('CVBI11', 'PCIP11')
    
    # Força conversão numérica segura prevenindo nulos ou textos como '-' ou '#REF!'
    df_mov['Quantidade'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor da Operação'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)
    
    # Tratamento específico para aceitar variações de escrita no nome da coluna de Preço Unitário
    nome_col_preco = 'Preço unitário' if 'Preço unitário' in df_mov.columns else 'Preço Unitário'
    if nome_col_preco in df_mov.columns:
        df_mov['Preço_Unit_Tratado'] = pd.to_numeric(df_mov[nome_col_preco], errors='coerce').fillna(0)
    else:
        df_mov['Preço_Unit_Tratado'] = 0.0
        
    df_inf['Preco_Atual'] = pd.to_numeric(df_inf['Preco_Atual'], errors='coerce').fillna(0)
    
    # 3. Processamento de Custódia e Preço Médio Atual
    df_trades = df_mov[df_mov['Movimentação'].isin(['Transferência - Liquidação', 'Desdobro', 'Atualização'])].sort_values('Data').copy()
    
    carteira = {}
    for _, row in df_trades.iterrows():
        tk = row['Ticker']
        mov = row['Movimentação']
        sentido = str(row['Entrada/Saída']).strip()
        qtd = float(row['Quantidade'])
        valor_op = float(row['Valor da Operação'])
        
        if tk not in carteira:
            carteira[tk] = {'qtd': 0.0, 'custo': 0.0}
            
        if mov == 'Desdobro':
            carteira[tk]['qtd'] += qtd
        elif mov == 'Atualização' and tk == 'PCIP11' and qtd == 159:
            continue
        elif mov == 'Transferência - Liquidação':
            if sentido == 'Credito': # Compra
                carteira[tk]['qtd'] += qtd
                carteira[tk]['custo'] += valor_op
            elif sentido == 'Debito': # Venda
                if carteira[tk]['qtd'] > 0:
                    pm_atual = carteira[tk]['custo'] / carteira[tk]['qtd']
                    carteira[tk]['qtd'] = max(0.0, carteira[tk]['qtd'] - qtd)
                    carteira[tk]['custo'] = carteira[tk]['qtd'] * pm_atual

    # Consolida os dados processados em DataFrame
    linhas = []
    for tk, dados in carteira.items():
        if dados['qtd'] > 0:
            pm = dados['custo'] / dados['qtd']
            linhas.append({'Ticker': tk, 'Quantidade': dados['qtd'], 'Preço Médio Real': pm, 'Total Investido Ativo': dados['custo']})
            
    df_consolidado = pd.DataFrame(linhas)
    
    if not df_consolidado.empty:
        # 4. Cruzamento com dados de mercado (Inf_Ativos)
        df_final = pd.merge(df_consolidado, df_inf[['Ticker', 'Preco_Atual', 'Seguimento', 'Classificacao', 'Tipo']], on='Ticker', how='left')
        df_final['Patrimônio Atual'] = df_final['Quantidade'] * df_final['Preco_Atual']
        
        # --- CÁLCULO DOS VALORES GLOBAIS ---
        patrimonio_total = df_final['Patrimônio Atual'].sum()
        total_investido = df_final['Total Investido Ativo'].sum()
        ganho_capital = patrimonio_total - total_investido
        
        # Extração de Dividendos Acumulados
        df_prov = df_mov[df_mov['Movimentação'].isin(['Rendimento', 'Juros Sobre Capital Próprio'])].copy()
        total_dividendos = df_prov['Valor da Operação'].sum()
        
        # Lucro Total
        lucro_total = ganho_capital + total_dividendos
        
        # Último Provento Mensal Pago
        df_prov['AnoMes'] = df_prov['Data'].dt.to_period('M')
        if not df_prov.empty:
            ultimo_mes_valido = df_prov.sort_values('Data')['AnoMes'].iloc[-1]
            ultimo_provento_mensal = df_prov[df_prov['AnoMes'] == ultimo_mes_valido]['Valor da Operação'].sum()
            str_mes_prov = ultimo_mes_valido.strftime('%m/%Y')
        else:
            ultimo_provento_mensal = 0.0
            str_mes_prov = "-"

        # Rentabilidade e Variação Absoluta
        rentabilidade_pct = (ganho_capital / total_investido * 100) if total_investido > 0 else 0.0
        
        # --- RECONSTRUÇÃO HISTÓRICA COM PREÇOS REAIS DE ÉPOCA ---
        df_trades['AnoMes'] = df_trades['Data'].dt.to_period('M')
        meses_historicos = sorted(df_trades['AnoMes'].dropna().unique())
        
        historico_patrimonio = []
        for am in meses_historicos:
            df_ate_o_mes = df_trades[df_trades['AnoMes'] <= am]
            
            carteira_mes = {}
            for _, r in df_ate_o_mes.iterrows():
                t = r['Ticker']
                m = r['Movimentação']
                s = str(r['Entrada/Saída']).strip()
                q = float(r['Quantidade'])
                v = float(r['Valor da Operação'])
                
                if t not in carteira_mes:
                    carteira_mes[t] = {'qtd': 0.0, 'custo': 0.0}
                if m == 'Desdobro':
                    carteira_mes[t]['qtd'] += q
                elif m == 'Atualização' and t == 'PCIP11' and q == 159:
                    continue
                elif m == 'Transferência - Liquidação':
                    if s == 'Credito':
                        carteira_mes[t]['qtd'] += q
                        carteira_mes[t]['custo'] += v
                    elif s == 'Debito':
                        if carteira_mes[t]['qtd'] > 0:
                            pm_m = carteira_mes[t]['custo'] / carteira_mes[t]['qtd']
                            carteira_mes[t]['qtd'] = max(0.0, carteira_mes[t]['qtd'] - q)
                            carteira_mes[t]['custo'] = carteira_mes[t]['qtd'] * pm_m
                            
            patr_do_mes = 0.0
            inv_do_mes = 0.0
            for t, dados_m in carteira_mes.items():
                if dados_m['qtd'] > 0:
                    inv_do_mes += dados_m['custo']
                    df_filtro_epoca = df_ate_o_mes[(df_ate_o_mes['Ticker'] == t) & (df_mov['Preço_Unit_Tratado'] > 0)]
                    if not df_filtro_epoca.empty:
                        preco_epoca = float(df_filtro_epoca.sort_values('Data').iloc[-1]['Preço_Unit_Tratado'])
                    else:
                        preco_f = df_inf[df_inf['Ticker'] == t]['Preco_Atual'].values
                        preco_epoca = float(preco_f[0]) if len(preco_f) > 0 else 0.0
                        
                    patr_do_mes += dados_m['qtd'] * preco_epoca
                    
            if patr_do_mes > 0 or inv_do_mes > 0:
                historico_patrimonio.append({
                    'Mês': am.strftime('%m/%Y'), 
                    'Patrimônio (Mercado)': patr_do_mes,
                    'Total Investido': inv_do_mes
                })
                
        df_evolucao = pd.DataFrame(historico_patrimonio)

        # --- ESTILIZAÇÃO DE STRINGS ---
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
        # CRIAÇÃO DAS ABAS (NAVEGAÇÃO)
        # ==============================================================================
        st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
        aba_resumo, aba_alocacao = st.tabs(["📝 Resumo", "⚙️ Outras Análises"])
        
        with aba_resumo:
            # Linha de KPIs (Trancados)
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
            # LINHA DE GRÁFICOS: 60% COMPARATIVO ÉPOCA | 40% ROSCA COM LEG PERCENTUAL APENAS
            # ==============================================================================
            g_col1, g_col2 = st.columns([6, 4])
            
            with g_col1:
                if not df_evolucao.empty:
                    fig_lin = go.Figure()
                    fig_lin.add_trace(go.Scatter(
                        x=df_evolucao['Mês'], 
                        y=df_evolucao['Patrimônio (Mercado)'],
                        mode='lines+markers',
                        name='Valor de Mercado',
                        line=dict(color='#2E8B57', width=3),
                        marker=dict(size=5),
                        hovertemplate='<b>Mês:</b> %{x}<br><b>Mercado:</b> R$ %{y:,.2f}<extra></extra>'
                    ))
                    fig_lin.add_trace(go.Scatter(
                        x=df_evolucao['Mês'], 
                        y=df_evolucao['Total Investido'],
                        mode='lines+markers',
                        name='Total Investido',
                        line=dict(color='#118DFF', width=2, dash='dot'),
                        marker=dict(size=5),
                        hovertemplate='<b>Mês:</b> %{x}<br><b>Investido:</b> R$ %{y:,.2f}<extra></extra>'
                    ))
                    fig_lin.update_layout(
                        title="<b>Evolução Patrimonial: Investido vs Mercado</b>",
                        title_font=dict(size=14, color='#2C3E50'),
                        margin=dict(l=40, r=20, t=40, b=30),
                        height=400,
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        yaxis=dict(gridcolor='rgba(230,235,240,0.6)', tickprefix="R$ "),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig_lin, use_container_width=True)
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
                st.plotly_chart(fig_pie, use_container_width=True)

        with aba_alocacao:
            st.info("Esta aba está pronta para receber O GPS de Rebalanceamento Estratégico nos próximos passos.")
        
    else:
        st.warning("Nenhuma operação elegível encontrada.")

except Exception as e:
    st.error(f"❌ Erro crítico mapeado no processamento: {e}")
