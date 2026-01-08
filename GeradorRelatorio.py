import math  # <--- Adicione esta importação no topo
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Gestão de Produção & Qualidade", layout="wide")
TEMPLATE_GRAFICO = "plotly_white"

# --- CSS PARA IMPRESSÃO (RETRATO) ---
st.markdown("""
    <style>
        @media print {
            @page { 
                size: portrait; 
                margin: 0.5cm; 
            }
            [data-testid="stSidebar"], header, footer, [data-testid="stToolbar"], .stAppHeader, .stDeployButton { 
                display: none !important; 
            }
            body { 
                zoom: 55%; 
                -webkit-print-color-adjust: exact !important; 
                print-color-adjust: exact !important; 
            }
            .stApp { 
                position: absolute; 
                top: 0; 
                left: 0; 
                width: 100%; 
                height: auto !important; 
                overflow: visible !important; 
            }
            .main .block-container { 
                max-width: 100% !important; 
                width: 100% !important; 
                padding: 10px !important; 
                overflow: visible !important; 
            }
            .js-plotly-plot { 
                max-width: 100% !important; 
                page-break-inside: avoid;
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
    # Multiplica por 100, corta as casas decimais (floor) e divide por 100
    return math.floor(valor * 100) / 100

def identificar_coluna(df, keywords, nome_padrao_exibicao):
    colunas_df = [c.lower().strip() for c in df.columns]
    mapa_cols = {c.lower().strip(): c for c in df.columns} 
    for kw in keywords:
        for col in colunas_df:
            if kw in col:
                return mapa_cols[col]
    return None

def carregar_arquivo(uploaded_file):
    try:
        if uploaded_file.name.lower().endswith('.csv'):
            try: return pd.read_csv(uploaded_file)
            except:
                uploaded_file.seek(0)
                return pd.read_csv(uploaded_file, sep=';')
        else: return pd.read_excel(uploaded_file)
    except Exception as e: return None

# --- FUNÇÕES DE CÁLCULO E GRÁFICO ---
def adicionar_linha_geral(df_original, nome_grupo, meta_pct):
    # Filtra pelo Grupo e cria cópia
    df_filt = df_original[df_original['Grupo_Relatorio'] == nome_grupo].copy()
    if df_filt.empty: return df_filt

    total_prod = df_filt['M2_Produzido'].sum()
    total_ret = df_filt['M2_Retido'].sum()
    meta_m2_total = total_prod * (meta_pct / 100)
    saldo_total = meta_m2_total - total_ret
    # Cálculo com truncamento (sem arredondar para cima)
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

def criar_tabela_grafica(df, meta_pct):
    if df.empty: return None
    cor_texto_pct = ['#E74C3C' if v > meta_pct else '#27AE60' for v in df['% Realizado']]
    cor_texto_saldo = ['#E74C3C' if v < 0 else '#27AE60' for v in df['Saldo_M2']]
    
    fig = go.Figure(data=[go.Table(
        header=dict(values=['<b>Grupo</b>', '<b>Equipe</b>', '<b>Produção</b>', '<b>Meta (m²)</b>', '<b>Retido (m²)</b>', '<b>Saldo</b>', '<b>% Perda</b>'],
                    fill_color='#2E86C1', align='center', font=dict(color='white', size=12)),
        cells=dict(values=[df['Grupo_Relatorio'], df['Equipe'], 
                           [f"{v:,.2f}" for v in df['M2_Produzido']], 
                           [f"{v:,.2f}" for v in df['Meta_M2']], 
                           [f"{v:,.2f}" for v in df['M2_Retido']], 
                           [f"{v:,.2f}" for v in df['Saldo_M2']], 
                           [f"{v:.2f}%" for v in df['% Realizado']]],
                   fill_color='#F7F9F9', align='center',
                   font=dict(color=['black', 'black', 'black', 'black', 'black', cor_texto_saldo, cor_texto_pct], size=11),
                   height=30))])
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=400)
    return fig

def criar_grafico_evolucao_com_geral(df_prod, df_ret, nome_grupo, meta_pct):
    df_p = df_prod[df_prod['Grupo_Relatorio'] == nome_grupo].copy()
    df_r = df_ret[df_ret['Grupo_Relatorio'] == nome_grupo].copy()
    if df_p.empty and df_r.empty: return None
    
    # Agrupa por Mês/Equipe (Somando tudo dentro do grupo)
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
    
    # --- ALTERAÇÃO AQUI: Apenas o nome da equipe no Label_X ---
    df_final['Label_X'] = df_final['Equipe'].astype(str)
    
    fig = go.Figure()
    # Barra Retido
    fig.add_trace(go.Bar(x=df_final['Label_X'], y=df_final['M2_Retido'], marker_color=df_final['Cor_Barra'],
                         text=[f"{v:,.2f}" for v in df_final['M2_Retido']], textposition='inside', name='Realizado'))
    
    # Linha Meta com Texto (Preto)
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
    fig.update_layout(title=f"{nome_grupo}: M²", yaxis=dict(range=[0, max_val * 1.3]), template=TEMPLATE_GRAFICO, showlegend=True)
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
    # 1. Carregamento
    df_prod = carregar_arquivo(file_prod)
    df_ret = carregar_arquivo(file_ret)

    if df_prod is None or df_ret is None:
        st.error("Erro na leitura dos arquivos.")
        st.stop()

    # 2. Identificação de Colunas
    erros_mapeamento = []
    # Prod
    col_equipe_p = identificar_coluna(df_prod, ['equipe', 'team', 'turno'], 'Equipe')
    col_forno_p = identificar_coluna(df_prod, ['forno', 'linha', 'maq'], 'Forno/Linha')
    col_metragem = identificar_coluna(df_prod, ['metragem', 'm2', 'prod'], 'Metragem/Produção')
    col_data_p = identificar_coluna(df_prod, ['data', 'date', 'dia'], 'Data') 
    # Ret
    col_motivo = identificar_coluna(df_ret, ['motivo', 'defeito', 'causa'], 'Motivo')
    col_m2 = identificar_coluna(df_ret, ['m²', 'm2', 'metragem', 'quant'], 'M2 Retido')
    col_equipe_r = identificar_coluna(df_ret, ['equipe', 'team', 'turno'], 'Equipe')
    col_forno_r = identificar_coluna(df_ret, ['forno', 'linha', 'maq'], 'Forno/Linha')
    col_data_r = identificar_coluna(df_ret, ['data', 'date', 'dia', 'hora'], 'Data')

    cols_obrigatorias = [col_equipe_p, col_forno_p, col_metragem, col_motivo, col_m2, col_equipe_r, col_forno_r]
    if any(c is None for c in cols_obrigatorias):
        st.error("Colunas obrigatórias não encontradas. Verifique os nomes no Excel.")
        st.stop()

    # Tratamento Inicial
    df_prod['metragem_real'] = df_prod[col_metragem].apply(limpar_numero)
    if col_data_p:
        df_prod['data_obj'] = pd.to_datetime(df_prod[col_data_p], dayfirst=True, errors='coerce')
        df_prod['mes_ano'] = df_prod['data_obj'].dt.strftime('%Y-%m')
    else: df_prod['mes_ano'] = 'Sem Data'

    df_ret['m2_real'] = df_ret[col_m2].apply(limpar_numero)
    if col_data_r:
        df_ret['data_obj'] = pd.to_datetime(df_ret[col_data_r], dayfirst=True, errors='coerce')
        df_ret['mes_ano'] = df_ret['data_obj'].dt.strftime('%Y-%m')
    else: df_ret['mes_ano'] = 'Sem Data'

    # --- FUNCIONALIDADE: MAPEAMENTO DE FORNOS ---
    st.sidebar.markdown("---")
    with st.sidebar.expander("🛠️ Configuração de Linhas/Fornos", expanded=True):
        st.write("Determine qual Forno pertence a qual Linha.")
        
        fornos_prod = df_prod[col_forno_p].dropna().unique().tolist()
        fornos_ret = df_ret[col_forno_r].dropna().unique().tolist()
        todos_fornos = sorted(list(set([str(x) for x in fornos_prod + fornos_ret])))

        if 'mapa_fornos_df' not in st.session_state:
            st.session_state.mapa_fornos_df = pd.DataFrame({
                'Código no Arquivo': todos_fornos,
                'Nome da Linha (Edite aqui)': todos_fornos
            })

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
        
        if st.button("➕ Criar Grupo de Linhas"):
            if novo_grupo_nome and linhas_selecionadas:
                st.session_state.grupos_linhas[novo_grupo_nome] = linhas_selecionadas
                st.rerun()

        if st.session_state.grupos_linhas:
            st.write("**Grupos Atuais:**")
            to_remove = []
            for k, v in st.session_state.grupos_linhas.items():
                c_del1, c_del2 = st.columns([0.8, 0.2])
                c_del1.text(f"{k}: {', '.join(v)}")
                if c_del2.button("🗑️", key=f"del_gl_{k}"): to_remove.append(k)
            for r in to_remove:
                del st.session_state.grupos_linhas[r]
                st.rerun()

    # --- APLICAÇÃO DO MAPEAMENTO ---
    df_prod['Linha_Nome'] = df_prod[col_forno_p].astype(str).map(mapa_de_para_linhas).fillna('Outros')
    df_ret['Linha_Nome'] = df_ret[col_forno_r].astype(str).map(mapa_de_para_linhas).fillna('Outros')

    def definir_grupo_relatorio(linha_nome):
        for nome_grupo, lista_linhas in st.session_state.grupos_linhas.items():
            if linha_nome in lista_linhas:
                return nome_grupo
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
        st.sidebar.write("Grupos de Defeitos:")
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

    # Agrupa por Grupo_Relatorio e Equipe (Soma tudo o que estiver dentro do grupo)
    prod_agg = df_p_agg.groupby(['Grupo_Relatorio', 'Equipe'])['metragem_real'].sum().reset_index().rename(columns={'metragem_real': 'M2_Produzido'})
    ret_agg = df_r_agg.groupby(['Grupo_Relatorio', 'Equipe'])['m2_real'].sum().reset_index().rename(columns={'m2_real': 'M2_Retido'})
    
    df_final = pd.merge(prod_agg, ret_agg, on=['Grupo_Relatorio', 'Equipe'], how='outer').fillna(0)
    
    df_final['Meta_M2'] = df_final['M2_Produzido'] * (META_PCT / 100)
    df_final['Saldo_M2'] = df_final['Meta_M2'] - df_final['M2_Retido']
# Calcula o percentual bruto e depois aplica o truncamento linha a linha
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

    # --- DASHBOARD ---
    tab1, tab2, tab3 = st.tabs(["📊 Resultados Consolidados", "🔍 Análise por Motivo", "💾 Dados Brutos"])

    with tab1:
        st.subheader(f"📈 Indicadores Gerais (Meta de {META_PCT}%)")
        
        if grupos_unicos:
            cols = st.columns(len(grupos_unicos))
            for idx, grupo in enumerate(grupos_unicos):
                with cols[idx]:
                    st.info(f"**{grupo}**")
                    if not df_tabela_final.empty:
                        row = df_tabela_final[(df_tabela_final['Grupo_Relatorio'] == grupo) & (df_tabela_final['Equipe'] == 'Média Geral')]
                        if not row.empty:
                            val = row['% Realizado'].values[0]
                            st.metric("Resultado", f"{val:.2f}%")
                            if val <= META_PCT: st.markdown(":green[**Dentro da Meta**]")
                            else: st.markdown(":red[**Fora da Meta**]")
        
            st.markdown("---")
            st.subheader(f"📊 Performance por Equipe em %")
            
            cols_g = st.columns(len(grupos_unicos))
            mapa_cores = {'Dentro da Meta (Verde)': '#27AE60', 'Fora da Meta (Vermelho)': '#E74C3C'}
            
            for idx, grupo in enumerate(grupos_unicos):
                with cols_g[idx]:
                    df_g = df_tabela_final[df_tabela_final['Grupo_Relatorio'] == grupo]
                    if not df_g.empty:
                        fig = go.Figure(go.Bar(x=df_g['Equipe'], y=df_g['% Realizado'],
                                                marker_color=[mapa_cores.get(s, '#333') for s in df_g['Status']],
                                                text=[f"{v:.2f}" for v in df_g['% Realizado']], textposition='inside'))
                        # AJUSTE: Cor do texto da meta (Preto)
                        fig.add_hline(y=META_PCT, line_dash="dot", 
                                      annotation_text=f"Meta: {META_PCT}%", 
                                      annotation_position="top right",
                                      annotation_font_color="black")
                        fig.update_layout(title=f"{grupo}: % ", template=TEMPLATE_GRAFICO)
                        st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")
            st.subheader("📊 Performance por Equipe em M²")
            if 'mes_ano' in df_p_agg.columns:
                cols_t = st.columns(len(grupos_unicos))
                for idx, grupo in enumerate(grupos_unicos):
                    with cols_t[idx]:
                        fig_t = criar_grafico_evolucao_com_geral(df_prod.rename(columns={col_equipe_p: 'Equipe'}), df_ret_filtrado.rename(columns={col_equipe_r: 'Equipe'}), grupo, META_PCT)
                        if fig_t: st.plotly_chart(fig_t, use_container_width=True)
            
            st.markdown("---")
            fig_tabela = criar_tabela_grafica(df_tabela_final, META_PCT)
            if fig_tabela: st.plotly_chart(fig_tabela, use_container_width=True)

            st.markdown("---")
            st.subheader("🏆 Top Causas de Retenção")
            cols_top = st.columns(len(grupos_unicos))
            for idx, grupo in enumerate(grupos_unicos):
                with cols_top[idx]:
                    df_m = df_ret_filtrado[df_ret_filtrado['Grupo_Relatorio'] == grupo]
                    if not df_m.empty:
                        top = df_m.groupby('Motivo_Analise')['m2_real'].sum().sort_values(ascending=False).head(10).reset_index()
                        fig_top = px.bar(top, y='Motivo_Analise', x='m2_real', orientation='h', title=f"Top 10 - {grupo}", text_auto='.2f', template=TEMPLATE_GRAFICO)
                        st.plotly_chart(fig_top, use_container_width=True)
        
        # --- AUDITORIA E DADOS DE CONFIGURAÇÃO (ABAIXO DO TOP 10) ---
        st.markdown("---")
        st.subheader("📝 Resumo das Configurações Aplicadas")
        
        c_log1, c_log2, c_log3 = st.columns(3)
        with c_log1:
            st.markdown("**⛔ Motivos Excluídos:**")
            if motivos_excluir:
                for m in motivos_excluir: st.markdown(f"- {m}")
            else: st.caption("Nenhum motivo excluído.")
        
        with c_log2:
            st.markdown("**📦 Agrupamento de Defeitos:**")
            if st.session_state.grupos_motivos:
                for g, l in st.session_state.grupos_motivos.items():
                    st.markdown(f"**{g}** contém: " + ", ".join(l))
            else: st.caption("Nenhum agrupamento de defeitos.")
            
        with c_log3:
            st.markdown("**🏭 Agrupamento de Linhas:**")
            if st.session_state.grupos_linhas:
                for g, l in st.session_state.grupos_linhas.items():
                    st.markdown(f"**Relatório {g}** contém: " + ", ".join(l))
            else: st.caption("Cada linha é um relatório individual.")

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
                    # AJUSTE: Cor do texto da meta (Preto)
                    fig.add_hline(y=META_ABSOLUTA_M2, line_dash="dash", 
                                  annotation_text=f"Meta: {META_ABSOLUTA_M2}m²", 
                                  annotation_position="top right",
                                  annotation_font_color="black")
                fig.update_layout(title="Metragem por Equipe", template=TEMPLATE_GRAFICO)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                spec_final['Cor_Qtd'] = spec_final['Qtd_Ocorrencias'].apply(lambda x: '#27AE60' if x <= META_FREQ_QTD or not USAR_META_FREQ else '#E74C3C')
                fig = go.Figure(go.Bar(x=spec_final['Equipe'], y=spec_final['Qtd_Ocorrencias'], marker_color=spec_final['Cor_Qtd'], text=spec_final['Qtd_Ocorrencias'], textposition='auto'))
                if USAR_META_FREQ: 
                    # AJUSTE: Cor do texto da meta (Preto)
                    fig.add_hline(y=META_FREQ_QTD, line_dash="dash", 
                                  annotation_text=f"Meta: {META_FREQ_QTD}", 
                                  annotation_position="top right",
                                  annotation_font_color="black")
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
    st.info("Aguardando upload dos arquivos (Formatos aceitos: .xlsx, .csv). O nome do arquivo não importa.")