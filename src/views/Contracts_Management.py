from google.oauth2.service_account import Credentials
import pandas as pd
import streamlit as st
import numpy as np
import pytz
import gspread
import datetime as dt

colombia_timezone = pytz.timezone('America/Bogota')
sheets_creds = Credentials.from_service_account_info(
        st.secrets["google_sheets_credentials"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
    )

client_gcp = gspread.authorize(sheets_creds)
time_sheet_id = st.secrets["general"]["time_sheet_id"]

def get_valid_value(primary, fallback):
    if pd.notna(primary) and str(primary).strip(): 
        return primary
    elif pd.notna(fallback) and str(fallback).strip():
        return fallback
    else:
        return "" 

def show():

    SPREADSHEET_ID = st.secrets["general"]["contratos_id"]
    SHEET_NAMES = ["Mejoras Q2", "TARIFAS SCRAP EXPO"]

    credentials = Credentials.from_service_account_info(
        st.secrets["contratos_credentials"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
    )

    @st.cache_data(ttl=1800)
    def load_data_from_gsheets(spreadsheet_id: str, worksheet_name: str) -> pd.DataFrame:
        gc = gspread.authorize(credentials)
        sh = gc.open_by_key(spreadsheet_id)
        worksheet = sh.worksheet(worksheet_name)
        data = worksheet.get_all_values()
        return pd.DataFrame(data[1:], columns=data[0]) if data else pd.DataFrame()

    @st.cache_data(ttl=1800)
    def get_all_data(sheet_names: list):
        return {sheet: load_data_from_gsheets(SPREADSHEET_ID, sheet) for sheet in sheet_names}

    data_frames = get_all_data(SHEET_NAMES)
    contratos_df = data_frames["Mejoras Q2"]
    #contratos_df = contratos_df[~contratos_df["Estado"].isin(["NO APROBADO", "EN PAUSA"])]

    tarifas_scrap = data_frames["TARIFAS SCRAP EXPO"]

    contratos_df["POL"] = contratos_df["POL"].astype(str)
    contratos_df["POD"] = contratos_df["POD"].astype(str)
    contratos_df["TIPO CONT"] = contratos_df["TIPO CONT"].astype(str)

    tarifas_scrap["POL"] = tarifas_scrap["POL"].astype(str)
    tarifas_scrap["POD"] = tarifas_scrap["POD"].astype(str)
    tarifas_scrap["TIPO CONT"] = tarifas_scrap["TIPO CONT"].astype(str)

    contratos_df['FECHA FIN FLETE'] = contratos_df['FECHA FIN FLETE'].str.strip() 
    contratos_df['FECHA FIN FLETE'] = pd.to_datetime(contratos_df['FECHA FIN FLETE'], format='%d/%m/%Y', errors='coerce')
    tarifas_scrap['FECHA FIN FLETE'] = pd.to_datetime(tarifas_scrap['FECHA FIN FLETE'], format='%d/%m/%Y', errors='coerce')

    common_columns = list(set(contratos_df.columns) & set(tarifas_scrap.columns))

    merged_df = pd.merge(contratos_df, tarifas_scrap, on=common_columns, how="outer")
    commodity = merged_df['COMMODITIES'].dropna().unique()

    st.header("Contracts Management")

    col1, col2 = st.columns(2)

    if "p_origen" not in st.session_state:
        st.session_state.p_origen = None
    if "p_destino" not in st.session_state:
        st.session_state.p_destino = None
    if "commodity" not in st.session_state:
        st.session_state.commodity_contracts = None
    if "tipo_cont" not in st.session_state:
        st.session_state.tipo_cont = None

    with col1:
        st.session_state.p_origen = st.selectbox("POL", merged_df["POL"].unique(), index=0)

    with col2:
        if st.session_state.p_origen:
            destinos_disponibles = merged_df[merged_df["POL"] == st.session_state.p_origen]["POD"].unique()
            st.session_state.p_destino = st.selectbox("POD", destinos_disponibles)
    
    col1, col2 = st.columns(2)

    with col1:
        if st.session_state.p_origen and st.session_state.p_destino:
            filtered_commodities = merged_df[
                (merged_df["POL"] == st.session_state.p_origen) & 
                (merged_df["POD"] == st.session_state.p_destino)
            ]["COMMODITIES"].dropna().unique()

            st.session_state.commodity_contracts = st.multiselect("Select Commodities", 
            options=filtered_commodities, 
            default=list(filtered_commodities))

    with col2:
        if st.session_state.p_origen and st.session_state.p_destino:
            filtered_cont = merged_df[
                (merged_df["POL"] == st.session_state.p_origen) & 
                (merged_df["POD"] == st.session_state.p_destino) &
                (merged_df["COMMODITIES"].isin(st.session_state.commodity_contracts))
            ]["TIPO CONT"].dropna().unique()
            st.session_state.tipo_cont = st.multiselect("Select Container Type", 
                                            options=filtered_cont, 
                                            default=list(filtered_cont))

    if st.session_state.p_origen and st.session_state.p_destino:
        p_origen = st.session_state.p_origen
        p_destino = st.session_state.p_destino
        commodity = st.session_state.commodity_contracts
        tipo_cont = st.session_state.tipo_cont

        contratos = merged_df[(merged_df["POL"] == p_origen) & (merged_df["POD"] == p_destino) & (merged_df["COMMODITIES"].isin(commodity)) & (merged_df["TIPO CONT"].isin(tipo_cont))]

        if not contratos.empty:
            hoy = dt.datetime.now()
            contratos_vigentes = contratos[pd.to_datetime(contratos["FECHA FIN FLETE"]) > hoy]

            if not contratos_vigentes.empty:
                contratos_agrupados = contratos_vigentes.groupby(["Línea", "No CONTRATO"])
                num_columns = 3

                contrato_list = list(contratos_agrupados) 
                num_contratos = len(contrato_list)

                for row_start in range(0, num_contratos, num_columns):
                    row_contracts = contrato_list[row_start:row_start + num_columns]  
                    columnas = st.columns(num_columns)

                    for idx, ((linea, contrato_id), contrato_rows) in enumerate(row_contracts):
                        with columnas[idx]:
                            with st.expander(f"🚢 **{linea} - {contrato_id.strip()}**", expanded=True):
                                contrato_info = contrato_rows.iloc[0]
                                fields = {
                                    "Shipping Line": contrato_info.get("Línea", ""),
                                    "Commodities": contrato_info.get("COMMODITIES", ""),
                                    "HS Code": contrato_info.get("HS CODES", ""),
                                    "Shipper": contrato_info.get("SHIPPER", ""),
                                    "Free Days in Origin": get_valid_value(contrato_info.get("DÍAS ORIGEN", ""), contrato_info.get("FDO", "")),
                                    "Free Days in Destination": get_valid_value(contrato_info.get("DÍAS DESTINO APROBADOS", ""), contrato_info.get("FDD", "")),
                                    "Transit Time": contrato_info.get("TT", ""),
                                    "Route": contrato_info.get("RUTA", ""),
                                    "Suitable Food": contrato_info.get("APTO ALIMENTO", ""),
                                    "Valid to": contrato_info.get("FECHA FIN FLETE", "").strftime("%Y-%m-%d") if pd.notnull(contrato_info.get("FECHA FIN FLETE", "")) else "",
                                    "Registered": contrato_info.get("Estado", ""),
                                    "Empty Pickup": contrato_info.get("EMPTY PICKUP", ""),
                                }

                                col3, col4 = st.columns(2)
                                index = 0

                                for key, value in fields.items():
                                    if key == "Suitable Food":
                                        if value == "TRUE":
                                            display_value = "Yes"
                                        else:
                                            continue 
                                    else:
                                        if pd.notna(value) and str(value).strip() and str(value) != "0": 
                                            display_value = value
                                        else:
                                            continue 

                                    if index % 2 == 0:
                                        col3.write(f"**{key}:** {display_value}")
                                    else:
                                        col4.write(f"**{key}:** {display_value}")
                                    index += 1 

                                # 🔹 Validar fecha de expiración
                                if pd.notna(contrato_info['FECHA FIN FLETE']):
                                    fecha_fin = contrato_info['FECHA FIN FLETE']
                                    dias_restantes = (fecha_fin - hoy).days
                                    if dias_restantes <= 15:
                                        st.warning(f"⚠️ **This contract expires soon: {fecha_fin.date()}**")

                                # 🔹 Generar la tabla de costos
                                columnas_clave = ["ORIGEN", "FLETE", "DESTINO", "TOTAL FLETE Y ORIGEN", "HBL", "Switch", "TOTAL FLETE, ORIGEN Y DESTINO", "TOTAL FLETE, ORIGEN Y SWITCH O HBL"]
                                contrato_rows_validos = contrato_rows.dropna(subset=columnas_clave, how="all")

                                if not contrato_rows_validos.empty:
                                    tabla_pivot = contrato_rows_validos.pivot_table(
                                        index=[],
                                        columns="TIPO CONT",
                                        values=columnas_clave,
                                        aggfunc=lambda x: x.iloc[0] if not x.empty else "Pendiente",
                                        fill_value=pd.NA
                                    )

                                    if isinstance(tabla_pivot.columns, pd.MultiIndex):
                                        available_cargo_types = tabla_pivot.columns.get_level_values(1).unique().tolist()
                                    else:
                                        available_cargo_types = tabla_pivot.columns.unique().tolist()

                                    tabla_pivot.rename_axis("CONCEPT", inplace=True)
                                    nuevo_orden =  ["ORIGEN", "FLETE", "TOTAL FLETE Y ORIGEN", "DESTINO", "HBL", "Switch", "TOTAL FLETE, ORIGEN Y DESTINO", "TOTAL FLETE, ORIGEN Y SWITCH O HBL"]
                                    tabla_pivot = tabla_pivot.reindex(nuevo_orden)
                                    tabla_pivot.index = tabla_pivot.index.map(lambda x: x.capitalize() if isinstance(x, str) else x)
                                    tabla_pivot.dropna(how="all", inplace=True)
                                    tabla_pivot = tabla_pivot.astype(str)

                                    tabla_pivot = tabla_pivot.loc[~(tabla_pivot.apply(lambda x: x.str.strip()).eq("").all(axis=1))]

                                    tabla_pivot.dropna(axis=1, how="all", inplace=True)

                                    st.table(tabla_pivot)

                                notas = contrato_info.get("NOTAS", "")

                                def capitalizar_notas(notas):
                                    lineas = notas.split("\n")
                                    lineas_transformadas = [
                                        linea.capitalize() if linea.isupper() else linea
                                        for linea in lineas
                                    ]
                                    return "\n".join(lineas_transformadas)

                                notas_formateadas = capitalizar_notas(notas).replace("\n", "  \n")  
                                st.markdown(f"**Notes:**  \n{notas_formateadas}")

                    st.write("\n")
        else:
            st.warning("⚠️ There are not active contracts")