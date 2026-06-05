import streamlit as st
import pandas as pd
import json
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Configuração de tela limpa
st.set_page_config(page_title="PREVPRIV | Painel", page_icon="📊", layout="wide")
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
# PROCESSAMENTO DOS DADOS (MÉTODO COLAB)
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
    
    # Unifica as mudanças históricas de Ticker
    df_mov['Ticker'] = df_mov['Ticker'].replace('MALL11', 'PMLL11')
    df_mov['Ticker'] = df_mov['Ticker'].replace('CVBI11', 'PCIP11')
    
    # Força conversão numérica
    df_mov['Quantidade'] = pd.to_numeric(df_mov['Quantidade'], errors='coerce').fillna(0)
    df_mov['Valor da Operação'] = pd.to_numeric(df_mov['Valor da Operação'], errors='coerce').fillna(0)
    
    # 3. Processamento de Custódia e Preço Médio
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
        
        # Cálculos Globais dos Indicadores
        patrimonio_total = df_final['Patrimônio Atual'].sum()
        total_investido = df_final['Total Investido Ativo'].sum()
        
        # Variação Percentual Global da Carteira
        if total_investido > 0:
            variacao_global = ((patrimonio_total / total_investido) - 1) * 100
        else:
            variacao_global = 0.0
            
        # Define a cor da variação de acordo com o resultado
        cor_variacao = "#2E8B57" if variacao_global >= 0 else "#E74C3C"
        sinal_variacao = "+" if variacao_global >= 0 else ""
        
        # Formatação em formato de moeda brasileira
        str_patrimonio = f"R$ {patrimonio_total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        str_investido = f"R$ {total_investido:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        str_variacao = f"{sinal_variacao}{variacao_global:.2f}%".replace('.', ',')

        # ==============================================================================
        # RENDEREZAÇÃO DO CARTÃO PERSONALIZADO (CSS STYLING)
        # ==============================================================================
        st.markdown(f"""
            <div style="
                border: 1px solid #E6E8EA; 
                border-radius: 8px; 
                padding: 20px; 
                background-color: #F8F9FA; 
                box-shadow: 1px 1px 4px rgba(0,0,0,0.05);
                width: fit-content;
                min-width: 350px;
                margin-bottom: 25px;
            ">
                <span style="color: #5D6D7E; font-size: 14px; font-weight: bold; uppercase;">PATRIMÔNIO ATUAL</span>
                <div style="color: #2C3E50; font-size: 32px; font-weight: 700; margin-top: 5px; margin-bottom: 10px;">
                    {str_patrimonio}
                </div>
                <div style="border-top: 1px solid #E6E8EA; padding-top: 10px; font-size: 14px; color: #7F8C8D;">
                    Total Investido: <strong style="color: #34495E;">{str_investido}</strong> 
                    <span style="color: {cor_variacao}; font-weight: bold; margin-left: 8px;">
                        ({str_variacao})
                    </span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Exibe a tabela pura de validação abaixo do cartão
        st.subheader("Validação de Saldos Atuais")
        st.dataframe(df_final.style.format({
            'Quantidade': '{:.0f}',
            'Preço Médio Real': 'R$ {:.2f}',
            'Preco_Atual': 'R$ {:.2f}',
            'Patrimônio Atual': 'R$ {:.2f}',
            'Total Investido Ativo': 'R$ {:.2f}'
        }), use_container_width=True)
        
    else:
        st.warning("Nenhuma operação elegível encontrada.")

except Exception as e:
    st.error(f"❌ Erro no processamento: {e}")
