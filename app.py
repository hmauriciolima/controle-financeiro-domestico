import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

st.set_page_config(
    page_title="Controle Financeiro Doméstico",
    page_icon="🏠",
    layout="wide",
)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

CATEGORIES_DEFAULT = [
    ("Supermercado", "variavel"),
    ("Energia", "fixa"),
    ("Água", "fixa"),
    ("Internet", "fixa"),
    ("Telefone", "fixa"),
    ("TV", "fixa"),
    ("Combustível", "variavel"),
    ("Farmácia", "variavel"),
    ("Educação", "variavel"),
    ("Livros", "variavel"),
    ("Informática", "variavel"),
    ("TZ da CAR", "outro"),
    ("Azer", "outro"),
    ("Oferta de primícia", "outro"),
    ("Cartão", "cartao"),
]

PAYMENT_DEFAULT = ["Pix", "Dinheiro", "Débito", "Crédito Mastercard", "Crédito Bradesco"]
ACCOUNTS_DEFAULT = [
    ("Mastercard", "cartao", 10),
    ("Bradesco", "cartao", 15),
    ("Pix", "outro", None),
]

st.title("🏠 Controle Financeiro Doméstico")
st.caption("Painel leve para despesas fixas, variáveis e parceladas, com visão por fatura e por mês.")

def money(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def month_start(d):
    d = pd.to_datetime(d)
    return pd.Timestamp(d.year, d.month, 1)

def month_label(d):
    return pd.to_datetime(d).strftime("%Y-%m")

def fmt_month_br(d):
    return pd.to_datetime(d).strftime("%m/%Y")

def safe_df(data):
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)

def query_table(name, order_col=None, desc=False):
    q = supabase.table(name).select("*")
    if order_col:
        q = q.order(order_col, desc=desc)
    res = q.execute()
    return safe_df(res.data)

def ensure_seed_tables():
    cats = query_table("categories")
    if cats.empty:
        supabase.table("categories").insert(
            [{"name": n, "type": t} for n, t in CATEGORIES_DEFAULT]
        ).execute()

    pays = query_table("payment_methods")
    if pays.empty:
        supabase.table("payment_methods").insert(
            [{"name": n} for n in PAYMENT_DEFAULT]
        ).execute()

    accs = query_table("accounts")
    if accs.empty:
        supabase.table("accounts").insert(
            [{"name": n, "kind": k, "due_day": d} for n, k, d in ACCOUNTS_DEFAULT]
        ).execute()

@st.cache_data(ttl=120)
def load_data():
    categories = query_table("categories", "name")
    payments = query_table("payment_methods", "name")
    accounts = query_table("accounts", "name")
    expenses = query_table("expenses", "expense_date", desc=True)
    installments = query_table("installments", "due_month", desc=True)
    return categories, payments, accounts, expenses, installments

def refresh_data():
    st.cache_data.clear()
    return load_data()

def get_id_by_name(df, name):
    if df.empty or not name or "name" not in df.columns:
        return None
    row = df[df["name"] == name]
    if row.empty:
        return None
    return row.iloc[0]["id"]

def make_installments(expense_id, total_value, total_installments, first_due_month):
    rows = []
    if total_installments <= 1:
        return rows
    installment_value = round(float(total_value) / int(total_installments), 2)
    start = pd.to_datetime(first_due_month)
    for i in range(total_installments):
        due = start + relativedelta(months=i)
        rows.append({
            "expense_id": expense_id,
            "installment_number": i + 1,
            "total_installments": int(total_installments),
            "installment_value": installment_value,
            "due_month": due.date().isoformat(),
            "paid": False,
        })
    return rows

def add_expense(payload, installment_info=None):
    ins = supabase.table("expenses").insert(payload).execute()
    if not ins.data:
        return False, "Falha ao salvar despesa."
    expense_id = ins.data[0]["id"]
    if installment_info and installment_info["total_installments"] > 1:
        rows = make_installments(
            expense_id=expense_id,
            total_value=payload["total_value"],
            total_installments=installment_info["total_installments"],
            first_due_month=installment_info["first_due_month"],
        )
        if rows:
            supabase.table("installments").insert(rows).execute()
    return True, "Salvo com sucesso."

def current_month_summary(df):
    if df.empty:
        return 0.0, 0.0, 0
    df = df.copy()
    df["expense_date"] = pd.to_datetime(df["expense_date"])
    cm = pd.Timestamp(date.today().year, date.today().month, 1)
    m = df[df["expense_date"].apply(lambda x: x.year == cm.year and x.month == cm.month)]
    total = float(m["total_value"].sum()) if not m.empty else 0.0
    count = int(len(m))
    avg = float(m["total_value"].mean()) if not m.empty else 0.0
    return total, avg, count

