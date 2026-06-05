import streamlit as st
import pandas as pd
import json
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Configuração de tela limpa
st.set_page_config(page_title="PREVPRIV | Essência", page_icon="📊", layout="wide")
st.title("PREVPRIV: Dashboard Wealth")
st.markdown("🎯 **Missão:** Do vácuo absoluto a renda passiva sustentável")
st.divider()

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
# PROCESSAMENTO DOS DADOS (MÉTODO COLAB RESTAURADO COM MUDANÇAS DE TICKER)
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
    
    # MUDANÇAS DE TICKER HISTÓRICAS (A essência do seu portfólio)
    df_mov['Ticker'] = df_mov['Ticker'].replace('MALL11', 'PMLL11')
    df_mov['Ticker'] = df_mov['Ticker'].replace('CVBI11', 'PCIP11') # Fusão CVBI -> PCIP
    
    # Força conversão numérica
    df_mov['Quantidade'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor da Operação'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)
    
    # 3. Filtro de eventos de custódia (Filtramos 'Atualização' pois o AppSheet usou para migrar o CVBI)
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
            
        # Caso 1: Desdobros normais (Soma cotas sem custo)
        if mov == 'Desdobro':
            carteira[tk]['qtd'] += qtd
            
        # Caso 2: Linha de atualização da fusão do CVBI11 para PCIP11 
        # Ignoramos a entrada das 159 cotas isoladas porque elas já foram contabilizadas no histórico como CVBI11 (que virou PCIP11)
        elif mov == 'Atualização' and tk == 'PCIP11' and qtd == 159:
            continue
            
        # Caso 3: Movimentações padrão de Mercado
        elif mov == 'Transferência - Liquidação':
            if sentido == 'Credito': # Compra
                carteira[tk]['qtd'] += qtd
                carteira[tk]['custo'] += valor_op
            elif sentido == 'Debito': # Venda
                if carteira[tk]['qtd'] > 0:
                    pm_atual = carteira[tk]['custo'] / carteira[tk]['qtd']
                    carteira[tk]['qtd'] = max(0.0, carteira[tk]['qtd'] - qtd)
                    carteira[tk]['custo'] = carteira[tk]['qtd'] * pm_atual

    # Consolida os dados processados em formato DataFrame
    linhas = []
    for tk, dados in carteira.items():
        if dados['qtd'] > 0:
            pm = dados['custo'] / dados['qtd']
            linhas.append({'Ticker': tk, 'Quantidade': dados['qtd'], 'Preço Médio Real': pm})
            
    df_consolidado = pd.DataFrame(linhas)
    
    if not df_consolidado.empty:
        # 4. Cruzamento com dados de mercado (Inf_Ativos)
        df_final = pd.merge(df_consolidado, df_inf[['Ticker', 'Preco_Atual', 'Seguimento', 'Classificacao', 'Tipo']], on='Ticker', how='left')
        df_final['Patrimônio Atual'] = df_final['Quantidade'] * df_final['Preco_Atual']
        
        patrimonio_total = df_final['Patrimônio Atual'].sum()
        st.metric(label="💰 Patrimônio Total Atualizado", value=f"R$ {patrimonio_total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        
        st.subheader("Validação de Saldos Atuais")
        st.dataframe(df_final.style.format({
            'Quantidade': '{:.0f}',
            'Preço Médio Real': 'R$ {:.2f}',
            'Preco_Atual': 'R$ {:.2f}',
            'Patrimônio Atual': 'R$ {:.2f}'
        }), use_container_width=True)
    else:
        st.warning("Nenhuma operação elegível encontrada.")

except Exception as e:
    st.error(f"❌ Erro no processamento: {e}")
