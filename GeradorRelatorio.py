import math
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão de Produção & Qualidade", layout="wide")
TEMPLATE_GRAFICO = "plotly_white"

# --- CSS PARA IMPRESSÃO (PAISAGEM + QUEBRA DE PÁGINA) ---
st.markdown("""
    <style>
        @media print {
            @page { 
                size: landscape; 
                margin: 0.5cm; 
            }
            /* Classe que força a quebra de página */
            .pagebreak { 
                page-break-before: always; 
                break-before: page;
            }
            /* Esconde menus e botões na impressão */
            [data-testid="stSidebar"], header, footer, [data-testid="stToolbar"], .stAppHeader, .stDeployButton { 
                display: none !important; 
            }
            body { 
                -webkit-print-color-adjust: exact !important; 
                print-color-adjust: exact !important; 
            }
            /* Tira espaçamentos desnecessários para caber na folha */
            .main .block-container { 
                max-width: 100% !important; 
                width: 100% !important; 
                padding: 1rem 0 !important; 
            }
            .js-plotly-plot { 
                width: 100% !important; 
                page-break-inside: avoid !important;
            }
            .stDataFrame, .stTable {
                width: 100% !important;
                page-break-inside: avoid !important;
            }
        }
    </style>
""", unsafe_allow_html=True)

st.title("🏭 Dashboard de Controle de Retidos")

# --- FUNÇÕES AUXILIARES ---
def limpar_numero(val):
    if pd.isna(val): return 0.0
    if isinstance(val, (int, float)): return float(val)
    val = str(val).strip().replace('R$', '').replace(' ', '')
    val = val.replace('.', '').replace(',', '.')
    try: return float(val)
    except: return 0.0

@st.cache_data
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Dados')
    return output.getvalue()

def truncar_duas_casas(valor):
    if pd.isna(valor) or valor == float('inf') or valor == float('-inf'):
        return 0.0
    return math.floor(valor * 100) / 100

def carregar_arquivo_sem_cabecalho(uploaded_file):
    """Carrega o arquivo ignorando nomes originais. Usa Calamine para planilhas sujas do ERP."""
    try:
        uploaded_file.seek(0)
        if uploaded_file.name.lower().endswith('.csv'):
            try: return pd.read_csv(uploaded_file, header=None, sep=None, engine='python')
            except:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, header=None, sep=';', engine='python')
        else: return pd.read_excel(uploaded_file, header=None, engine='calamine')
    except Exception as e:
        st.error(f"Erro detalhado ao ler '{uploaded_file.name}': {e}")
        return None

# --- FUNÇÕES DE CÁLCULO E GRÁFICO ---
def adicionar_linha_geral(df_original, nome_grupo, meta_pct):
    df_filt = df_original[df_original['Grupo_Relatorio'] == nome_grupo].copy()
    if df_filt.empty: return df_filt

    total_prod = df_filt['M2_Produzido'].sum()
    total_ret = df_filt['M2_Retido'].sum()
    meta_m2_total = total_prod * (meta_pct / 100)
    saldo_total = meta_m2_total - total_ret
    pct_calc = (total_ret / total_prod * 100) if total_prod > 0 else 0
    pct_geral = truncar_duas_casas(pct_calc)
    
    row_geral = pd.DataFrame({
        'Grupo_Relatorio': [nome_grupo], 'Equipe': ['Média Geral'], 
        'M2_Produzido': [total_prod], 'M2_Retido': [total_ret],
        'Meta_M2': [meta_m2_total], 'Saldo_M2': [saldo_total], '% Realizado': [pct_geral]
    })
    
    df_filt['Equipe'] = df_filt['Equipe'].astype(str)
    df_final = pd.concat([df_filt, row_geral], ignore_index=True)
    df_final['Ordem'] = df_final['Equipe'].apply(lambda x: 1 if x == 'Média Geral' else 0)
    df_final = df_final.sort_values(by=['Ordem', 'Equipe'])
    return df_final

