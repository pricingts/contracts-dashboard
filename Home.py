import streamlit as st
import pandas as pd
from src.services.auth import check_authentication
from collections import defaultdict

st.set_page_config(page_title="Contracts Management", layout="wide")

def identity_role(email):
    role_mapping = defaultdict(list)

    roles = {
        "commercial": [
            "sales2", "sales1", "sales3", "sales4", "sales5", "sales6", "bds", "insidesales", "sales"
        ],
        "pricing": [
            "pricing2", "pricing8", "pricing10", "pricing11", "customer9", "pricing6",
        ],
        "admin": [
            "manager", "jsanchez", "pricing2", "sjaafar", "corporate", "pricing3"
        ],
    }

    domain_variants = ["@tradingsolutions.com", "@tradingsol.com"]

    email_to_role = {}
    for role, usernames in roles.items():
        for username in usernames:
            for domain in domain_variants:
                full_email = f"{username}{domain}"
                email_to_role[full_email] = role

    return email_to_role.get(email, None)

@st.dialog("Warning", width="large")
def non_identiy():
    st.write("Dear user, it appears that you do not have an assigned role on the platform. This might restrict your access to certain features. Please contact the support team to have the appropriate role assigned. Thank you!")
    st.write("pricing@tradingsolutions.com")

col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    st.image("resources/logo_trading.png", width=800)

check_authentication()
role = identity_role(st.experimental_user.email)

if role is None:
    non_identiy()
else:
    user = st.experimental_user.name

    pages_by_role = {
    "commercial": ["Home", "Contracts Management", "New Request", "Scrap Rates"],
    "pricing": ["Home", "Contracts Management", "Scrap Rates"],
    "admin": ["Home", "Contracts Management", "Scrap Rates", "New Request"]
    }

    if role in pages_by_role:
        with st.sidebar:
            page = st.radio("Go to", pages_by_role[role])

        if page == "Contracts Management":
            import src.views.Contracts_Management as cm
            cm.show()

        elif page == "Scrap Rates":
            import src.views.Scrap_Rates as sr
            sr.show()

        elif page == "New Request":
            import src.views.New_Request as nr
            nr.show(role)
