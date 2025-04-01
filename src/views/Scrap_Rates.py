import streamlit as st

def show():
    html_code = """
    <div style="display: flex; justify-content: center;">
        <iframe width="1100" height="900" 
            src="https://lookerstudio.google.com/embed/reporting/d6fe2354-5259-47c2-9a7c-49a27463cd1c/page/jvK2E" 
            frameborder="0" style="border:0;" allowfullscreen></iframe>
    </div>
    """
    st.markdown(html_code, unsafe_allow_html=True)