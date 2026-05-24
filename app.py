"""
Controle Financeiro Doméstico
Streamlit + Supabase
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
    url = raw_url.split("/rest/")[0].split("/auth/")[0].rstrip("/")
    return create_client(url, st.secrets["SUPABASE_ANON_KEY"])

supabase = get_supabase()

TB_DESPESAS   = "expenses"
TB_CATEGORIAS = "categories"
TB_CONTAS     = "accounts"
TB_PAGAMENTOS = "payment_methods"
TB_PARCELAS   = "installments"
TB_ENTRADAS   = "incomes"

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
    except Exception:
        return pd.DataFrame()

def name_col(df: pd.DataFrame) -> str:
    for c in ["name", "nome", "descricao", "descrição", "title"]:
        if c in df.columns:
            return c
    return df.columns[1] if len(df.columns) > 1 else df.columns[0]

def id_from_name(df: pd.DataFrame, chosen: str):
    if df.empty or chosen in ("Sem cadastro", ""):
        return None
    nc = name_col(df)
    rows = df.loc[df[nc] == chosen, "id"]
    return rows.iloc[0] if not rows.empty else None

def fc(df, *candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

# ── Cache ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_all():
    return {
        "despesas":   safe_query(TB_DESPESAS),
        "parcelas":   safe_query(TB_PARCELAS),
        "categorias": safe_query(TB_CATEGORIAS),
        "pagamentos": safe_query(TB_PAGAMENTOS),
        "contas":     safe_query(TB_CONTAS),
        "entradas":   safe_query(TB_ENTRADAS),
    }

def refresh():
    load_all.clear()
    st.rerun()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("💰 Finanças")
    st.caption("Controle doméstico pessoal")
    page = st.radio("Menu", [
        "📊 Visão geral",
        "💵 Entradas",
        "➕ Despesa simples",
        "💳 Despesa parcelada",
        "🗑️ Gerenciar",
        "🗂️ Cadastros",
        "🔎 Diagnóstico",
    ], label_visibility="collapsed")
    st.divider()
    if st.button("🔄 Recarregar"):
        refresh()

data    = load_all()
df_exp  = data["despesas"].copy()
df_inst = data["parcelas"].copy()
df_cats = data["categorias"].copy()
df_pays = data["pagamentos"].copy()
df_accs = data["contas"].copy()
df_inc  = data["entradas"].copy()


# ════════════════════════════════════════════════════════════════════
# VISÃO GERAL
# ════════════════════════════════════════════════════════════════════
if page == "📊 Visão geral":
    st.title("📊 Visão geral")

    c_date = fc(df_exp, "expense_date", "data", "date")
    c_val  = fc(df_exp, "total_value",  "valor", "value", "amount")
    c_type = fc(df_exp, "expense_type", "tipo",  "type")
    c_desc = fc(df_exp, "description",  "descricao", "nome")
    ci_pay = fc(df_inc, "payment_date", "data_pagamento", "data", "date")
    ci_val = fc(df_inc, "value",        "valor", "amount", "total_value")
    ci_type= fc(df_inc, "income_type",  "tipo",  "type")

    has_exp = not df_exp.empty and c_date and c_val
    has_inc = not df_inc.empty and ci_val

    # Preparar parcelas para usar no lugar do valor total de parceladas
    c_due_v  = fc(df_inst, "due_month", "vencimento", "due_date")
    c_ival_v = fc(df_inst, "installment_value", "valor_parcela", "value")
    c_paid_v = fc(df_inst, "paid", "pago")
    has_inst = not df_inst.empty and c_due_v and c_ival_v

    if has_exp:
        df_exp[c_date]   = pd.to_datetime(df_exp[c_date])
        df_exp["_month"] = df_exp[c_date].dt.to_period("M").astype(str)
        df_exp[c_val]    = df_exp[c_val].astype(float)
        # Separar fixas/variáveis das parceladas
        if c_type:
            df_simples   = df_exp[df_exp[c_type] != "Parcelada"].copy()
        else:
            df_simples   = df_exp.copy()

    if has_inst:
        df_inst[c_due_v]  = pd.to_datetime(df_inst[c_due_v])
        df_inst["_month"] = df_inst[c_due_v].dt.to_period("M").astype(str)
        df_inst[c_ival_v] = df_inst[c_ival_v].astype(float)

    if has_inc and ci_pay:
        df_inc[ci_pay]    = pd.to_datetime(df_inc[ci_pay])
        df_inc["_month"]  = df_inc[ci_pay].dt.to_period("M").astype(str)
        df_inc[ci_val]    = df_inc[ci_val].astype(float)

    all_months = set()
    if has_exp:  all_months |= set(df_exp["_month"].unique())
    if has_inst: all_months |= set(df_inst["_month"].unique())
    if has_inc and "_month" in df_inc.columns: all_months |= set(df_inc["_month"].unique())
    months = sorted(all_months, reverse=True)

    MESES_PT = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
                7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}

    sel = st.selectbox("Filtrar mês", ["Todos"] + months,
                       format_func=lambda x: x if x == "Todos" else
                       f"{MESES_PT[int(x.split('-')[1])]} {x.split('-')[0]}")

    # Despesas simples (Fixa + Variável) no mês
    dv = (df_simples if sel == "Todos" else df_simples[df_simples["_month"] == sel]) if has_exp else pd.DataFrame()
    # Parcelas do mês
    dp = (df_inst if sel == "Todos" else df_inst[df_inst["_month"] == sel]) if has_inst else pd.DataFrame()
    di = (df_inc if sel == "Todos" else df_inc[df_inc["_month"] == sel]) if (has_inc and "_month" in df_inc.columns) else df_inc if has_inc else pd.DataFrame()

    saida_simples  = dv[c_val].sum()    if has_exp  and not dv.empty else 0
    saida_parcelas = dp[c_ival_v].sum() if has_inst and not dp.empty else 0
    total_saida    = saida_simples + saida_parcelas
    total_entrada  = di[ci_val].sum()   if has_inc  and not di.empty else 0

    # Separar obrigações religiosas das demais entradas
    sal_val = obg_val = 0
    if has_inc and not di.empty and ci_type:
        sal_val = di[di[ci_type].isin(["salario", "salário", "outros"])][ci_val].sum()
        obg_val = di[di[ci_type].isin(["primicias", "primícias", "maaser", "tzedaka", "tzedaká"])][ci_val].sum()

    saldo = total_entrada - total_saida

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("💵 Entradas",       money(total_entrada))
    k2.metric("💸 Fixas/Variáveis",money(saida_simples))
    k3.metric("💳 Parcelas mês",   money(saida_parcelas))
    k4.metric("💰 Saldo",          money(saldo),
              delta=("positivo" if saldo >= 0 else "negativo"),
              delta_color="normal" if saldo >= 0 else "inverse")
    k5.metric("🕍 Obrigações",     money(obg_val),
              help="Primícias + Maaser + Tzedaká")

    st.divider()

    # Gráfico entradas x saídas
    if has_exp and has_inc and "_month" in df_inc.columns:
        by_exp = df_exp.groupby("_month")[c_val].sum().rename("Saídas")
        by_inc = df_inc.groupby("_month")[ci_val].sum().rename("Entradas")
        bal    = pd.concat([by_exp, by_inc], axis=1).fillna(0).reset_index()
        bal_m  = bal.melt(id_vars=bal.columns[0], var_name="Tipo", value_name="R$")
        fig = px.bar(bal_m, x=bal.columns[0], y="R$", color="Tipo", barmode="group",
                     title="Entradas vs Saídas por mês",
                     color_discrete_map={"Entradas":"#00CC96","Saídas":"#EF553B"})
        st.plotly_chart(fig, use_container_width=True)
    elif has_exp:
        by_m = df_exp.groupby("_month", as_index=False)[c_val].sum().sort_values("_month")
        fig  = px.bar(by_m, x="_month", y=c_val, title="Saídas por mês",
                      color_discrete_sequence=["#EF553B"])
        st.plotly_chart(fig, use_container_width=True)

    # Tabelas resumo
    c1, c2 = st.columns(2)
    if has_exp and not dv.empty:
        with c1:
            st.subheader("Últimas despesas")
            show = [x for x in [c_date, c_desc, c_type, c_val] if x]
            st.dataframe(dv[show].sort_values(c_date, ascending=False).head(15),
                         use_container_width=True)
    if has_inc and not di.empty:
        with c2:
            st.subheader("Entradas")
            show_i = [x for x in [ci_pay, ci_type, ci_val] if x]
            st.dataframe(di[show_i].sort_values(ci_pay, ascending=False).head(15)
                         if ci_pay else di[show_i], use_container_width=True)

    # Parcelas do mês selecionado
    if not df_inst.empty:
        c_due  = fc(df_inst, "due_month", "vencimento", "due_date")
        c_ival = fc(df_inst, "installment_value", "valor_parcela", "value")
        c_paid = fc(df_inst, "paid", "pago")
        if c_due and c_ival:
            df_inst[c_due]  = pd.to_datetime(df_inst[c_due])
            df_inst["_m"]   = df_inst[c_due].dt.to_period("M").astype(str)
            df_inst[c_ival] = df_inst[c_ival].astype(float)
            pend = df_inst[(df_inst[c_paid] == False) & (df_inst["_m"] == sel)] if c_paid and sel != "Todos" else df_inst[df_inst[c_paid] == False] if c_paid else df_inst
            if not pend.empty:
                st.divider()
                st.subheader(f"💳 Parcelas em aberto {'' if sel == 'Todos' else sel}")
                st.metric("Total parcelas", money(pend[c_ival].sum()))
                st.dataframe(pend.sort_values(c_due), use_container_width=True)


# ════════════════════════════════════════════════════════════════════
# ENTRADAS
# ════════════════════════════════════════════════════════════════════
elif page == "💵 Entradas":
    st.title("💵 Entradas")

    # SQL para criar tabela incomes se não existir
    inc_sql = """
