import streamlit as st
import pandas as pd
from src.services.auth import check_authentication
from collections import defaultdict

st.set_page_config(page_title="Contracts Management", layout="wide")

# def identity_role(email):
    # commercial = [
    #     "sales2@tradingsolutions.com", "sales1@tradingsolutions.com", "sales3@tradingsolutions.com",
    #     "sales4@tradingsolutions.com", "sales5@tradingsolutions.com", "sales6@tradingsolutions.com",

    #     "sales2@tradingsol.com", "sales1@tradingsol.com", "sales3@tradingsol.com",
    #     "sales4@tradingsol.com", "sales5@tradingsol.com", "sales6@tradingsol.com",
    # ]
    # pricing = [
    #     "pricing2@tradingsolutions.com", "pricing8@tradingsolutions.com", "pricing6@tradingsolutions.com", "pricing10@tradingsolutions.com", "pricing11@tradingsolutions.com", "customer9@tradingsolutions.com",
    #     "pricing2@tradingsol.com", "pricing8@tradingsol.com", "pricing6@tradingsol.com", "pricing10@tradingsol.com", "pricing11@tradingsol.com", "customer9@tradingsol.com",
    # ]
    # admin = [
    #     "manager@tradingsolutions.com", "jsanchez@tradingsolutions.com", "pricing2@tradingsolutions.com", "pricing@tradingsolutions.com", 
    #     "manager@tradingsol.com", "jsanchez@tradingsol.com", "pricing2@tradingsol.com", "pricing@tradingsol.com",
    # ]
    # scrap_team = ["bds@tradingsolutions.com", "insidesales@tradingsolutions.com", "sales@tradingsolutions.com", "pricing3@tradingsolutions.com",
    #                 "bds@tradingsol.com", "insidesales@tradingsol.com", "sales@tradingsol.com", "pricing3@tradingsol.com"]

    # if email in commercial:
    #     return "commercial"
    # elif email in pricing:
    #     return "pricing"
    # elif email in admin:
    #     return "admin"
    # elif email in scrap_team:
    #     return "scrap_team"
    # else:
    #     return None

def identity_role(email):
    role_mapping = defaultdict(list)

    roles = {
        "commercial": [
            "sales2", "sales1", "sales3", "sales4", "sales5", "sales6"
        ],
        "pricing": [
            "pricing2", "pricing8", "pricing6", "pricing10", "pricing11", "customer9"
        ],
        "admin": [
            "manager", "jsanchez", "pricing2", "pricing"
        ],
        "scrap_team": [
            "bds", "insidesales", "sales", "pricing3"
        ]
    }

    # Crear un set con todos los emails posibles para cada rol
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
    "commercial": ["Home", "Contracts Management", "New Request"],
    "pricing": ["Home", "Contracts Management"],
    "scrap_team": ["Home", "Contracts Management", "Scrap Rates", "New Request"],
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
