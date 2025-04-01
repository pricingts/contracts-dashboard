import streamlit as st

def user_data():
    user = st.experimental_user.email
    users = {
        "pricing@tradingsol.com": {
            "name": "Shadia Jaafar",
            "tel": "+57 12345678",
            "position": "Data Analyst",
            "email": "pricing@tradingsol.com"
        },
        "sales2@tradingsol.com": {
            "name": "Sharon Zuñiga",
            "tel": "+57 (300) 510 0295",
            "position": "Business Development Manager",
            "email": "sales2@tradingsol.com"
        },
        "sales1@tradingsol.com": {
            "name": "Irina Paternina",
            "tel": "+57 (301) 3173340",
            "position": "Business Development Manager",
            "email": "sales1@tradingsol.com"
        },
        "sales3@tradingsol.com": {
            "name": "Johnny Farah",
            "tel": "+57 (301) 6671725",
            "position": "Manager of Americas",
            "email": "sales3@tradingsol.com"
        },
        "sales4@tradingsol.com": {
            "name": "Jorge Sánchez",
            "tel": "+57 (301) 7753510",
            "position": "Business Development Manager",
            "email": "sales4@tradingsol.com"
        },
        "sales@tradingsol.com": {
            "name": "Pedro Luis Bruges",
            "tel": "+57 (304) 4969358",
            "position": "Business Development Manager",
            "email": "sales@tradingsol.com"
        },
        "sales5@tradingsol.com": {
            "name": "Ivan Zuluaga",
            "tel": "+57 (300) 5734657",
            "position": "Business Development Manager",
            "email": "sales5@tradingsol.com"
        },
        "manager@tradingsol.com": { 
            "name": "Andrés Consuegra",
            "tel": "+57 (301) 7542622",
            "position": "CEO",
            "email": "manager@tradingsol.com"
        },
        "bds@tradingsol.com": {
            "name": "Stephanie Bruges",
            "tel": "+57 300 4657077",
            "position": "Business Development Specialist",
            "email": "bds@tradingsol.com"
        },
        "insidesales@tradingsol.com": {
            "name": "Catherine Silva",
            "tel": "+57 304 4969351",
            "position": "Inside Sales",
            "email": "insidesales@tradingsol.com"
        }
    }

    return users.get(user, {"name": "Desconocido", "position": "N/A", "tel": "N/A", "email": user})


def check_authentication():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        if not st.experimental_user.is_logged_in:
            st.warning("Por favor, inicia sesión primero.")
            if st.button("Log in ➡️"):
                st.login()
            st.stop()
        else:
            st.header(f"Hello, {st.experimental_user.name}!")
            st.session_state.authenticated = True

    if st.experimental_user.is_logged_in:
        col1, col2, col3 = st.columns([1, 1.55, 0.3])
        with col3:
            if st.button("Log out"):
                st.logout()
                st.session_state.authenticated = False
                st.rerun() 
    else:
        st.session_state.authenticated = False
        st.stop()