ensure_seed_tables()
categories_df, payments_df, accounts_df, expenses_df, installments_df = load_data()

pages = st.sidebar.radio(
    "Menu",
    ["Visão geral", "Novo lançamento", "Parceladas", "Cadastros", "Relatórios"],
)

if pages == "Visão geral":
    st.subheader("Painel geral")

    total, avg, count = current_month_summary(expenses_df)
    col1, col2, col3 = st.columns(3)
    col1.metric("Gasto no mês atual", money(total))
    col2.metric("Média por lançamento", money(avg))
    col3.metric("Lançamentos no mês", count)

    if not expenses_df.empty:
        exp = expenses_df.copy()
        exp["expense_date"] = pd.to_datetime(exp["expense_date"])
        exp["month"] = exp["expense_date"].dt.to_period("M").astype(str)

        exp_month = exp.groupby("month", as_index=False)["total_value"].sum().sort_values("month")
        fig1 = px.line(exp_month, x="month", y="total_value", markers=True, title="Gastos por mês")
        st.plotly_chart(fig1, use_container_width=True)

        st.markdown("### Principais categorias")
        if "category_id" in exp.columns and not categories_df.empty:
            exp = exp.merge(categories_df[["id", "name"]], left_on="category_id", right_on="id", how="left")
            by_cat = exp.groupby("name", as_index=False)["total_value"].sum().sort_values("total_value", ascending=False)
            fig2 = px.bar(by_cat, x="name", y="total_value", title="Gasto por categoria")
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("### Últimos lançamentos")
        show_cols = [c for c in ["expense_date", "description", "expense_type", "total_value", "notes"] if c in exp.columns]
        st.dataframe(exp[show_cols].head(10), use_container_width=True)
    else:
        st.info("Ainda não há lançamentos.")

    if not installments_df.empty:
        inst = installments_df.copy()
        inst["due_month"] = pd.to_datetime(inst["due_month"])
        inst["month"] = inst["due_month"].dt.to_period("M").astype(str)
        open_inst = inst[inst["paid"] == False]
        due_soon = open_inst[open_inst["due_month"] <= pd.Timestamp.today() + pd.DateOffset(months=2)]
        st.markdown("### Próximas parcelas")
        if not due_soon.empty:
            summary = due_soon.groupby("month", as_index=False)["installment_value"].sum().sort_values("month")
            fig3 = px.bar(summary, x="month", y="installment_value", title="Parcelas que vencem nos próximos meses")
            st.plotly_chart(fig3, use_container_width=True)
        st.dataframe(open_inst.sort_values("due_month").head(20), use_container_width=True)