def criar_tabela_grafica(df, meta_pct, altura=220):
    if df.empty: return None
    cor_texto_pct = ['#E74C3C' if v > meta_pct else '#27AE60' for v in df['% Realizado']]
    cor_texto_saldo = ['#E74C3C' if v < 0 else '#27AE60' for v in df['Saldo_M2']]
    
    fig = go.Figure(data=[go.Table(
        header=dict(values=['<b>Grupo</b>', '<b>Equipe</b>', '<b>Produção</b>', '<b>Meta (m²)</b>', '<b>Retido (m²)</b>', '<b>Saldo</b>', '<b>% Perda</b>'],
                    fill_color='#2E86C1', align='center', font=dict(color='white', size=11)),
        cells=dict(values=[df['Grupo_Relatorio'], df['Equipe'], 
                           [f"{v:,.2f}" for v in df['M2_Produzido']], 
                           [f"{v:,.2f}" for v in df['Meta_M2']], 
                           [f"{v:,.2f}" for v in df['M2_Retido']], 
                           [f"{v:,.2f}" for v in df['Saldo_M2']], 
                           [f"{v:.2f}%" for v in df['% Realizado']]],
                   fill_color='#F7F9F9', align='center',
                   font=dict(color=['black', 'black', 'black', 'black', 'black', cor_texto_saldo, cor_texto_pct], size=10),
                   height=25))])
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=altura)
    return fig

def criar_grafico_evolucao_com_geral(df_prod, df_ret, nome_grupo, meta_pct):
    df_p = df_prod[df_prod['Grupo_Relatorio'] == nome_grupo].copy()
    df_r = df_ret[df_ret['Grupo_Relatorio'] == nome_grupo].copy()
    if df_p.empty and df_r.empty: return None
    
    p_eq = df_p.groupby(['mes_ano', 'Equipe'])['metragem_real'].sum().reset_index().rename(columns={'metragem_real': 'M2_Produzido'})
    r_eq = df_r.groupby(['mes_ano', 'Equipe'])['m2_real'].sum().reset_index().rename(columns={'m2_real': 'M2_Retido'})
    
    if not df_p.empty:
        p_tot = df_p.groupby(['mes_ano'])['metragem_real'].sum().reset_index().rename(columns={'metragem_real': 'M2_Produzido'})
        p_tot['Equipe'] = 'Média Geral'
    else: p_tot = pd.DataFrame()

    if not df_r.empty:
        r_tot = df_r.groupby(['mes_ano'])['m2_real'].sum().reset_index().rename(columns={'m2_real': 'M2_Retido'})
        r_tot['Equipe'] = 'Média Geral'
    else: r_tot = pd.DataFrame()

    df_final = pd.merge(pd.concat([p_eq, p_tot]), pd.concat([r_eq, r_tot]), on=['mes_ano', 'Equipe'], how='outer').fillna(0)
    df_final['Meta_M2'] = df_final['M2_Produzido'] * (meta_pct / 100)
    df_final['Cor_Barra'] = df_final.apply(lambda row: '#27AE60' if row['M2_Retido'] <= row['Meta_M2'] else '#E74C3C', axis=1)
    df_final['Ordem_Equipe'] = df_final['Equipe'].apply(lambda x: 1 if x == 'Média Geral' else 0)
    df_final = df_final.sort_values(by=['mes_ano', 'Ordem_Equipe', 'Equipe'])
    
    df_final['Label_X'] = df_final['Equipe'].astype(str)
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_final['Label_X'], y=df_final['M2_Retido'], marker_color=df_final['Cor_Barra'],
                         text=[f"{v:,.2f}" for v in df_final['M2_Retido']], textposition='inside', name='Realizado'))
    
    fig.add_trace(go.Scatter(
        x=df_final['Label_X'], 
        y=df_final['Meta_M2'], 
        mode='lines+markers+text',
        text=[f"{v:,.1f}" for v in df_final['Meta_M2']], 
        textposition="top center",
        textfont=dict(color='black'), 
        marker=dict(symbol='line-ew', color='black', size=10, line=dict(width=2)), 
        line=dict(color='black', dash='dot'),
        name='Meta M²'
    ))
    
    max_val = max(df_final['M2_Retido'].max(), df_final['Meta_M2'].max()) if not df_final.empty else 100
    fig.update_layout(title=f"Perda em M²", yaxis=dict(range=[0, max_val * 1.3]), template=TEMPLATE_GRAFICO, showlegend=False)
    return fig

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("1. Upload de Dados")
    file_prod = st.file_uploader("📂 Arquivo de Produção", type=["xlsx", "csv"])
    file_ret = st.file_uploader("📂 Arquivo de Retidos", type=["xlsx", "csv"])
    st.markdown("---")
    st.header("2. Metas Gerais")
    META_PCT = st.slider("🎯 % Máximo de Perda (Geral)", 0.0, 5.0, 0.5, 0.1)
    st.markdown("---")
    st.header("3. Análise Específica")
    st.info("Configuração para a aba 'Análise por Motivo'")

