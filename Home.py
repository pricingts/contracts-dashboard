import streamlit as st
import pandas as pd
from src.services.auth import check_authentication

st.set_page_config(page_title="Contracts Management", layout="wide")

def identity_role(email):
    commercial = [
        "sales2@tradingsol.com", "sales1@tradingsol.com", "sales3@tradingsol.com",
        "sales4@tradingsol.com", "sales5@tradingsol.com"
    ]
    pricing = [
        "pricing2@tradingsol.com", "pricing8@tradingsol.com",
        "pricing6@tradingsol.com", "pricing10@tradingsol.com", "pricing11@tradingsol.com",
        "customer9@tradingsol.com",
    ]
    admin = [
        "manager@tradingsol.com", "jsanchez@tradingsol.com", "pricing2@tradingsol.com", "pricing@tradingsol.com"
    ]
    scrap_team = ["bds@tradingsol.com", "insidesales@tradingsol.com", "sales@tradingsol.com"]

    if email in commercial:
        return "commercial"
    elif email in pricing:
        return "pricing"
    elif email in admin:
        return "admin"
    elif email in scrap_team:
        return "scrap_team"
    else:
        return None

@st.dialog("Warning", width="large")
def non_identiy():
    st.write("Dear user, it appears that you do not have an assigned role on the platform. This might restrict your access to certain features. Please contact the support team to have the appropriate role assigned. Thank you!")
    st.write("pricing@tradingsol.com")

col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    st.image("resources/logo_trading.png", width=800)

check_authentication()
role = identity_role(st.experimental_user.email)

if role is None:
    non_identiy()
else:
    user = st.experimental_user.name

    if role in ["commercial", "pricing"]:
        with st.sidebar:
            page = st.radio("Go to", ["Home", "Contracts Management"])

        if page == "Contracts Management":
            import src.views.Contracts_Management as cm
            cm.show()

    if role in ["scrap_team", "admin"]:
        with st.sidebar:
            page = st.radio("Go to", ["Home", "Contracts Management", "Scrap Rates"])
        if page == "Contracts Management":
            import src.views.Contracts_Management as cm
            cm.show()
        elif page == "Scrap Rates":
            import src.views.Scrap_Rates as sr
            sr.show()