elif pages == "Novo lançamento":
    st.subheader("Novo lançamento")

    with st.form("expense_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        expense_date = c1.date_input("Data da compra", value=date.today())
        expense_type = c2.selectbox("Tipo de gasto", ["Fixa", "Variavel", "Parcelada"])
        description = c3.text_input("Descrição")

        c4, c5, c6 = st.columns(3)
        category_name = c4.selectbox("Categoria", categories_df["name"].tolist() if not categories_df.empty else ["Sem cadastro"])
        payment_name = c5.selectbox("Forma de pagamento", payments_df["name"].tolist() if not payments_df.empty else ["Sem cadastro"])
        account_name = c6.selectbox("Conta / Cartão", accounts_df["name"].tolist() if not accounts_df.empty else ["Sem cadastro"])

        c7, c8 = st.columns(2)
        total_value = c7.number_input("Valor total", min_value=0.0, step=10.0, format="%.2f")
        month_to_pay = c8.date_input("Mês de pagamento da fatura / compromisso", value=date.today())

        notes = st.text_area("Observações")

        st.markdown("#### Parcelamento")
        is_installment = expense_type == "Parcelada"
        total_installments = st.number_input("Quantidade de parcelas", min_value=1, max_value=48, value=1, step=1, disabled=not is_installment)
        first_due_month = st.date_input("Primeiro mês de vencimento", value=date.today().replace(day=1), disabled=not is_installment)

        submitted = st.form_submit_button("Salvar lançamento")

    if submitted:
        if not description:
            st.error("Informe a descrição.")
        else:
            payload = {
                "expense_date": expense_date.isoformat(),
                "description": description,
                "category_id": get_id_by_name(categories_df, category_name),
                "payment_method_id": get_id_by_name(payments_df, payment_name),
                "account_id": get_id_by_name(accounts_df, account_name),
                "expense_type": expense_type,
                "total_value": float(total_value),
                "notes": notes,
                "month_to_pay": month_to_pay.isoformat(),
            }
            installment_info = {
                "total_installments": int(total_installments),
                "first_due_month": first_due_month,
            }
            ok, msg = add_expense(payload, installment_info)
            if ok:
                st.success(msg)
                refresh_data()
                st.rerun()
            else:
                st.error(msg)

elif pages == "Parceladas":
    st.subheader("Controle de parcelas")

    if installments_df.empty:
        st.info("Ainda não há parcelas.")
    else:
        inst = installments_df.copy()
        inst["due_month"] = pd.to_datetime(inst["due_month"])
        inst["month"] = inst["due_month"].dt.to_period("M").astype(str)

        open_inst = inst[inst["paid"] == False]
        summary = open_inst.groupby("month", as_index=False)["installment_value"].sum().sort_values("month")
        fig = px.bar(summary, x="month", y="installment_value", title="Total de parcelas por mês")
        st.plotly_chart(fig, use_container_width=True)

        months = sorted(open_inst["month"].unique().tolist())
        selected_month = st.selectbox("Filtrar mês", months if months else ["Sem meses"])
        filtered = open_inst[open_inst["month"] == selected_month] if months else open_inst
        st.dataframe(filtered.sort_values("due_month"), use_container_width=True)

elif pages == "Cadastros":
    st.subheader("Cadastros")
    st.write("Categorias, formas de pagamento e contas/cartões.")

    left, right = st.columns(2)
    with left:
        st.markdown("#### Nova categoria")
        new_cat = st.text_input("Nome da categoria")
        new_cat_type = st.selectbox("Tipo", ["fixa", "variavel", "parcelada", "cartao", "outro"], key="cat_type")
        if st.button("Salvar categoria"):
            if new_cat:
                supabase.table("categories").insert({"name": new_cat, "type": new_cat_type}).execute()
                refresh_data()
                st.rerun()

        st.markdown("#### Nova forma de pagamento")
        new_pay = st.text_input("Nome da forma de pagamento")
        if st.button("Salvar forma de pagamento"):
            if new_pay:
                supabase.table("payment_methods").insert({"name": new_pay}).execute()
                refresh_data()
                st.rerun()

    with right:
        st.markdown("#### Nova conta / cartão")
        new_acc = st.text_input("Nome do cartão / conta")
        due_day = st.number_input("Dia de vencimento", min_value=1, max_value=31, value=10, step=1)
        kind = st.selectbox("Tipo da conta", ["cartao", "banco", "outro"], key="acc_kind")
        if st.button("Salvar conta/cartão"):
            if new_acc:
                supabase.table("accounts").insert({"name": new_acc, "kind": kind, "due_day": int(due_day)}).execute()
                refresh_data()
                st.rerun()

    st.markdown("### Cadastros atuais")
    t1, t2, t3 = st.tabs(["Categorias", "Formas de pagamento", "Contas/cartões"])
    with t1:
        st.dataframe(categories_df, use_container_width=True)
    with t2:
        st.dataframe(payments_df, use_container_width=True)
    with t3:
        st.dataframe(accounts_df, use_container_width=True)

elif pages == "Relatórios":
    st.subheader("Relatórios e análises")

    if expenses_df.empty:
        st.info("Sem dados para relatório.")
    else:
        exp = expenses_df.copy()
        exp["expense_date"] = pd.to_datetime(exp["expense_date"])
        exp["month"] = exp["expense_date"].dt.to_period("M").astype(str)

        month_options = sorted(exp["month"].unique().tolist())
        selected = st.selectbox("Mês para análise", month_options)
        dfm = exp[exp["month"] == selected]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total do mês", money(dfm["total_value"].sum()))
        c2.metric("Quantidade", len(dfm))
        c3.metric("Ticket médio", money(dfm["total_value"].mean() if not dfm.empty else 0))

        if "category_id" in dfm.columns and not categories_df.empty:
            dfm = dfm.merge(categories_df[["id", "name"]], left_on="category_id", right_on="id", how="left")
            by_cat = dfm.groupby("name", as_index=False)["total_value"].sum().sort_values("total_value", ascending=False)
            fig = px.pie(by_cat, names="name", values="total_value", title="Distribuição por categoria")
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(dfm.sort_values("expense_date", ascending=False), use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.caption("Controle financeiro doméstico")
