"""
Controle Financeiro Doméstico
Streamlit + Supabase
Tabelas: despesas | categorias | contas | payment_methods | edições
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
from datetime import date
from dateutil.relativedelta import relativedelta

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Controle Financeiro",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Supabase ──────────────────────────────────────────────────────────────────
def get_supabase() -> Client:
    raw_url = st.secrets["SUPABASE_URL"]
    # Garante que a URL seja só o host, sem /rest/v1/ ou barras extras
    url = raw_url.split("/rest/")[0].split("/auth/")[0].rstrip("/")
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

supabase = get_supabase()

# ── Nomes das tabelas (ajuste aqui se necessário) ─────────────────────────────
TB_DESPESAS   = "expenses"
TB_CATEGORIAS = "categories"
TB_CONTAS     = "accounts"
TB_PAGAMENTOS = "payment_methods"
TB_PARCELAS   = "installments"

# ── Mapeamento de colunas (PT → padrão interno) ───────────────────────────────
# Cada lista contém possíveis nomes que o Perplexity pode ter usado.
# O app usa sempre o primeiro que encontrar no DataFrame real.
COL_MAP = {
    # despesas
    "expense_date":      ["expense_date", "data", "data_despesa", "date"],
    "description":       ["description", "descricao", "descrição", "nome", "title"],
    "expense_type":      ["expense_type", "tipo", "type", "categoria_tipo"],
    "total_value":       ["total_value", "valor", "value", "amount", "valor_total"],
    "category_id":       ["category_id", "categoria_id", "id_categoria"],
    "payment_method_id": ["payment_method_id", "forma_pagamento_id", "id_forma_pagamento"],
    "account_id":        ["account_id", "conta_id", "id_conta"],
    "notes":             ["notes", "observacoes", "observações", "obs"],
    # parcelas
    "due_month":         ["due_month", "mes_vencimento", "vencimento", "due_date"],
    "installment_value": ["installment_value", "valor_parcela", "parcela_valor", "value"],
    "installment_number":["installment_number", "numero_parcela", "parcela_numero", "numero"],
    "total_installments":["total_installments", "total_parcelas", "parcelas_total", "total"],
    "paid":              ["paid", "pago", "quitado"],
    "expense_id":        ["expense_id", "despesa_id", "id_despesa"],
    # cadastros
    "name":              ["name", "nome", "descricao", "descrição", "title"],
}

def col(df: pd.DataFrame, key: str) -> str | None:
    """Retorna o nome real da coluna no df para a chave padrão, ou None."""
    for candidate in COL_MAP.get(key, [key]):
        if candidate in df.columns:
            return candidate
    return None

def get(row, key: str, default=None):
    """Lê valor de uma Series/dict usando mapeamento de colunas."""
    for candidate in COL_MAP.get(key, [key]):
        if candidate in row:
            return row[candidate]
    return default

# ── Helpers ───────────────────────────────────────────────────────────────────
def money(v) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def safe_query(table: str) -> pd.DataFrame:
    try:
        res = supabase.table(table).select("*").execute()
        return pd.DataFrame(res.data or [])
    except Exception as e:
        st.warning(f"⚠️ Tabela `{table}`: {e}")
        return pd.DataFrame()

def name_col(df: pd.DataFrame) -> str:
    """Coluna de nome/label nos cadastros auxiliares."""
    return col(df, "name") or (df.columns[1] if len(df.columns) > 1 else df.columns[0])

def id_from_name(df: pd.DataFrame, chosen: str) -> int | None:
    if df.empty or chosen in ("Sem cadastro", ""):
        return None
    nc = name_col(df)
    rows = df.loc[df[nc] == chosen, "id"]
    return int(rows.iloc[0]) if not rows.empty else None

# ── Cache de dados ────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_all():
    return {
        "despesas":   safe_query(TB_DESPESAS),
        "parcelas":   safe_query(TB_PARCELAS),
        "categorias": safe_query(TB_CATEGORIAS),
        "pagamentos": safe_query(TB_PAGAMENTOS),
        "contas":     safe_query(TB_CONTAS),
    }

def refresh():
    load_all.clear()
    st.rerun()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("💰 Finanças")
    st.caption("Controle doméstico pessoal")
    page = st.radio(
        "Menu",
        ["📊 Visão geral", "➕ Lançar despesa", "💳 Parceladas", "🗂️ Cadastros", "🔎 Diagnóstico"],
        label_visibility="collapsed",
    )
    st.divider()
    if st.button("🔄 Recarregar"):
        refresh()

data      = load_all()
df_exp    = data["despesas"].copy()
df_inst   = data["parcelas"].copy()
df_cats   = data["categorias"].copy()
df_pays   = data["pagamentos"].copy()
df_accs   = data["contas"].copy()


# ════════════════════════════════════════════════════════════════════
# PÁGINA: VISÃO GERAL
# ════════════════════════════════════════════════════════════════════
if page == "📊 Visão geral":
    st.title("📊 Visão geral")

    if df_exp.empty:
        st.info("Nenhum lançamento ainda. Use **➕ Lançar despesa** para começar.")
        st.stop()

    # Colunas detectadas
    c_date  = col(df_exp, "expense_date")
    c_val   = col(df_exp, "total_value")
    c_type  = col(df_exp, "expense_type")
    c_desc  = col(df_exp, "description")

    if not c_date or not c_val:
        st.error("Colunas de data ou valor não encontradas. Veja a página **🔎 Diagnóstico**.")
        st.stop()

    df_exp[c_date] = pd.to_datetime(df_exp[c_date])
    df_exp["_month"] = df_exp[c_date].dt.to_period("M").astype(str)
    df_exp[c_val]    = df_exp[c_val].astype(float)

    months    = sorted(df_exp["_month"].unique(), reverse=True)
    sel_month = st.selectbox("Filtrar mês", ["Todos"] + months)
    df_view   = df_exp if sel_month == "Todos" else df_exp[df_exp["_month"] == sel_month]

    total = df_view[c_val].sum()
    qty   = len(df_view)
    avg   = df_view[c_val].mean() if qty else 0

    k1, k2, k3 = st.columns(3)
    k1.metric("Total gasto",   money(total))
    k2.metric("Lançamentos",   qty)
    k3.metric("Ticket médio",  money(avg))

    st.divider()
    c1, c2 = st.columns(2)

    if c_type and c_type in df_view.columns:
        by_type = df_view.groupby(c_type, as_index=False)[c_val].sum()
        fig1 = px.pie(by_type, values=c_val, names=c_type,
                      title="Por tipo", color_discrete_sequence=px.colors.qualitative.Set2)
        c1.plotly_chart(fig1, use_container_width=True)

    by_month = df_exp.groupby("_month", as_index=False)[c_val].sum().sort_values("_month")
    fig2 = px.bar(by_month, x="_month", y=c_val, title="Gastos mensais",
                  labels={"_month": "Mês", c_val: "R$"},
                  color_discrete_sequence=["#636EFA"])
    c2.plotly_chart(fig2, use_container_width=True)

    st.subheader("Últimos lançamentos")
    show_cols = [c for c in [c_date, c_desc, c_type, c_val] if c]
    st.dataframe(df_view[show_cols].sort_values(c_date, ascending=False).head(30),
                 use_container_width=True)


# ════════════════════════════════════════════════════════════════════
# PÁGINA: LANÇAR DESPESA
# ════════════════════════════════════════════════════════════════════
elif page == "➕ Lançar despesa":
    st.title("➕ Novo lançamento")

    nc_cat = name_col(df_cats) if not df_cats.empty else "name"
    nc_pay = name_col(df_pays) if not df_pays.empty else "name"
    nc_acc = name_col(df_accs) if not df_accs.empty else "name"

    cat_opts = df_cats[nc_cat].tolist() if not df_cats.empty else []
    pay_opts = df_pays[nc_pay].tolist() if not df_pays.empty else []
    acc_opts = df_accs[nc_acc].tolist() if not df_accs.empty else []

    with st.form("expense_form", clear_on_submit=True):
        r1c1, r1c2, r1c3 = st.columns([1, 2, 1])
        expense_date = r1c1.date_input("Data", value=date.today())
        description  = r1c2.text_input("Descrição *")
        expense_type = r1c3.selectbox("Tipo *", ["Fixa", "Variável", "Parcelada"])

        r2c1, r2c2, r2c3 = st.columns(3)
        category_name = r2c1.selectbox("Categoria",          cat_opts or ["Sem cadastro"])
        payment_name  = r2c2.selectbox("Forma de pagamento", pay_opts or ["Sem cadastro"])
        account_name  = r2c3.selectbox("Conta / Cartão",     acc_opts or ["Sem cadastro"])

        r3c1, r3c2 = st.columns([1, 2])
        total_value = r3c1.number_input("Valor total (R$) *", min_value=0.01, step=10.0, format="%.2f")
        notes       = r3c2.text_input("Observações")

        num_inst = 1
        if expense_type == "Parcelada":
            num_inst = st.number_input("Nº de parcelas *", min_value=2, max_value=60, value=2, step=1)

        submitted = st.form_submit_button("💾 Salvar", use_container_width=True)

    if submitted:
        if not description.strip():
            st.error("Informe a descrição.")
        else:
            # Monta payload com nomes que existem na tabela despesas
            # Usa os nomes reais detectados, com fallback para inglês
            c_date_real  = col(df_exp, "expense_date")  or "expense_date"
            c_desc_real  = col(df_exp, "description")   or "description"
            c_type_real  = col(df_exp, "expense_type")  or "expense_type"
            c_val_real   = col(df_exp, "total_value")   or "total_value"
            c_notes_real = col(df_exp, "notes")         or "notes"
            c_cat_real   = col(df_exp, "category_id")   or "category_id"
            c_pay_real   = col(df_exp, "payment_method_id") or "payment_method_id"
            c_acc_real   = col(df_exp, "account_id")    or "account_id"

            payload = {
                c_date_real:  expense_date.isoformat(),
                c_desc_real:  description.strip(),
                c_type_real:  expense_type,
                c_val_real:   float(total_value),
                c_cat_real:   id_from_name(df_cats, category_name),
                c_pay_real:   id_from_name(df_pays, payment_name),
                c_acc_real:   id_from_name(df_accs, account_name),
                c_notes_real: notes.strip(),
            }
            # Remove chaves com valor None para evitar erro de FK
            payload = {k: v for k, v in payload.items() if v is not None or k in (c_date_real, c_desc_real)}

            try:
                res = supabase.table(TB_DESPESAS).insert(payload).execute()
                if res.data:
                    expense_id = res.data[0]["id"]
                    if expense_type == "Parcelada" and num_inst >= 2:
                        inst_val = round(float(total_value) / num_inst, 2)
                        parcelas = []
                        for i in range(num_inst):
                            due = expense_date + relativedelta(months=i)
                            parcelas.append({
                                "expense_id":          expense_id,
                                "installment_number":  i + 1,
                                "total_installments":  num_inst,
                                "due_month":           due.replace(day=1).isoformat(),
                                "installment_value":   inst_val,
                                "paid":                False,
                            })
                        try:
                            supabase.table(TB_PARCELAS).insert(parcelas).execute()
                        except Exception as ep:
                            st.warning(f"Despesa salva, mas erro ao gerar parcelas: {ep}")
                    st.success("✅ Salvo com sucesso!")
                    refresh()
                else:
                    st.error("Supabase não retornou dados. Verifique as colunas na aba Diagnóstico.")
            except Exception as e:
                st.error(f"Erro: {e}")


# ════════════════════════════════════════════════════════════════════
# PÁGINA: PARCELADAS
# ════════════════════════════════════════════════════════════════════
elif page == "💳 Parceladas":
    st.title("💳 Despesas parceladas")

    if df_inst.empty:
        st.info("Nenhuma parcela ainda, ou tabela 'edições' vazia.")
        st.stop()

    c_due   = col(df_inst, "due_month")
    c_ival  = col(df_inst, "installment_value")
    c_paid  = col(df_inst, "paid")

    if not c_due or not c_ival:
        st.error("Colunas esperadas não encontradas em 'edições'. Veja **🔎 Diagnóstico**.")
        st.dataframe(df_inst.head(), use_container_width=True)
        st.stop()

    df_inst[c_due]  = pd.to_datetime(df_inst[c_due])
    df_inst[c_ival] = df_inst[c_ival].astype(float)
    df_inst["_ml"]  = df_inst[c_due].dt.strftime("%Y-%m")

    if c_paid:
        pending = df_inst[df_inst[c_paid] == False].copy()
        paid_df = df_inst[df_inst[c_paid] == True].copy()
    else:
        pending = df_inst.copy()
        paid_df = pd.DataFrame()

    k1, k2, k3 = st.columns(3)
    k1.metric("Em aberto",  len(pending))
    k2.metric("Total aberto", money(pending[c_ival].sum()))
    k3.metric("Total pago",   money(paid_df[c_ival].sum() if not paid_df.empty else 0))

    if not pending.empty:
        summary = pending.groupby("_ml", as_index=False)[c_ival].sum().sort_values("_ml")
        fig = px.bar(summary, x="_ml", y=c_ival, title="Parcelas em aberto por mês",
                     labels={"_ml": "Mês", c_ival: "R$"},
                     color_discrete_sequence=["#EF553B"])
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Parcelas em aberto")
        st.dataframe(pending.sort_values(c_due), use_container_width=True)

        if c_paid:
            with st.form("mark_paid"):
                inst_id = st.number_input("ID da parcela para marcar como paga", min_value=1, step=1)
                if st.form_submit_button("✅ Marcar paga"):
                    try:
                        supabase.table(TB_PARCELAS).update({c_paid: True}).eq("id", int(inst_id)).execute()
                        st.success("Marcada como paga.")
                        refresh()
                    except Exception as e:
                        st.error(f"Erro: {e}")
    else:
        st.success("🎉 Sem parcelas em aberto!")


# ════════════════════════════════════════════════════════════════════
# PÁGINA: CADASTROS
# ════════════════════════════════════════════════════════════════════
elif page == "🗂️ Cadastros":
    st.title("🗂️ Cadastros auxiliares")
    tab1, tab2, tab3 = st.tabs(["Categorias", "Formas de pagamento", "Contas / Cartões"])

    def render_crud(tab, table_name: str, df: pd.DataFrame, label: str):
        with tab:
            nc = name_col(df) if not df.empty else "name"
            # Detecta colunas extras além das padrão
            skip = {"id", "name", "nome", "created_at", "updated_at", nc}
            extra_cols = [c for c in df.columns if c not in skip] if not df.empty else []

            st.subheader(f"Adicionar {label}")
            with st.form(f"add_{table_name}", clear_on_submit=True):
                nm = st.text_input("Nome")
                extra_vals = {}
                for ec in extra_cols:
                    if ec == "type":
                        extra_vals[ec] = st.selectbox(
                            "Tipo (obrigatório pela tabela)",
                            ["expense", "income"],
                            format_func=lambda x: "Despesa" if x == "expense" else "Receita"
                        )
                    else:
                        extra_vals[ec] = st.text_input(f"Campo extra: {ec}")
                if st.form_submit_button("➕ Adicionar"):
                    if not nm.strip():
                        st.error("Informe um nome.")
                    else:
                        try:
                            payload = {nc: nm.strip(), **extra_vals}
                            supabase.table(table_name).insert(payload).execute()
                            st.success(f"'{nm}' adicionado.")
                            refresh()
                        except Exception as e:
                            st.error(f"Erro: {e}")
            st.subheader(f"{label}s")
            if df.empty:
                st.info("Vazio.")
            else:
                cols_show = ["id", nc] if nc in df.columns else df.columns.tolist()
                st.dataframe(df[cols_show], use_container_width=True)
                with st.form(f"del_{table_name}"):
                    del_id = st.number_input("ID para excluir", min_value=1, step=1)
                    if st.form_submit_button("🗑️ Excluir"):
                        try:
                            supabase.table(table_name).delete().eq("id", int(del_id)).execute()
                            st.success("Excluído.")
                            refresh()
                        except Exception as e:
                            st.error(f"Erro: {e}")

    # CATEGORIAS — tem coluna type NOT NULL (hardcoded)
    with tab1:
        st.subheader("Adicionar Categoria")
        with st.form("add_categories", clear_on_submit=True):
            nm   = st.text_input("Nome")
            tipo = st.selectbox("Tipo", ["fixa", "variavel", "parcelada", "cartao", "outro"], format_func=lambda x: {"fixa":"Fixa","variavel":"Variável","parcelada":"Parcelada","cartao":"Cartão","outro":"Outro"}[x])
            if st.form_submit_button("\u2795 Adicionar"):
                if not nm.strip():
                    st.error("Informe um nome.")
                else:
                    try:
                        supabase.table(TB_CATEGORIAS).insert({"name": nm.strip(), "type": tipo}).execute()
                        st.success(f"'{nm}' adicionada.")
                        refresh()
                    except Exception as e:
                        st.error(f"Erro: {e}")
        st.subheader("Categorias cadastradas")
        if df_cats.empty:
            st.info("Nenhuma cadastrada.")
        else:
            st.dataframe(df_cats, use_container_width=True)
            with st.form("del_categories"):
                del_id = st.number_input("ID para excluir", min_value=1, step=1)
                if st.form_submit_button("\U0001f5d1\ufe0f Excluir"):
                    try:
                        supabase.table(TB_CATEGORIAS).delete().eq("id", str(del_id)).execute()
                        st.success("Exclu\u00eddo.")
                        refresh()
                    except Exception as e:
                        st.error(f"Erro: {e}")
    render_crud(tab2, TB_PAGAMENTOS, df_pays, "Forma de pagamento")
    render_crud(tab3, TB_CONTAS,     df_accs, "Conta / Cartão")


# ════════════════════════════════════════════════════════════════════
# PÁGINA: DIAGNÓSTICO
# ════════════════════════════════════════════════════════════════════
elif page == "🔎 Diagnóstico":
    st.title("🔎 Diagnóstico de tabelas")
    st.caption("Use esta página para verificar se as tabelas e colunas estão corretas.")

    tabelas = {
        TB_DESPESAS:   df_exp,
        TB_PARCELAS:   df_inst,
        TB_CATEGORIAS: df_cats,
        TB_PAGAMENTOS: df_pays,
        TB_CONTAS:     df_accs,
    }

    for nome, df in tabelas.items():
        with st.expander(f"📋 `{nome}` — {len(df)} linhas", expanded=True):
            if df.empty:
                st.warning("Vazia ou inacessível.")
            else:
                st.write("**Colunas detectadas:**", list(df.columns))
                st.dataframe(df.head(3), use_container_width=True)
