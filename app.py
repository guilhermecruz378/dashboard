import streamlit as st 
import pandas as pd 
import mysql.connector 
import plotly.express as px 
import os  
from dotenv import load_dotenv

# Configura o caminho para buscar o .env na pasta de cima
load_dotenv()

DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')

if not DB_PASSWORD: 
    st.error('Atenção: senha do banco não encontrada.')

# . CONFIGURAÇÃO DA PÁGINA 
st.set_page_config(
    page_title="Dashboard ", # nome da pagina
    page_icon="📊", # icone
    layout="wide", 
    initial_sidebar_state="expanded"
)

#  FUNÇÕES DE SUPORTE 
def format_brl(valor):
    """Transforma um número float (1234.5) em string de moeda brasileira (R$ 1.234,50)"""
    if pd.isna(valor):
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_data # impede a atualização a cada clique
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
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0) # os numeros salvos como texto viram numeros real
            
        return df
    except Exception as e: # se der erro na leitura cai aqui
        st.error(f"Erro Crítico na Conexão: {e}")
        return pd.DataFrame()

# Carrega os dados iniciais
df = load_data()

# INTERFACE E FILTROS 
if not df.empty:
    
    #  BARRA LATERAL 
    st.sidebar.title("🔍 Filtros") 
    
    termo_busca = st.sidebar.text_input("Buscar (Nome, Código ou Fornecedor)", placeholder="Ex: Coca Cola...") # busca por texto
    
    st.sidebar.markdown("---")
    todos_grupos = st.sidebar.checkbox("Selecionar Todos os Grupos", value=True) #filtro para grupos
    
    if todos_grupos:
        grupos_selecionados = df["GRUPO"].unique() # BUSCA TODOS
    else:
        grupos_selecionados = st.sidebar.multiselect(
            "Filtrar por Grupo", 
            options=sorted(df["GRUPO"].unique().astype(str)) 
        ) # BUSCA SELECIONADOS

    #  APLICANDO FILTROS NO DATAFRAME 
    df_filtered = df[df["GRUPO"].isin(grupos_selecionados)]
    
    if termo_busca:
        termo = termo_busca.upper()
        # Busca assicrona
        df_filtered = df_filtered[
            df_filtered["DESCRICAO"].str.contains(termo, case=False) | 
            df_filtered["CODIGODEBARRA"].str.contains(termo) |
            df_filtered["FORNECEDOR"].str.contains(termo, case=False)
        ] #busca assicrona
    st.sidebar.markdown("---")
    
    st.title("📊 Painel de Controle de Estoque")
    st.markdown("---")

    # Cálculos para lógica das abas 

    #PARA FAZER O ALERTA FOI NECESSARIO O CALCULO ANTES DA CRIAÇÃO DAS ABASCALCULO EM REAIS

    alertas = df_filtered[df_filtered["ESTOQUEATUAL"] < df_filtered["ESTOQUEMINIMO"]]
    qtd_alertas = len(alertas)
    
    # Define o título da aba dinamicamente
    titulo_aba_alertas = f"🚨 Reposição ({qtd_alertas})" if qtd_alertas > 0 else "✅ Reposição"

    # CRIAÇÃO DAS ABAS
    tab1, tab2, tab3 = st.tabs(["📈 Visão Geral", titulo_aba_alertas, "📋 Base Completa"])

    # ABA 1: DASHBOARD VISUAL COLUNAS E PIZZA 
    with tab1:
        st.header("Indicadores de Performance")
        
        
        col1, col2, col3, col4 = st.columns(4)
        
        total_itens = df_filtered["ESTOQUEATUAL"].sum()
        valor_estoque = (df_filtered["ESTOQUEATUAL"] * df_filtered["PRECOCUSTO"]).sum()
        
        # Evita divisão por zero no cálculo da margem
        # Markup (Margem sobre o Custo).
        custo_total = df_filtered["PRECOCUSTO"].sum()
        venda_total = df_filtered["PRECOVENDA"].sum()
        margem_media = ((venda_total - custo_total) / custo_total * 100) if custo_total > 0 else 0

        col1.metric("📦 Volume em Estoque", f"{total_itens:,.0f}".replace(",", "."))
        col2.metric("💰 Valor do Estoque", format_brl(valor_estoque))
        col3.metric("📈 Margem Média Global", f"{margem_media:.1f}%") #Markup (Margem sobre o Custo).
        col4.metric("⚠️ Produtos em Alerta", f"{qtd_alertas}", delta_color="inverse" if qtd_alertas > 0 else "off")

        st.markdown("---")
        
        # Gráficos
        col_g1, col_g2 = st.columns(2)

        with col_g1: # MOSTRANDO PRIMEIRO GRAFICO
            st.subheader("Estoque por Grupo")
            estoque_grupo = df_filtered.groupby("GRUPO")["ESTOQUEATUAL"].sum().reset_index().sort_values("ESTOQUEATUAL", ascending=True)
            
            fig_bar = px.bar(
                estoque_grupo, 
                x="ESTOQUEATUAL", 
                y="GRUPO", 
                orientation='h',
                text_auto=True,
                color_discrete_sequence=[st.get_option("theme.primaryColor") or "#0083B8"]
            )
            fig_bar.update_layout(template="plotly_white", xaxis_title="Quantidade", yaxis_title=None)
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_g2: # SEGUNDO GRÁFICO
            st.subheader("Top 5 Fabricantes (R$ Investido)") 
            
            
            # FOI NECESSÁRIO PREENCHER O VAZIO PQ O GRÁFICCO ESTAVA SUMINDO, INLCUI A STRING 'NÃO INFORMADO' 
            df_filtered["FABRICANTE"] = df_filtered["FABRICANTE"].fillna("Não Informado")
            
            # Calcula o valor total
            df_filtered["VALOR_TOTAL"] = df_filtered["ESTOQUEATUAL"] * df_filtered["PRECOCUSTO"]
            
            #Agrupa por FABRICANTE (que tem dados) em vez de FORNECEDOR -- CORREÇÃO --
            top_fabricantes = df_filtered.groupby("FABRICANTE")["VALOR_TOTAL"].sum().reset_index().sort_values("VALOR_TOTAL", ascending=False).head(5)
            
            # Verificação de Segurança: Só desenha se tiver dados
            if not top_fabricantes.empty:
                fig_pie = px.pie(
                    top_fabricantes, 
                    values="VALOR_TOTAL", 
                    names="FABRICANTE",
                    hole=0.4 # transforma a pizza numa rosca 
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Sem dados suficientes para gerar o gráfico de pizza.")
        st.header("Base de Dados Completa")
        st.dataframe(
        df_filtered,
        use_container_width=True
        )

    #  ABA 2: RELATÓRIO DE COMPRAS 
    with tab2:
        st.header("Relatório de Sugestão de Compras")
        
        if qtd_alertas > 0:
            st.warning(f"⚠️ Atenção: {qtd_alertas} produtos estão abaixo do mínimo!")
            
            # Lógica de Compra
            df_compra = alertas.copy()
            df_compra["QTD_COMPRA"] = df_compra["ESTOQUEMINIMO"] - df_compra["ESTOQUEATUAL"] # SUBTRAI OQUE TEM DO QUE DEVERIA TER
            df_compra["INVESTIMENTO"] = df_compra["QTD_COMPRA"] * df_compra["PRECOCUSTO"] # CALCULA O QUANTO DEVERIA SER INVESTIDO
            
            total_investimento = df_compra["INVESTIMENTO"].sum() # CALCULO SIMULADO PARA SABER O NECESSÁRIO PARA A REPOSIÇÃO 
            
            st.info(f"💸 Investimento estimado para regularizar: **{format_brl(total_investimento)}**") # MOSTRA O ESTIMADO

            # Preparar tabela para exibição
            tabela_final = df_compra[[
                "CODIGODEBARRA", "DESCRICAO", "FORNECEDOR", 
                "ESTOQUEATUAL", "ESTOQUEMINIMO", 
                "QTD_COMPRA", "INVESTIMENTO"
            ]].sort_values("INVESTIMENTO", ascending=False)
            
            tabela_final.columns = ["Código", "Produto", "Fornecedor", "Atual", "Mínimo", "Comprar (+)", "Custo Estimado"]

            st.dataframe(
                tabela_final.style.format({"Custo Estimado": "R$ {:,.2f}"}), 
                use_container_width=True
            )

            # Botão de Download Excel/CSV
            csv = tabela_final.to_csv(index=False, sep=';', decimal=',') # CONFIG PARA O EXCEL BRASILEIRO 
            st.download_button(
                label="📥 Baixar Pedido de Compra (.csv)",
                data=csv,
                file_name="pedido_compra.csv",
                mime="text/csv",
                help="Arquivo CSV formatado para Excel Brasil (ponto e vírgula)"
            )
        else:
            st.success("✅ Tudo certo! Seu estoque está saudável.")
            

    # --- ABA 3: DADOS BRUTOS ---
    with tab3: # OUTRA TABELA PARA VERIFICAR OQUE FICA MELHOR SEPARADO OU JUNTO DO GRÁFICO
        st.header("Base de Dados Completa")
        st.dataframe(
            df_filtered,
            use_container_width=True
        )

else:
    # Tela de erro se o banco estiver vazio ou offline
    st.warning("⚠️ Não foi possível carregar os dados. Verifique:")
    st.markdown("""
    1. O servidor MySQL está rodando?
    2. O banco de dados `davi_teste` e a tabela `PRODUTOS` existem?
    3. As credenciais (usuário/senha) no código estão corretas?
    """)