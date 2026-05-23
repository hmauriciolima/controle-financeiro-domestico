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

st.title("Controle Financeiro Doméstico")
st.caption("Controle de despesas fixas, variáveis e parceladas com visão mensal.")

def load_expenses():
    response = supabase.table("expenses").select("*").order("expense_date", desc=True).execute()
    data = response.data or []
    return pd.DataFrame(data)

def load_installments():
    response = supabase.table("installments").select("*").execute()
    data = response.data or []
    return pd.DataFrame(data)

def load_categories():
    response = supabase.table("categories").select("*").order("name").execute()
    data = response.data or []
    return pd.DataFrame(data)

def load_payment_methods():
    response = supabase.table("payment_methods").select("*").order("name").execute()
    data = response.data or []
    return pd.DataFrame(data)

def load_accounts():
    response = supabase.table("accounts").select("*").order("name").execute()
    data = response.data or []
    return pd.DataFrame(data)

def money(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def month_label(dt):
    return pd.to_datetime(dt).strftime("%Y-%m")

page = st.sidebar.radio(
    "Menu",
    ["Visão geral", "Lançar despesa", "Despesas parceladas", "Cadastros"],
)

df_expenses = load_expenses()
df_installments = load_installments()
df_categories = load_categories()
df_payments = load_payment_methods()
df_accounts = load_accounts()

if page == "Visão geral":
    st.subheader("Painel geral")

    if not df_expenses.empty:
        df_expenses["expense_date"] = pd.to_datetime(df_expenses["expense_date"])
        df_expenses["month"] = df_expenses["expense_date"].dt.to_period("M").astype(str)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total de lançamentos", len(df_expenses))
        col2.metric("Total gasto", money(df_expenses["total_value"].sum()))
        col3.metric("Gasto médio", money(df_expenses["total_value"].mean()))

        col4, col5 = st.columns(2)

        by_category = (
            df_expenses.groupby("expense_type", as_index=False)["total_value"].sum()
            .sort_values("total_value", ascending=False)
        )
        fig1 = px.bar(by_category, x="expense_type", y="total_value", title="Gastos por tipo")
        col4.plotly_chart(fig1, use_container_width=True)

        by_month = (
            df_expenses.groupby("month", as_index=False)["total_value"].sum()
            .sort_values("month")
        )
        fig2 = px.line(by_month, x="month", y="total_value", markers=True, title="Gastos por mês")
        col5.plotly_chart(fig2, use_container_width=True)

        st.subheader("Últimos lançamentos")
        st.dataframe(df_expenses.head(10), use_container_width=True)
    else:
        st.info("Ainda não há lançamentos cadastrados.")

elif page == "Lançar despesa":
    st.subheader("Novo lançamento")

    with st.form("expense_form"):
        c1, c2, c3 = st.columns(3)

        expense_date = c1.date_input("Data", value=date.today())
        description = c2.text_input("Descrição")
        expense_type = c3.selectbox("Tipo", ["Fixa", "Variável", "Parcelada"])

        categories = df_categories["name"].tolist() if not df_categories.empty else []
        payment_methods = df_payments["name"].tolist() if not df_payments.empty else []
        accounts = df_accounts["name"].tolist() if not df_accounts.empty else []

        c4, c5, c6 = st.columns(3)
        category_name = c4.selectbox("Categoria", categories if categories else ["Sem cadastro"])
        payment_name = c5.selectbox("Forma de pagamento", payment_methods if payment_methods else ["Sem cadastro"])
        account_name = c6.selectbox("Conta / Cartão", accounts if accounts else ["Sem cadastro"])

        total_value = st.number_input("Valor total", min_value=0.0, step=10.0, format="%.2f")
        notes = st.text_area("Observações")

        submitted = st.form_submit_button("Salvar")

    if submitted:
        if not description:
            st.error("Informe a descrição.")
        else:
            category_id = None
            payment_method_id = None
            account_id = None

            if not df_categories.empty and category_name != "Sem cadastro":
                category_id = df_categories.loc[df_categories["name"] == category_name, "id"].iloc[0]

            if not df_payments.empty and payment_name != "Sem cadastro":
                payment_method_id = df_payments.loc[df_payments["name"] == payment_name, "id"].iloc[0]

            if not df_accounts.empty and account_name != "Sem cadastro":
                account_id = df_accounts.loc[df_accounts["name"] == account_name, "id"].iloc[0]

            payload = {
                "expense_date": expense_date.isoformat(),
                "description": description,
                "category_id": category_id,
                "payment_method_id": payment_method_id,
                "account_id": account_id,
                "expense_type": expense_type,
                "total_value": float(total_value),
                "notes": notes,
            }

            result = supabase.table("expenses").insert(payload).execute()
            if result.data:
                st.success("Lançamento salvo com sucesso.")
            else:
                st.error("Não foi possível salvar.")

elif page == "Despesas parceladas":
    st.subheader("Parcelas e vencimentos")

    if not df_expenses.empty and not df_installments.empty:
        df_installments["due_month"] = pd.to_datetime(df_installments["due_month"])
        df_installments["month"] = df_installments["due_month"].dt.to_period("M").astype(str)

        open_installments = df_installments[df_installments["paid"] == False].copy()
        summary = (
            open_installments.groupby("month", as_index=False)["installment_value"].sum()
            .sort_values("month")
        )

        fig = px.bar(summary, x="month", y="installment_value", title="Parcelas por mês")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(open_installments.sort_values("due_month"), use_container_width=True)
    else:
        st.info("Ainda não há parcelas cadastradas.")

elif page == "Cadastros":
    st.subheader("Cadastros auxiliares")
    st.write("Aqui você pode manter categorias, formas de pagamento e contas/cartões.")
    st.write("Esses cadastros podem ser adicionados depois com formulários simples.")