# --- LÓGICA PRINCIPAL ---
if file_prod and file_ret:
    df_prod_raw = carregar_arquivo_sem_cabecalho(file_prod)
    df_ret_raw = carregar_arquivo_sem_cabecalho(file_ret)

    if df_prod_raw is None or df_ret_raw is None:
        st.stop()

    # =========================================================================
    # ⚙️ CONFIGURAÇÃO DOS ÍNDICES DAS COLUNAS
    # =========================================================================
    IDX_PROD_DATA = 0      
    IDX_PROD_FORNO = 1     
    IDX_PROD_EQUIPE = 2    
    IDX_PROD_METRAGEM = 6  

    IDX_RET_MOTIVO = 0     
    IDX_RET_DATA = 1       
    IDX_RET_FORNO = 2      
    IDX_RET_EQUIPE = 3     
    IDX_RET_M2 = 8         
    # =========================================================================

    try:
        df_prod = pd.DataFrame()
        df_prod['Metragem/Produção'] = df_prod_raw.iloc[:, IDX_PROD_METRAGEM]
        df_prod['Equipe'] = df_prod_raw.iloc[:, IDX_PROD_EQUIPE]
        df_prod['Forno/Linha'] = df_prod_raw.iloc[:, IDX_PROD_FORNO]
        df_prod['Data'] = df_prod_raw.iloc[:, IDX_PROD_DATA]
        
        col_metragem = 'Metragem/Produção'
        col_equipe_p = 'Equipe'
        col_forno_p = 'Forno/Linha'
        col_data_p = 'Data'
    except IndexError:
        st.error("Erro: O arquivo de Produção não possui as colunas mapeadas.")
        st.stop()

    try:
        df_ret = pd.DataFrame()
        df_ret['Data'] = df_ret_raw.iloc[:, IDX_RET_DATA]
        df_ret['Equipe'] = df_ret_raw.iloc[:, IDX_RET_EQUIPE]
        df_ret['Forno/Linha'] = df_ret_raw.iloc[:, IDX_RET_FORNO]
        df_ret['Motivo'] = df_ret_raw.iloc[:, IDX_RET_MOTIVO]
        df_ret['M2 Retido'] = df_ret_raw.iloc[:, IDX_RET_M2]

        col_data_r = 'Data'
        col_equipe_r = 'Equipe'
        col_forno_r = 'Forno/Linha'
        col_motivo = 'Motivo'
        col_m2 = 'M2 Retido'
    except IndexError:
        st.error("Erro: O arquivo de Retidos não possui as colunas mapeadas.")
        st.stop()

    # Tratamento Inicial de Dados
    df_prod['metragem_real'] = df_prod[col_metragem].apply(limpar_numero)
    df_prod['data_obj'] = pd.to_datetime(df_prod[col_data_p], dayfirst=True, errors='coerce')
    df_prod['mes_ano'] = df_prod['data_obj'].dt.strftime('%Y-%m').fillna('Sem Data')

    df_ret['m2_real'] = df_ret[col_m2].apply(limpar_numero)
    df_ret['data_obj'] = pd.to_datetime(df_ret[col_data_r], dayfirst=True, errors='coerce')
    df_ret['mes_ano'] = df_ret['data_obj'].dt.strftime('%Y-%m').fillna('Sem Data')

    # --- FUNCIONALIDADE: MAPEAMENTO DE FORNOS ---
    st.sidebar.markdown("---")
    with st.sidebar.expander("🛠️ Configuração de Linhas/Fornos", expanded=True):
        st.write("Determine qual Forno pertence a qual Linha.")
        
        fornos_prod = df_prod[col_forno_p].dropna().unique().tolist()
        fornos_ret = df_ret[col_forno_r].dropna().unique().tolist()
        todos_fornos = sorted(list(set([str(x) for x in fornos_prod + fornos_ret])))

        if 'mapa_fornos_df' not in st.session_state:
            st.session_state.mapa_fornos_df = pd.DataFrame({'Código no Arquivo': todos_fornos, 'Nome da Linha (Edite aqui)': todos_fornos})

        st.caption("Edite a coluna da direita para agrupar os fornos:")
        editor_df = st.data_editor(
            st.session_state.mapa_fornos_df, 
            hide_index=True, 
            column_config={
                "Código no Arquivo": st.column_config.TextColumn(disabled=True),
                "Nome da Linha (Edite aqui)": st.column_config.TextColumn(required=True)
            },
            key='editor_fornos'
        )
        mapa_de_para_linhas = dict(zip(editor_df['Código no Arquivo'], editor_df['Nome da Linha (Edite aqui)']))

        # --- FUNCIONALIDADE: AGRUPAMENTO DE LINHAS ---
        st.markdown("---")
        st.write("Agrupar Linhas em Relatórios:")
        linhas_criadas = sorted(list(set(mapa_de_para_linhas.values())))
        if 'grupos_linhas' not in st.session_state: st.session_state.grupos_linhas = {}

        col_add1, col_add2 = st.columns(2)
        novo_grupo_nome = col_add1.text_input("Nome do Grupo (ex: Fábrica 1)")
        linhas_selecionadas = col_add2.multiselect("Selecione as Linhas", linhas_criadas)
        
        if st.button("➕ Criar Grupo"):
            if novo_grupo_nome and linhas_selecionadas:
                st.session_state.grupos_linhas[novo_grupo_nome] = linhas_selecionadas
                st.rerun()

        if st.session_state.grupos_linhas:
            to_remove = []
            for k, v in st.session_state.grupos_linhas.items():
                c_del1, c_del2 = st.columns([0.8, 0.2])
                c_del1.text(f"{k}: {', '.join(v)}")
                if c_del2.button("🗑️", key=f"del_gl_{k}"): to_remove.append(k)
            for r in to_remove:
                del st.session_state.grupos_linhas[r]
                st.rerun()

    df_prod['Linha_Nome'] = df_prod[col_forno_p].astype(str).map(mapa_de_para_linhas).fillna('Outros')
    df_ret['Linha_Nome'] = df_ret[col_forno_r].astype(str).map(mapa_de_para_linhas).fillna('Outros')

    def definir_grupo_relatorio(linha_nome):
        for nome_grupo, lista_linhas in st.session_state.grupos_linhas.items():
            if linha_nome in lista_linhas: return nome_grupo
        return linha_nome 

    df_prod['Grupo_Relatorio'] = df_prod['Linha_Nome'].apply(definir_grupo_relatorio)
    df_ret['Grupo_Relatorio'] = df_ret['Linha_Nome'].apply(definir_grupo_relatorio)

    # --- SIDEBAR: ANÁLISE ESPECÍFICA E FILTROS DE MOTIVO ---
    todos_motivos_brutos = sorted(df_ret[col_motivo].astype(str).unique())
    motivo_alvo = st.sidebar.selectbox("🔎 Escolha o Motivo:", ["(Selecione um motivo)"] + todos_motivos_brutos)
    
    st.sidebar.markdown("**Metas para este Motivo:**")
    c_sb1, c_sb2 = st.sidebar.columns(2)
    META_ABSOLUTA_M2 = c_sb1.number_input("M² Limite", min_value=0.0, value=100.0, step=10.0)
    USAR_META_M2 = c_sb2.checkbox("Ativar Meta M²", value=True)
    c_sb3, c_sb4 = st.sidebar.columns(2)
    META_FREQ_QTD = c_sb3.number_input("Qtd Limite", min_value=0, value=10, step=1)
    USAR_META_FREQ = c_sb4.checkbox("Ativar Meta Qtd", value=False)

    st.sidebar.markdown("---")
    st.sidebar.write("**Filtros de Motivos**")
    motivos_excluir = st.sidebar.multiselect("🗑️ Excluir Motivos da Análise", options=todos_motivos_brutos)
    
    df_ret_filtrado = df_ret[~df_ret[col_motivo].isin(motivos_excluir)].copy() if motivos_excluir else df_ret.copy()

    if 'grupos_motivos' not in st.session_state: st.session_state.grupos_motivos = {}
    with st.sidebar.expander("➕ Agrupar Defeitos/Motivos"):
        motivos_disp = sorted(df_ret_filtrado[col_motivo].unique())
        selecao_mot = st.multiselect("Selecione os Motivos:", motivos_disp)
        nome_grupo_mot = st.text_input("Nome do Grupo de Defeito")
        if st.button("Salvar Grupo Defeito") and selecao_mot and nome_grupo_mot:
            st.session_state.grupos_motivos[nome_grupo_mot] = selecao_mot
            st.rerun()
    
    if st.session_state.grupos_motivos:
        remover_mot = []
        for g, l in st.session_state.grupos_motivos.items():
            if st.sidebar.button(f"Remover {g}", key=f"del_gm_{g}"): remover_mot.append(g)
        for r in remover_mot: del st.session_state.grupos_motivos[r]
        if remover_mot: st.rerun()

    def definir_motivo_analise(m):
        for g, l in st.session_state.grupos_motivos.items():
            if m in l: return g
        return m
    df_ret_filtrado['Motivo_Analise'] = df_ret_filtrado[col_motivo].apply(definir_motivo_analise)

    # --- CÁLCULOS KPI GERAL ---
    df_p_agg = df_prod.rename(columns={col_equipe_p: 'Equipe'})
    df_r_agg = df_ret_filtrado.rename(columns={col_equipe_r: 'Equipe'})

    prod_agg = df_p_agg.groupby(['Grupo_Relatorio', 'Equipe'])['metragem_real'].sum().reset_index().rename(columns={'metragem_real': 'M2_Produzido'})
    ret_agg = df_r_agg.groupby(['Grupo_Relatorio', 'Equipe'])['m2_real'].sum().reset_index().rename(columns={'m2_real': 'M2_Retido'})
    
    df_final = pd.merge(prod_agg, ret_agg, on=['Grupo_Relatorio', 'Equipe'], how='outer').fillna(0)
    
    df_final['Meta_M2'] = df_final['M2_Produzido'] * (META_PCT / 100)
    df_final['Saldo_M2'] = df_final['Meta_M2'] - df_final['M2_Retido']

    pct_raw = (df_final['M2_Retido'] / df_final['M2_Produzido']) * 100
    df_final['% Realizado'] = pct_raw.apply(truncar_duas_casas)    
    grupos_unicos = sorted(df_final['Grupo_Relatorio'].unique())
    
    df_tabela_consolidadas = []
    for grupo in grupos_unicos:
        df_grupo = adicionar_linha_geral(df_final, grupo, META_PCT)
        if df_grupo is not None:
            df_grupo['Status'] = df_grupo['% Realizado'].apply(lambda x: 'Dentro da Meta (Verde)' if x <= META_PCT else 'Fora da Meta (Vermelho)')
            df_tabela_consolidadas.append(df_grupo)
            
    df_tabela_final = pd.concat(df_tabela_consolidadas, ignore_index=True) if df_tabela_consolidadas else pd.DataFrame()

    # =========================================================================
    # --- DASHBOARD: ABAS ---
    # =========================================================================
    tab1, tab2, tab3 = st.tabs(["📊 Resultados Consolidados", "🔍 Análise por Motivo", "💾 Dados Brutos"])

    with tab1:
        if grupos_unicos:
            for idx, grupo in enumerate(grupos_unicos):
                # QUEBRA DE PÁGINA (Aplica a partir do 2º grupo na hora de imprimir)
                if idx > 0:
                    st.markdown('<div class="pagebreak"></div>', unsafe_allow_html=True)
                
                st.markdown(f"<h3 style='color: #2E86C1;'>🏭 Escolha: {grupo}</h3>", unsafe_allow_html=True)

                df_g = df_tabela_final[df_tabela_final['Grupo_Relatorio'] == grupo]
                df_m = df_ret_filtrado[df_ret_filtrado['Grupo_Relatorio'] == grupo]

                # --- LINHA 1 (Paisagem): Métrica | Gráfico % | Gráfico M2 ---
                c1, c2, c3 = st.columns([1.2, 2.4, 2.4])

                with c1:
                    st.markdown("**Indicador Geral**")
                    if not df_g.empty:
                        row = df_g[df_g['Equipe'] == 'Média Geral']
                        if not row.empty:
                            val = row['% Realizado'].values[0]
                            st.metric(f"Meta: {META_PCT}%", f"{val:.2f}%")
                            if val <= META_PCT: st.success("🟢 Dentro da Meta")
                            else: st.error("🔴 Fora da Meta")

                with c2:
                    mapa_cores = {'Dentro da Meta (Verde)': '#27AE60', 'Fora da Meta (Vermelho)': '#E74C3C'}
                    if not df_g.empty:
                        fig_pct = go.Figure(go.Bar(x=df_g['Equipe'], y=df_g['% Realizado'],
                                                marker_color=[mapa_cores.get(s, '#333') for s in df_g['Status']],
                                                text=[f"{v:.2f}" for v in df_g['% Realizado']], textposition='inside'))
                        fig_pct.add_hline(y=META_PCT, line_dash="dot",
                                      annotation_text=f"Meta: {META_PCT}%",
                                      annotation_position="top right", annotation_font_color="black")
                        fig_pct.update_layout(title="Performance por Equipe (%)", template=TEMPLATE_GRAFICO, margin=dict(l=0, r=0, t=30, b=0), height=230)
                        st.plotly_chart(fig_pct, use_container_width=True)

                with c3:
                    if 'mes_ano' in df_p_agg.columns:
                        fig_m2 = criar_grafico_evolucao_com_geral(df_prod.rename(columns={col_equipe_p: 'Equipe'}),
                                                                  df_ret_filtrado.rename(columns={col_equipe_r: 'Equipe'}),
                                                                  grupo, META_PCT)
                        if fig_m2:
                            fig_m2.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=230)
                            st.plotly_chart(fig_m2, use_container_width=True)

                st.write("") # Pequeno respiro

                # --- LINHA 2 (Paisagem): Top Causas | Tabela ---
                c4, c5 = st.columns([2, 4])

                with c4:
                    st.markdown("**Top 5 Defeitos**")
                    if not df_m.empty:
                        top = df_m.groupby('Motivo_Analise')['m2_real'].sum().sort_values(ascending=False).head(5).reset_index()
                        fig_top = px.bar(top, y='Motivo_Analise', x='m2_real', orientation='h', text_auto='.2f', template=TEMPLATE_GRAFICO)
                        fig_top.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=220)
                        fig_top.update_yaxes(title="")
                        fig_top.update_xaxes(title="")
                        st.plotly_chart(fig_top, use_container_width=True)

                with c5:
                    if not df_g.empty:
                        fig_tabela = criar_tabela_grafica(df_g, META_PCT, altura=220)
                        if fig_tabela:
                            st.plotly_chart(fig_tabela, use_container_width=True)

                st.markdown("---")

            # --- ÚLTIMA PÁGINA: Logs ---
            st.markdown('<div class="pagebreak"></div>', unsafe_allow_html=True)
            st.subheader("📝 Resumo das Configurações do Sistema")
            c_log1, c_log2, c_log3 = st.columns(3)
            with c_log1:
                st.markdown("**⛔ Motivos Excluídos:**")
                if motivos_excluir:
                    for m in motivos_excluir: st.markdown(f"- {m}")
                else: st.caption("Nenhum.")
            with c_log2:
                st.markdown("**📦 Grupos de Defeitos:**")
                if st.session_state.grupos_motivos:
                    for g, l in st.session_state.grupos_motivos.items(): st.markdown(f"**{g}**: {', '.join(l)}")
                else: st.caption("Nenhum.")
            with c_log3:
                st.markdown("**🏭 Agrupamento de Linhas:**")
                if st.session_state.grupos_linhas:
                    for g, l in st.session_state.grupos_linhas.items(): st.markdown(f"**{g}**: {', '.join(l)}")
                else: st.caption("Automático.")

    with tab2:
        if motivo_alvo and motivo_alvo != "(Selecione um motivo)":
            st.subheader(f"🔎 Análise: {motivo_alvo}")
            df_spec = df_ret[df_ret[col_motivo] == motivo_alvo].copy()
            todas_equipes = pd.DataFrame({'Equipe': sorted(df_prod[col_equipe_p].unique())})
            
            spec_agg = df_spec.groupby(col_equipe_r)['m2_real'].sum().reset_index().rename(columns={col_equipe_r: 'Equipe', 'm2_real': 'M2_Retido'})
            spec_count = df_spec.groupby(col_equipe_r).size().reset_index(name='Qtd_Ocorrencias')
            spec_final = pd.merge(todas_equipes, spec_agg, on='Equipe', how='left').fillna(0)
            spec_final = pd.merge(spec_final, spec_count, on='Equipe', how='left').fillna(0)
            
            c1, c2 = st.columns(2)
            with c1:
                spec_final['Cor_M2'] = spec_final['M2_Retido'].apply(lambda x: '#27AE60' if x <= META_ABSOLUTA_M2 or not USAR_META_M2 else '#E74C3C')
                fig = go.Figure(go.Bar(x=spec_final['Equipe'], y=spec_final['M2_Retido'], marker_color=spec_final['Cor_M2'], text=[f"{v:.2f}" for v in spec_final['M2_Retido']], textposition='auto'))
                if USAR_META_M2: 
                    fig.add_hline(y=META_ABSOLUTA_M2, line_dash="dash", annotation_text=f"Meta: {META_ABSOLUTA_M2}m²", annotation_position="top right", annotation_font_color="black")
                fig.update_layout(title="Metragem por Equipe", template=TEMPLATE_GRAFICO)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                spec_final['Cor_Qtd'] = spec_final['Qtd_Ocorrencias'].apply(lambda x: '#27AE60' if x <= META_FREQ_QTD or not USAR_META_FREQ else '#E74C3C')
                fig = go.Figure(go.Bar(x=spec_final['Equipe'], y=spec_final['Qtd_Ocorrencias'], marker_color=spec_final['Cor_Qtd'], text=spec_final['Qtd_Ocorrencias'], textposition='auto'))
                if USAR_META_FREQ: 
                    fig.add_hline(y=META_FREQ_QTD, line_dash="dash", annotation_text=f"Meta: {META_FREQ_QTD}", annotation_position="top right", annotation_font_color="black")
                fig.update_layout(title="Quantidade de Ocorrências", template=TEMPLATE_GRAFICO)
                st.plotly_chart(fig, use_container_width=True)

            spec_linha = df_spec.groupby('Grupo_Relatorio').size().reset_index(name='Qtd_Ocorrencias')
            fig_l = px.bar(spec_linha, x='Grupo_Relatorio', y='Qtd_Ocorrencias', text='Qtd_Ocorrencias', title="Ocorrências por Grupo/Linha", template=TEMPLATE_GRAFICO)
            st.plotly_chart(fig_l, use_container_width=True)
        else:
            st.info("👈 Selecione um motivo na barra lateral.")

    with tab3:
        st.dataframe(df_tabela_final, use_container_width=True)
        st.download_button("📥 Baixar Excel", data=convert_df_to_excel(df_tabela_final), file_name="relatorio_consolidado.xlsx")

else:
    st.info("Aguardando upload dos arquivos (Formatos aceitos: .xlsx, .csv). O sistema fará a leitura posicional automática configurada.")