CREATE TABLE IF NOT EXISTS incomes (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description      TEXT NOT NULL,
    income_type      TEXT NOT NULL DEFAULT 'salario',
    value            NUMERIC(12,2) NOT NULL,
    payment_date     DATE NOT NULL,
    competence_month DATE NOT NULL,
    account_id       UUID REFERENCES accounts(id) ON DELETE SET NULL,
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE incomes DISABLE ROW LEVEL SECURITY;
"""

    tab_sal, tab_obg, tab_hist = st.tabs(["💼 Salário / Outras entradas", "🕍 Obrigações", "📋 Histórico"])

    acc_opts = df_accs[name_col(df_accs)].tolist() if not df_accs.empty else []

    # ── ABA: SALÁRIO
    with tab_sal:
        st.subheader("Lançar salário ou outra entrada")
        with st.form("income_sal", clear_on_submit=True):
            r1, r2, r3 = st.columns(3)
            income_type   = r1.selectbox("Tipo", ["salario", "outros"],
                                         format_func=lambda x: {"salario":"Salário","outros":"Outras entradas"}[x])
            description   = r2.text_input("Descrição (ex: Salário Maio/2026)")
            account_name  = r3.selectbox("Conta", acc_opts or ["Sem cadastro"])

            r4, r5, r6 = st.columns(3)
            value             = r4.number_input("Valor bruto (R$)*", min_value=0.01, step=100.0, format="%.2f")
            payment_date      = r5.date_input("Data de pagamento",   value=date.today(),
                                               help="Quando o dinheiro entrou na conta")
            competence_month  = r6.date_input("Mês de competência",
                                               value=date.today().replace(day=1) - relativedelta(months=1),
                                               help="Mês que você trabalhou (ex: maio p/ salário pago em junho)")
            notes = st.text_input("Observações")

            # Sugestão automática
            if value > 0:
                primicias = value / 30
                maaser    = value * 0.10
                st.info(f"💡 Primícias (salário ÷ 30): **{money(primicias)}**   |   Maaser (10%): **{money(maaser)}**   |   Tzedaká: livre")

            submitted = st.form_submit_button("💾 Salvar entrada", use_container_width=True)

        if submitted:
            if not description.strip():
                st.error("Informe a descrição.")
            else:
                payload = {
                    "description":      description.strip(),
                    "income_type":      income_type,
                    "value":            float(value),
                    "payment_date":     payment_date.isoformat(),
                    "competence_month": competence_month.replace(day=1).isoformat(),
                    "account_id":       id_from_name(df_accs, account_name),
                    "notes":            notes.strip(),
                }
                payload = {k: v for k, v in payload.items() if v is not None and v != ""}
                try:
                    res = supabase.table(TB_ENTRADAS).insert(payload).execute()
                    if res.data:
                        st.success("✅ Entrada salva!")
                        refresh()
                    else:
                        st.error("Não foi possível salvar. Crie a tabela incomes se ainda não existir.")
                        st.code(inc_sql, language="sql")
                except Exception as e:
                    st.error(f"Erro: {e}")
                    st.info("Se a tabela não existir, rode o SQL abaixo no DBeaver ou Supabase:")
                    st.code(inc_sql, language="sql")

    # ── ABA: OBRIGAÇÕES
    with tab_obg:
        st.subheader("Primícias | Maaser (Dízimo) | Tzedaká")
        st.caption("Esses valores são saídas especiais — registrados como entrada negativa / comprometimento.")

        with st.form("income_obg", clear_on_submit=True):
            r1, r2 = st.columns(2)
            obg_type = r1.selectbox("Tipo", ["primicias", "maaser", "tzedaka"],
                                    format_func=lambda x: {
                                        "primicias": "🌾 Primícias",
                                        "maaser":    "🕍 Maaser (Dízimo 10%)",
                                        "tzedaka":   "🤲 Tzedaká (Caridade)"
                                    }[x])
            account_name = r2.selectbox("Conta", acc_opts or ["Sem cadastro"])

            r3, r4, r5 = st.columns(3)
            value            = r3.number_input("Valor (R$)*", min_value=0.01, step=10.0, format="%.2f")
            payment_date     = r4.date_input("Data do pagamento", value=date.today())
            competence_month = r5.date_input("Mês de competência",
                                              value=date.today().replace(day=1))
            description = st.text_input("Observações (opcional)")

            st.info("💡 Referência: Maaser = 10% do salário bruto. Primícias = 10% (ou conforme sua prática). Tzedaká = valor que desejar.")

            submitted_obg = st.form_submit_button("💾 Salvar obrigação", use_container_width=True)

        if submitted_obg:
            labels = {"primicias":"Primícias","maaser":"Maaser","tzedaka":"Tzedaká"}
            desc   = description.strip() or labels[obg_type]
            payload = {
                "description":      desc,
                "income_type":      obg_type,
                "value":            float(value),
                "payment_date":     payment_date.isoformat(),
                "competence_month": competence_month.replace(day=1).isoformat(),
                "account_id":       id_from_name(df_accs, account_name),
            }
            payload = {k: v for k, v in payload.items() if v is not None}
            try:
                res = supabase.table(TB_ENTRADAS).insert(payload).execute()
                if res.data:
                    st.success(f"✅ {labels[obg_type]} registrada!")
                    refresh()
                else:
                    st.error("Não foi possível salvar.")
            except Exception as e:
                st.error(f"Erro: {e}")

    # ── ABA: HISTÓRICO
    with tab_hist:
        st.subheader("Histórico de entradas e obrigações")
        if df_inc.empty:
            st.info("Nenhum registro ainda.")
        else:
            ci_type = fc(df_inc, "income_type", "tipo", "type")
            ci_val  = fc(df_inc, "value", "valor")
            ci_pay  = fc(df_inc, "payment_date", "data_pagamento", "data")

            # KPIs por tipo
            if ci_type and ci_val:
                df_inc[ci_val] = df_inc[ci_val].astype(float)
                tipos = {
                    "💼 Salário":   ["salario"],
                    "🌾 Primícias": ["primicias", "primícias"],
                    "🕍 Maaser":    ["maaser"],
                    "🤲 Tzedaká":   ["tzedaka", "tzedaká"],
                    "📦 Outros":    ["outros"],
                }
                cols = st.columns(len(tipos))
                for i, (label, keys) in enumerate(tipos.items()):
                    total = df_inc[df_inc[ci_type].isin(keys)][ci_val].sum()
                    cols[i].metric(label, money(total))

            st.dataframe(df_inc.sort_values(ci_pay, ascending=False) if ci_pay else df_inc,
                         use_container_width=True)


# ════════════════════════════════════════════════════════════════════
# DESPESA SIMPLES (Fixa / Variável)
# ════════════════════════════════════════════════════════════════════
elif page == "➕ Despesa simples":
    st.title("➕ Despesa simples")
    st.caption("Para despesas **Fixas** (energia, internet, água...) e **Variáveis** (mercado, lazer...)")

    cat_opts = df_cats[name_col(df_cats)].tolist() if not df_cats.empty else []
    pay_opts = df_pays[name_col(df_pays)].tolist() if not df_pays.empty else []
    acc_opts = df_accs[name_col(df_accs)].tolist() if not df_accs.empty else []

    with st.form("expense_simple", clear_on_submit=True):
        r1, r2, r3 = st.columns([2, 1, 1])
        description   = r1.text_input("Descrição *  (ex: Energia Elétrica Maio/26)")
        expense_date  = r2.date_input("Data de vencimento / pagamento", value=date.today(),
                                       help="Data em que vence ou foi pago")
        expense_type  = r3.selectbox("Tipo", ["Fixa", "Variavel"])

        r4, r5, r6 = st.columns(3)
        category_name = r4.selectbox("Categoria",          cat_opts or ["Sem cadastro"])
        payment_name  = r5.selectbox("Forma de pagamento", pay_opts or ["Sem cadastro"])
        account_name  = r6.selectbox("Cartão / Conta",     acc_opts or ["Sem cadastro"])

        r7, r8 = st.columns([1, 2])
        total_value = r7.number_input("Valor (R$) *", min_value=0.01, step=10.0, format="%.2f")
        notes       = r8.text_input("Observações")

        submitted = st.form_submit_button("💾 Salvar", use_container_width=True)

    if submitted:
        if not description.strip():
            st.error("Informe a descrição.")
        else:
            payload = {
                "expense_date":      expense_date.isoformat(),
                "description":       description.strip(),
                "expense_type":      expense_type,
                "total_value":       float(total_value),
                "category_id":       id_from_name(df_cats, category_name),
                "payment_method_id": id_from_name(df_pays, payment_name),
                "account_id":        id_from_name(df_accs, account_name),
                "notes":             notes.strip(),
            }
            payload = {k: v for k, v in payload.items() if v is not None and v != ""}
            try:
                res = supabase.table(TB_DESPESAS).insert(payload).execute()
                if res.data:
                    st.success("✅ Salvo!")
                    refresh()
                else:
                    st.error("Não foi possível salvar.")
            except Exception as e:
                st.error(f"Erro: {e}")


# ════════════════════════════════════════════════════════════════════
# DESPESA PARCELADA
# ════════════════════════════════════════════════════════════════════
elif page == "💳 Despesa parcelada":
    st.title("💳 Despesa parcelada")

    cat_opts = df_cats[name_col(df_cats)].tolist() if not df_cats.empty else []
    pay_opts = df_pays[name_col(df_pays)].tolist() if not df_pays.empty else []
    acc_opts = df_accs[name_col(df_accs)].tolist() if not df_accs.empty else []

    tab_novo, tab_resumo, tab_detalhe = st.tabs(["➕ Nova parcelada", "📊 Resumo por mês", "📋 Detalhes"])

    # ── ABA: NOVA PARCELADA
    with tab_novo:
        with st.form("expense_parcel", clear_on_submit=True):
            r1, r2 = st.columns([3, 1])
            description   = r1.text_input("Descrição *  (ex: Tratamento Dentário)")
            purchase_date = r2.date_input("Data da compra", value=date.today(),
                                          help="Quando comprou / contratou")

            r3, r4, r5 = st.columns(3)
            category_name = r3.selectbox("Categoria",            cat_opts or ["Sem cadastro"])
            payment_name  = r4.selectbox("Forma de pagamento",   pay_opts or ["Sem cadastro"])
            account_name  = r5.selectbox("Cartão / Conta usado", acc_opts or ["Sem cadastro"])

            r6, r7, r8 = st.columns(3)
            total_value = r6.number_input("Valor TOTAL (R$) *", min_value=0.01, step=10.0, format="%.2f")
            num_inst    = r7.number_input("Nº de parcelas *",   min_value=2, max_value=60, value=2, step=1)
            first_due   = r8.date_input("Vencimento 1ª parcela", value=date.today(),
                                        help="Quando cai a primeira parcela")
            notes = st.text_input("Observações")

            if total_value > 0 and num_inst > 0:
                inst_val = total_value / num_inst
                st.info(f"📐 {int(num_inst)}x de **{money(inst_val)}** = {money(total_value)}")

            submitted = st.form_submit_button("💾 Salvar e gerar parcelas", use_container_width=True)

        if submitted:
            if not description.strip():
                st.error("Informe a descrição.")
            else:
                inst_val = round(float(total_value) / num_inst, 2)
                payload = {
                    "expense_date":      purchase_date.isoformat(),
                    "description":       description.strip(),
                    "expense_type":      "Parcelada",
                    "total_value":       float(total_value),
                    "category_id":       id_from_name(df_cats, category_name),
                    "payment_method_id": id_from_name(df_pays, payment_name),
                    "account_id":        id_from_name(df_accs, account_name),
                    "notes":             notes.strip(),
                }
                payload = {k: v for k, v in payload.items() if v is not None and v != ""}
                try:
                    res = supabase.table(TB_DESPESAS).insert(payload).execute()
                    if res.data:
                        expense_id = res.data[0]["id"]
                        parcelas = []
                        for i in range(int(num_inst)):
                            due = first_due + relativedelta(months=i)
                            parcelas.append({
                                "expense_id":         expense_id,
                                "installment_number": i + 1,
                                "total_installments": int(num_inst),
                                "due_month":          due.replace(day=1).isoformat(),
                                "installment_value":  inst_val,
                                "paid":               False,
                            })
                        try:
                            supabase.table(TB_PARCELAS).insert(parcelas).execute()
                            st.success(f"✅ {int(num_inst)}x de {money(inst_val)} geradas!")
                        except Exception as ep:
                            st.warning(f"Despesa salva, mas erro nas parcelas: {ep}")
                        refresh()
                    else:
                        st.error("Não foi possível salvar.")
                except Exception as e:
                    st.error(f"Erro: {e}")

    # Preparar dados de parcelas para as outras abas
    c_due  = fc(df_inst, "due_month",          "vencimento", "due_date")
    c_ival = fc(df_inst, "installment_value",   "valor_parcela", "value")
    c_paid = fc(df_inst, "paid",                "pago")
    c_eid  = fc(df_inst, "expense_id",          "despesa_id")
    c_inum = fc(df_inst, "installment_number",  "numero_parcela")
    c_itot = fc(df_inst, "total_installments",  "total_parcelas")

    MESES_PT = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
                7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}

    has_inst = not df_inst.empty and c_due and c_ival and c_paid

    if has_inst:
        df_inst[c_due]  = pd.to_datetime(df_inst[c_due])
        df_inst[c_ival] = df_inst[c_ival].astype(float)
        df_inst["_ano"] = df_inst[c_due].dt.year
        df_inst["_mes"] = df_inst[c_due].dt.month
        df_inst["_ym"]  = df_inst[c_due].dt.to_period("M").astype(str)
        df_inst["_mes_label"] = df_inst.apply(
            lambda r: f"{MESES_PT[r['_mes']]} {r['_ano']}", axis=1)

        # Juntar com expenses para pegar descrição
        c_exp_desc = fc(df_exp, "description", "descricao", "nome")
        if c_eid and c_exp_desc and not df_exp.empty:
            desc_map = df_exp.set_index("id")[c_exp_desc].to_dict()
            df_inst["_descricao"] = df_inst[c_eid].map(desc_map).fillna("—")
        else:
            df_inst["_descricao"] = "—"

    # ── ABA: RESUMO POR MÊS
    with tab_resumo:
        if not has_inst:
            st.info("Nenhuma parcela cadastrada ainda.")
        else:
            st.subheader("Resumo mensal de parcelas")

            # Totais globais
            total_pago   = df_inst[df_inst[c_paid] == True][c_ival].sum()
            total_aberto = df_inst[df_inst[c_paid] == False][c_ival].sum()
            k1, k2, k3 = st.columns(3)
            k1.metric("✅ Total já pago",     money(total_pago))
            k2.metric("⏳ Total em aberto",   money(total_aberto))
            k3.metric("📦 Total comprometido",money(total_pago + total_aberto))

            st.divider()

            # Tabela por mês — pago x em aberto
            resumo = df_inst.groupby(["_mes_label","_ym",c_paid])[c_ival].sum().reset_index()
            resumo.columns = ["Mês","_ym","Pago","Valor"]
            pivot = resumo.pivot_table(index=["Mês","_ym"], columns="Pago",
                                       values="Valor", aggfunc="sum").reset_index()
            pivot.columns.name = None
            pivot = pivot.rename(columns={False:"Em aberto (R$)", True:"Pago (R$)"})
            pivot = pivot.sort_values("_ym")
            for col_r in ["Em aberto (R$)","Pago (R$)"]:
                if col_r not in pivot.columns:
                    pivot[col_r] = 0.0
            pivot["Em aberto (R$)"] = pivot["Em aberto (R$)"].fillna(0)
            pivot["Pago (R$)"]      = pivot["Pago (R$)"].fillna(0)
            pivot["Total mês"]      = pivot["Em aberto (R$)"] + pivot["Pago (R$)"]
            pivot_show = pivot[["Mês","Pago (R$)","Em aberto (R$)","Total mês"]].copy()

            # Formatar valores
            for col_r in ["Pago (R$)","Em aberto (R$)","Total mês"]:
                pivot_show[col_r] = pivot_show[col_r].apply(money)

            st.dataframe(pivot_show, use_container_width=True, hide_index=True)

            # Gráfico barras empilhadas pago x aberto
            fig = px.bar(
                pivot, x="Mês", y=["Pago (R$)","Em aberto (R$)"],
                barmode="stack",
                title="Parcelas por mês — Pago vs Em aberto",
                color_discrete_map={"Pago (R$)":"#00CC96","Em aberto (R$)":"#EF553B"},
                labels={"value":"R$","variable":"Status"},
            )
            fig.update_xaxes(tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)

    # ── ABA: DETALHES POR DESPESA
    with tab_detalhe:
        if not has_inst:
            st.info("Nenhuma parcela cadastrada.")
        else:
            st.subheader("Progresso por despesa")

            if c_eid and c_itot and c_inum:
                grupos = df_inst.groupby([c_eid, "_descricao"])
                for (eid, desc), grp in grupos:
                    pagas   = grp[grp[c_paid] == True]
                    abertas = grp[grp[c_paid] == False]
                    total_p = pagas[c_ival].sum()
                    total_a = abertas[c_ival].sum()
                    n_pagas = len(pagas)
                    n_total = grp[c_itot].iloc[0] if c_itot else len(grp)
                    prox    = abertas.sort_values(c_due).iloc[0] if not abertas.empty else None

                    with st.expander(
                        f"{'✅' if abertas.empty else '⏳'} **{desc}** — "
                        f"{n_pagas}/{n_total} pagas — "
                        f"Aberto: {money(total_a)}", expanded=not abertas.empty):

                        c1, c2, c3 = st.columns(3)
                        c1.metric("Pagas",    f"{n_pagas}/{n_total}", money(total_p))
                        c2.metric("Em aberto", money(total_a))
                        if prox is not None:
                            c3.metric("Próximo vencimento",
                                      f"{MESES_PT[prox[c_due].month]} {prox[c_due].year}",
                                      money(prox[c_ival]))

                        # Tabela de parcelas
                        cols_show = [c for c in [c_inum, "_mes_label", c_ival, c_paid] if c]
                        rename = {c_inum:"Parcela", "_mes_label":"Mês",
                                  c_ival:"Valor (R$)", c_paid:"Pago"}
                        sub = grp[cols_show].rename(columns=rename).sort_values("Parcela")
                        sub["Valor (R$)"] = sub["Valor (R$)"].apply(money)
                        sub["Pago"] = sub["Pago"].map({True:"✅ Sim", False:"⏳ Não"})
                        st.dataframe(sub, use_container_width=True, hide_index=True)

                        # Marcar como paga
                        if not abertas.empty:
                            with st.form(f"pagar_{eid}"):
                                inst_id = st.text_input("ID da parcela para marcar como paga",
                                                        key=f"inp_{eid}")
                                if st.form_submit_button("✅ Marcar paga"):
                                    try:
                                        supabase.table(TB_PARCELAS).update({c_paid: True}).eq("id", inst_id.strip()).execute()
                                        st.success("Marcada como paga.")
                                        refresh()
                                    except Exception as e:
                                        st.error(f"Erro: {e}")
            else:
                st.dataframe(df_inst, use_container_width=True)

# ════════════════════════════════════════════════════════════════════
# GERENCIAR (EXCLUIR)
# ════════════════════════════════════════════════════════════════════
elif page == "🗑️ Gerenciar":
    st.title("🗑️ Gerenciar lançamentos")

    tab_exp, tab_inc, tab_inst = st.tabs(["Despesas", "Entradas / Obrigações", "Parcelas"])

    def del_widget(table, df, tab, label, also_installments=False):
        with tab:
            if df.empty:
                st.info(f"Nenhum registro em {label}.")
                return
            st.dataframe(df, use_container_width=True)
            with st.form(f"del_{table}"):
                del_id  = st.text_input("ID para excluir (copie da tabela acima)")
                confirm = st.checkbox(f"Confirmo a exclusão deste {label.lower()}")
                if st.form_submit_button("🗑️ Excluir", use_container_width=True):
                    if not del_id.strip() or not confirm:
                        st.error("Informe o ID e confirme.")
                    else:
                        try:
                            if also_installments:
                                try:
                                    supabase.table(TB_PARCELAS).delete().eq("expense_id", del_id.strip()).execute()
                                except Exception:
                                    pass
                            supabase.table(table).delete().eq("id", del_id.strip()).execute()
                            st.success("Excluído com sucesso.")
                            refresh()
                        except Exception as e:
                            st.error(f"Erro: {e}")

    del_widget(TB_DESPESAS, df_exp,  tab_exp,  "Despesa",  also_installments=True)
    del_widget(TB_ENTRADAS, df_inc,  tab_inc,  "Entrada")
    del_widget(TB_PARCELAS, df_inst, tab_inst, "Parcela")


# ════════════════════════════════════════════════════════════════════
# CADASTROS
# ════════════════════════════════════════════════════════════════════
elif page == "🗂️ Cadastros":
    st.title("🗂️ Cadastros auxiliares")
    tab1, tab2, tab3 = st.tabs(["Categorias", "Formas de pagamento", "Contas / Cartões"])

    with tab1:
        st.subheader("Adicionar Categoria")
        with st.form("add_cat", clear_on_submit=True):
            nm   = st.text_input("Nome")
            tipo = st.selectbox("Tipo", ["fixa","variavel","parcelada","cartao","outro"],
                                format_func=lambda x: {"fixa":"Fixa","variavel":"Variável",
                                "parcelada":"Parcelada","cartao":"Cartão","outro":"Outro"}[x])
            if st.form_submit_button("➕ Adicionar"):
                if not nm.strip():
                    st.error("Informe um nome.")
                else:
                    try:
                        supabase.table(TB_CATEGORIAS).insert({"name": nm.strip(), "type": tipo}).execute()
                        st.success(f"'{nm}' adicionada.")
                        refresh()
                    except Exception as e:
                        st.error(f"Erro: {e}")
        if not df_cats.empty:
            st.dataframe(df_cats, use_container_width=True)
            with st.form("del_cat"):
                del_id = st.text_input("ID para excluir")
                if st.form_submit_button("🗑️ Excluir"):
                    try:
                        supabase.table(TB_CATEGORIAS).delete().eq("id", del_id.strip()).execute()
                        st.success("Excluído.")
                        refresh()
                    except Exception as e:
                        st.error(f"Erro: {e}")

    def render_crud(tab, table_name, df, label):
        with tab:
            nc     = name_col(df) if not df.empty else "name"
            skip   = {"id", "name", "nome", "created_at", "updated_at", nc}
            extras = [c for c in df.columns if c not in skip] if not df.empty else []
            int_c  = {c for c in extras if not df.empty and pd.api.types.is_numeric_dtype(df[c])}

            st.subheader(f"Adicionar {label}")
            with st.form(f"add_{table_name}", clear_on_submit=True):
                nm = st.text_input("Nome")
                ev = {}
                for ec in extras:
                    if ec in int_c:
                        v = st.number_input(f"{ec} (0 = vazio)", min_value=0, step=1, value=0)
                        ev[ec] = int(v) if v > 0 else None
                    elif ec == "kind":
                        ev[ec] = st.selectbox("Tipo",
                            ["corrente","poupanca","cartao_credito","cartao_debito","outro"],
                            format_func=lambda x: {"corrente":"Corrente","poupanca":"Poupança",
                            "cartao_credito":"Cartão Crédito","cartao_debito":"Cartão Débito",
                            "outro":"Outro"}.get(x, x))
                    else:
                        v = st.text_input(ec)
                        ev[ec] = v.strip() or None
                if st.form_submit_button("➕ Adicionar"):
                    if not nm.strip():
                        st.error("Informe um nome.")
                    else:
                        try:
                            pl = {k: v for k, v in {nc: nm.strip(), **ev}.items() if v is not None}
                            supabase.table(table_name).insert(pl).execute()
                            st.success(f"'{nm}' adicionado.")
                            refresh()
                        except Exception as e:
                            st.error(f"Erro: {e}")
            if not df.empty:
                st.dataframe(df, use_container_width=True)
                with st.form(f"del_{table_name}"):
                    del_id = st.text_input("ID para excluir")
                    if st.form_submit_button("🗑️ Excluir"):
                        try:
                            supabase.table(table_name).delete().eq("id", del_id.strip()).execute()
                            st.success("Excluído.")
                            refresh()
                        except Exception as e:
                            st.error(f"Erro: {e}")

    render_crud(tab2, TB_PAGAMENTOS, df_pays, "Forma de pagamento")
    render_crud(tab3, TB_CONTAS,     df_accs, "Conta / Cartão")


# ════════════════════════════════════════════════════════════════════
# DIAGNÓSTICO
# ════════════════════════════════════════════════════════════════════
elif page == "🔎 Diagnóstico":
    st.title("🔎 Diagnóstico")
    for nome, df in {
        TB_DESPESAS: df_exp, TB_PARCELAS: df_inst, TB_ENTRADAS: df_inc,
        TB_CATEGORIAS: df_cats, TB_PAGAMENTOS: df_pays, TB_CONTAS: df_accs,
    }.items():
        with st.expander(f"📋 `{nome}` — {len(df)} linhas", expanded=False):
            if df.empty:
                st.warning("Vazia ou inacessível.")
            else:
                st.write("**Colunas:**", list(df.columns))
                st.dataframe(df.head(3), use_container_width=True)
