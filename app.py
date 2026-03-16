import streamlit as st
import pandas as pd
import mysql.connector
import plotly.express as px
import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Dashboard | MeuERP",
    page_icon="📊", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# === CSS ENTERPRISE PARA OS CARDS (KPIs) ===
st.markdown("""
    <style>
    div[data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid #dfe3e8;
        padding: 15px 20px;
        border-radius: 10px;
        border-left: 5px solid #1a73e8;
        box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

if not DB_PASSWORD: 
    st.error('Atenção: senha do banco não encontrada no arquivo .env.')

# --- 2. FUNÇÕES DE SUPORTE ---
def format_brl(valor):
    if pd.isna(valor):
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_data 
def load_data():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,        
            database=DB_NAME
        )
        
        query = """
        SELECT 
            CODIGODEBARRA, GRUPO, DESCRICAO, FABRICANTE, FORNECEDOR,
            PRECOCUSTO, PRECOVENDA, 
            ESTOQUEATUAL, ESTOQUEMINIMO 
        FROM PRODUTOS
        """
        df = pd.read_sql(query, conn)
        conn.close()
        
        cols_numericas = ['PRECOCUSTO', 'PRECOVENDA', 'ESTOQUEATUAL', 'ESTOQUEMINIMO']
        for col in cols_numericas:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
        return df
    except Exception as e:
        st.error(f"Erro Crítico na Conexão: {e}")
        return pd.DataFrame()

df = load_data()

# --- 3. INTERFACE E FILTROS ---
if not df.empty:
    
    # === BARRA LATERAL ===
    st.sidebar.title("🔍 Filtros") 
    
    termo_busca = st.sidebar.text_input("Buscar (Nome, Código ou Fornecedor)", placeholder="Ex: Coca Cola...") 
    
    st.sidebar.markdown("---")
    todos_grupos = st.sidebar.checkbox("Selecionar Todos os Grupos", value=True) 
    
    if todos_grupos:
        grupos_selecionados = df["GRUPO"].unique()
    else:
        grupos_selecionados = st.sidebar.multiselect(
            "Filtrar por Grupo", 
            options=sorted(df["GRUPO"].fillna("Sem Grupo").unique().astype(str)) 
        )

    # APLICANDO FILTROS NO DATAFRAME 
    df_filtered = df[df["GRUPO"].isin(grupos_selecionados)]
    
    if termo_busca:
        termo = termo_busca.upper()
        df_filtered = df_filtered[
            df_filtered["DESCRICAO"].str.contains(termo, case=False, na=False) | 
            df_filtered["CODIGODEBARRA"].str.contains(termo, na=False) |
            df_filtered["FORNECEDOR"].str.contains(termo, case=False, na=False)
        ]
        
    # PRINCIPAL CABEÇALHO DO DASHBOARD 
    st.title("📊 Painel de Controle de Estoque")
    st.markdown("---")

    # Cálculos para lógica das abas 
    alertas = df_filtered[df_filtered["ESTOQUEATUAL"] < df_filtered["ESTOQUEMINIMO"]]
    qtd_alertas = len(alertas)
    
    titulo_aba_alertas = f"🚨 Reposição ({qtd_alertas})" if qtd_alertas > 0 else "✅ Reposição"

    # CRIAÇÃO DAS ABAS
    tab1, tab2, tab3 = st.tabs(["📈 Visão Geral", titulo_aba_alertas, "📋 Base Completa"])

    # === ABA 1: VISÃO GERAL === 
    with tab1:
        st.header("Indicadores de Performance")
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_itens = df_filtered["ESTOQUEATUAL"].sum()
        valor_estoque = (df_filtered["ESTOQUEATUAL"] * df_filtered["PRECOCUSTO"]).sum()
        
        custo_total = df_filtered["PRECOCUSTO"].sum()
        venda_total = df_filtered["PRECOVENDA"].sum()
        margem_media = ((venda_total - custo_total) / custo_total * 100) if custo_total > 0 else 0

        col1.metric("📦 Volume em Estoque", f"{total_itens:,.0f}".replace(",", "."))
        col2.metric("💰 Valor do Estoque", format_brl(valor_estoque))
        col3.metric("📈 Margem Média Global", f"{margem_media:.1f}%")
        col4.metric("⚠️ Produtos em Alerta", f"{qtd_alertas}", delta_color="inverse" if qtd_alertas > 0 else "off")

        st.markdown("---")
        
        col_g1, col_g2 = st.columns(2)

        with col_g1: 
            st.subheader("Estoque por Grupo")
            estoque_grupo = df_filtered.groupby("GRUPO")["ESTOQUEATUAL"].sum().reset_index().sort_values("ESTOQUEATUAL", ascending=True)
            
            fig_bar = px.bar(
                estoque_grupo, 
                x="ESTOQUEATUAL", 
                y="GRUPO", 
                orientation='h',
                text_auto=True,
                color_discrete_sequence=["#1a73e8"] # Azul Google
            )
            fig_bar.update_layout(template="plotly_white", xaxis_title="Quantidade", yaxis_title=None)
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_g2: 
            st.subheader("Top 5 Fabricantes (R$ Investido)") 
            
            df_filtered["FABRICANTE"] = df_filtered["FABRICANTE"].fillna("Não Informado")
            df_filtered["VALOR_TOTAL"] = df_filtered["ESTOQUEATUAL"] * df_filtered["PRECOCUSTO"]
            
            top_fabricantes = df_filtered.groupby("FABRICANTE")["VALOR_TOTAL"].sum().reset_index().sort_values("VALOR_TOTAL", ascending=False).head(5)
            
            if not top_fabricantes.empty:
                fig_pie = px.pie(
                    top_fabricantes, 
                    values="VALOR_TOTAL", 
                    names="FABRICANTE",
                    hole=0.4 
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Sem dados suficientes para gerar o gráfico de pizza.")

    # === ABA 2: RELATÓRIO DE COMPRAS === 
    with tab2:
        st.header("Relatório de Sugestão de Compras")
        
        if qtd_alertas > 0:
            st.warning(f"⚠️ Atenção: {qtd_alertas} produtos estão abaixo do estoque mínimo estabelecido!")
            
            df_compra = alertas.copy()
            df_compra["QTD_COMPRA"] = df_compra["ESTOQUEMINIMO"] - df_compra["ESTOQUEATUAL"] 
            df_compra["INVESTIMENTO"] = df_compra["QTD_COMPRA"] * df_compra["PRECOCUSTO"] 
            
            total_investimento = df_compra["INVESTIMENTO"].sum() 
            
            st.info(f"💸 Investimento estimado para regularizar o estoque: **{format_brl(total_investimento)}**") 

            tabela_final = df_compra[[
                "CODIGODEBARRA", "DESCRICAO", "FORNECEDOR", 
                "ESTOQUEATUAL", "ESTOQUEMINIMO", 
                "QTD_COMPRA", "INVESTIMENTO"
            ]].sort_values("INVESTIMENTO", ascending=False)
            
            tabela_final.columns = ["Código", "Produto", "Fornecedor", "Atual", "Mínimo", "Comprar (+)", "Custo Estimado"]

            st.dataframe(
                tabela_final.style.format({"Custo Estimado": "R$ {:,.2f}"}), 
                use_container_width=True,
                hide_index=True # Esconde aquele índice numérico feio (0, 1, 2...)
            )

            csv = tabela_final.to_csv(index=False, sep=';', decimal=',') 
            st.download_button(
                label="📥 Baixar Pedido de Compra (.csv)",
                data=csv,
                file_name="pedido_compra.csv",
                mime="text/csv"
            )
        else:
            st.success("✅ Tudo certo! Seu estoque está saudável.")

    # === ABA 3: DADOS BRUTOS === 
    with tab3: 
        st.header("Base de Dados Completa")
        st.dataframe(
            df_filtered,
            use_container_width=True,
            hide_index=True
        )

else:
    st.warning("⚠️ Não foi possível carregar os dados. Verifique:")
    st.markdown("""
    1. O servidor MySQL está rodando?
    2. O banco de dados e a tabela `PRODUTOS` existem?
    3. As credenciais no arquivo `.env` estão corretas?
    """)