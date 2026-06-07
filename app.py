# (CÓDIGO INTEIRO PRESERVADO ATÉ A ABA ALOCAÇÃO — OMITINDO A PARTE INICIAL PARA FOCO)

# ------------------------------------------------------------------------------  
# ⚙️ ABA 2: CENTRAL DE ALOCAÇÃO  
# ------------------------------------------------------------------------------  
with aba_alocacao:
    if not df_custodia_atual.empty:
        df_analise = df_custodia_atual.copy()
        
        if 'Classificacao' not in df_analise.columns: df_analise['Classificacao'] = 'NÃO INFORMADO'
        if 'Seguimento' not in df_analise.columns: df_analise['Seguimento'] = 'NÃO INFORMADO'
        if 'Gestora' not in df_analise.columns: df_analise['Gestora'] = 'NÃO INFORMADO'
            
        df_analise['Classificacao'] = df_analise['Classificacao'].fillna('NÃO INFORMADO').astype(str).str.upper()
        df_analise['Seguimento'] = df_analise['Seguimento'].fillna('NÃO INFORMADO').astype(str).str.upper()
        df_analise['Gestora'] = df_analise['Gestora'].fillna('NÃO INFORMADO').astype(str).str.upper()

        col_super_esq, col_super_dir = st.columns([4, 6])
        
        # ======================================================================
        # ESQUERDA
        # ======================================================================
        with col_super_esq:
            with st.container(border=True):
                st.markdown("<h4 style='margin:0; padding-bottom:4px;'>1. Exposição por Ativo</h4>", unsafe_allow_html=True)

                df_ativos_sorted = df_analise.sort_values(by='Patrimonio_Mercado_Ativo', ascending=True)

                fig_bar_ativos = go.Figure(go.Bar(
                    x=df_ativos_sorted['Patrimonio_Mercado_Ativo'],
                    y=df_ativos_sorted['Ticker'],
                    orientation='h',
                    marker_color='#1fbc74'
                ))

                fig_bar_ativos.update_layout(
                    margin=dict(l=65, r=15, t=10, b=10),
                    height=540
                )

                st.plotly_chart(fig_bar_ativos, use_container_width=True)

        # ======================================================================
        # DIREITA
        # ======================================================================
        with col_super_dir:

            col_interna_class, col_interna_seg = st.columns(2)

            # -------------------
            # CLASSIFICAÇÃO
            # -------------------
            with col_interna_class:
                with st.container(border=True):

                    st.markdown("<h4 style='margin:0;'>Classificação</h4>", unsafe_allow_html=True)

                    df_g_tipo = df_analise.groupby('Classificacao')['Patrimonio_Mercado_Ativo'].sum().reset_index()

                    fig_t = go.Figure(go.Pie(
                        labels=df_g_tipo['Classificacao'],
                        values=df_g_tipo['Patrimonio_Mercado_Ativo'],
                        hole=0.55
                    ))

                    fig_t.update_layout(
                        margin=dict(l=5, r=5, t=10, b=0),  # ✅ AJUSTE
                        height=210
                    )

                    st.plotly_chart(fig_t, use_container_width=True)

            # -------------------
            # SEGUIMENTO
            # -------------------
            with col_interna_seg:
                with st.container(border=True):

                    st.markdown("<h4 style='margin:0;'>Seguimento</h4>", unsafe_allow_html=True)

                    df_g_seg = df_analise.groupby('Seguimento')['Patrimonio_Mercado_Ativo'].sum().reset_index()

                    fig_s = go.Figure(go.Pie(
                        labels=df_g_seg['Seguimento'],
                        values=df_g_seg['Patrimonio_Mercado_Ativo'],
                        hole=0.55
                    ))

                    fig_s.update_layout(
                        margin=dict(l=5, r=5, t=10, b=0),  # ✅ AJUSTE
                        height=210
                    )

                    st.plotly_chart(fig_s, use_container_width=True)

            # 🔥 REMOVIDO margin-top negativo aqui

            # ======================================================================
            # GESTORA
            # ======================================================================
            with st.container(border=True):

                st.markdown("<h4 style='margin:0;'>Gestora</h4>", unsafe_allow_html=True)

                df_g_gest = df_analise.groupby('Gestora')['Patrimonio_Mercado_Ativo'].sum().reset_index()

                fig_bar_gest = go.Figure(go.Bar(
                    x=df_g_gest['Patrimonio_Mercado_Ativo'],
                    y=df_g_gest['Gestora'],
                    orientation='h',
                    marker_color='#118DFF'
                ))

                fig_bar_gest.update_layout(
                    margin=dict(l=75, r=15, t=10, b=0),  # ✅ AJUSTE
                    height=320
                )

                st.plotly_chart(fig_bar_gest, use_container_width=True)

        # Insights
        st.markdown("""
        <div style="border: 1px solid #D6DBDF; padding: 10px;">
            💡 Use classificação vs seguimento para avaliar risco estrutural da carteira.
        </div>
        """, unsafe_allow_html=True)
``
