import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import streamlit as st
import numpy as np
from src.services.cotizacion import *
from src.services.utils import load_existing_ids_from_sheets, log_time
import pytz
from datetime import datetime
import datetime as dt
from src.services.utils import load_clients
from src.common.google_sheets import (
    open_spreadsheet,
    get_or_create_worksheet,
    load_all_records,
)
from src.common.config import SHEETS

tz = pytz.timezone('America/Bogota')

if "client" not in st.session_state:
    st.session_state["client"] = None

if "clients_list" not in st.session_state:
    st.session_state["clients_list"] = []

def get_valid_value(primary, fallback):
    if pd.notna(primary) and str(primary).strip(): 
        return primary
    elif pd.notna(fallback) and str(fallback).strip():
        return fallback
    else:
        return "" 

def parse_price(value):
    if isinstance(value, str) and value.strip().upper() == "INCLUIDO":
        return "INCLUIDO"
    try:
        return float(value.replace('$', '').replace('.', '').replace(',', '.'))
    except ValueError:
        return value 

def validate_inputs(client, cargo_types, incoterm, cargo_value, selected_surcharges, surcharge_values):
    errors = []

    if not client.strip():
        errors.append("⚠️ Please enter a client name.")

    if not cargo_types:
        errors.append("⚠️ Please select at least one container.")

    if incoterm == "CIF" and cargo_value == 0:
        errors.append("⚠️ Cargo value must be greater than 0.")

    if not selected_surcharges:
        errors.append("⚠️ Please select at least one surcharge.")

    has_invalid_sales = any(sale == 0 for surcharge in surcharge_values for sale in surcharge_values[surcharge].values())
    if has_invalid_sales:
        errors.append("❌ Sales values must be greater than 0.")

    return errors

def generate_request_id():
    if "generated_ids" not in st.session_state:
        st.session_state["generated_ids"] = set()

    existing_ids = load_existing_ids_from_sheets()
    new_sequence_ids = [
        int(id[1:]) for id in existing_ids 
        if id.startswith('Q') and id[1:].isdigit()
    ]

    if new_sequence_ids:
        next_id = max(new_sequence_ids) + 1
    else:
        next_id = 1 

    unique_id = f"Q{next_id:04d}"

    st.session_state["generated_ids"].add(unique_id)
    return unique_id


def save_to_google_sheets(data, start_time):
    
    ss = open_spreadsheet("costs_sales_contracts")
    headers = [
        "REQUEST_ID","COMMERCIAL","TIME","CLIENT","CUSTOMER_NAME","INCOTERM",
        "VALIDITY","POL","POD","COMMODITY","CONTRATO_ID",
        "CARGO_TYPES","CARGO_VALUE","SURCHARGES (COSTOS)","SURCHARGES (VENTAS)",
        "ADDITIONAL_SURCHARGES (Costos)","ADDITIONAL_SURCHARGES (Ventas)",
        "TOTAL_COST","TOTAL_SALE","TOTAL_PROFIT"
    ]
    ws = get_or_create_worksheet(ss, "CONTRATOS", headers=headers)

    total_cost = total_sale = 0
    costs, sales = [], []
    for surcharge, details in data["surcharges"].items():
        for cont, vals in details.items():
            c, s = vals['cost'], vals['sale']
            costs.append(f"{surcharge} {cont}: ${c:.2f}")
            sales.append(f"{surcharge} {cont}: ${s:.2f}")
            total_cost += c; total_sale += s
    additional_costs, additional_sales = [], []
    for add in data.get("additional_surcharges", []):
        c, s = add['cost'], add['sale']
        additional_costs.append(f"{add['concept']}: ${c:.2f}")
        additional_sales.append(f"{add['concept']}: ${s:.2f}")
        total_cost += c; total_sale += s

    end_time = datetime.now(pytz.utc).astimezone(tz)
    end_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
    if not start_time:
        st.error("Error: 'start_time' no definido.")
        return
    duration = (end_time - start_time).total_seconds()

    row = [
        data['request_id'], data['commercial'], end_str,
        data['client'], data['customer_name'], data['incoterm'], data['validity'],
        data['pol'], data['pod'], data['commodity'], data['contract_id'],
        "\n".join(data['cargo_types']), data['cargo_value'],
        "\n".join(costs), "\n".join(sales),
        "\n".join(additional_costs), "\n".join(additional_sales),
        f"${total_cost:.2f}", f"${total_sale:.2f}", f"${data['total_profit']:.2f}"
    ]
    ws.append_row(row)
    log_time(start_time, end_time, duration, data['request_id'], quotation_type="Contracts")

incoterm_op = ['CIF', 'CFR', 'FOB', 'CPT', 'DAP']

@st.dialog("Generate Quotation", width="large")
def select_options(role, contrato_id, available_cargo_types, tabla_pivot):
    if role in ["commercial", "admin"]:

        if "clients_list" not in st.session_state or not st.session_state["clients_list"]:
            try:
                client_data = load_clients()
                st.session_state["clients_list"] = client_data if client_data else []
            except Exception as e:
                st.error(f"Error al cargar la lista de clientes: {e}")
                st.session_state["clients_list"] = []

        if st.session_state.get("start_time") is None:
            st.session_state["start_time"] = datetime.now(tz)

        start_time = st.session_state["start_time"]

        col1, col2 = st.columns(2)

        with col1:
            incoterm = st.selectbox('Select Incoterm', incoterm_op, key=f'incoterm_{contrato_id}')
        with col2:
            validity = st.date_input('Quotation Validity', value="today", format="YYYY/MM/DD", key=f'validity_{contrato_id}')

        clients_list = st.session_state.get("clients_list", [])

        col1, col2 = st.columns(2)
        with col1:
            client = st.selectbox("Who is your client?*", [" "] + ["+ Add New"] + clients_list, key=f'client_{contrato_id}')

            new_client_saved = st.session_state.get("new_client_saved", False)

            if client == "+ Add New":
                st.write("### Add a New Client")
                new_client_name = st.text_input("Enter the client's name:", key=f"new_client_name_{contrato_id}")

                if st.button("Save Client"):
                    if new_client_name:
                        if new_client_name not in st.session_state["clients_list"]:
                            st.session_state["client"] = new_client_name
                            st.session_state["new_client_saved"] = True
                            client = new_client_name
                            st.success(f"✅ Client '{new_client_name}' saved!")
                        else:
                            st.warning(f"⚠️ Client '{new_client_name}' already exists in the list.")
                    else:
                        st.error("⚠️ Please enter a valid client name.")
            else:
                st.session_state["client"] = client
        
        with col2:
            customer_name = st.text_input("Enter the customer name:", key=f"customer_name_{contrato_id}")

        cargo_types = st.multiselect('Select Cargo Type', available_cargo_types, key=f'cargo_{contrato_id}')

        cargo_value = 0.0
        insurance_cost = 0.0
        insurance_sale = 0.0
        total_profit = 0

        if incoterm == "CIF":
            cargo_value = st.number_input(f'Enter Cargo Value', min_value=0.0, step=0.01, key=f'cargo_value_{contrato_id}')
            insurance_cost = round(cargo_value * (0.13/100) * 1.04, 2)
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Cost of Insurance**")
                st.write(f'${insurance_cost}')
            with col2:
                insurance_sale = st.number_input(f'Sale of Insurance', min_value=0.0, step=0.01, key=f'insurance_{contrato_id}')

            insurance_profit = insurance_sale - insurance_cost
            total_profit += insurance_profit

        if not cargo_types:
            st.warning('Please select a container to continue')
            return

        available_surcharges = [s for s in tabla_pivot.index if s in ["Origin", "Freight", "Destination", "Hbl", "Switch"]]
        selected_surcharges = st.multiselect('Select Surcharges', available_surcharges, key=f'surcharges_{contrato_id}')
        tabla_pivot = tabla_pivot.map(parse_price)

        surcharge_values = {surcharge: {} for surcharge in selected_surcharges}

        cols = st.columns(len(cargo_types) * 2)
        for idx, cont in enumerate(cargo_types):
            with cols[idx * 2]:
                st.write(f"### {cont}")

        for surcharge in selected_surcharges:
            cols = st.columns(len(cargo_types) * 2) 

            for idx, cont in enumerate(cargo_types):
                with cols[idx * 2]:
                    if surcharge in tabla_pivot.index and cont in tabla_pivot.columns:
                        cost_value = tabla_pivot.at[surcharge, cont]
                        try:
                            if isinstance(cost_value, str) and cost_value.upper() == "INCLUIDO":
                                cost_display = "INCLUIDO"
                                cost_value = 0.0
                            else:
                                cost_value = float(cost_value)
                                cost_display = f"${cost_value:.2f}"
                        except (KeyError, ValueError):
                            cost_display = "Not Available"
                            cost_value = 0.0
                    else:
                        cost_display = "Not Available"
                        cost_value = 0.0

                    st.write(f'**Cost of {surcharge}**')
                    st.write(cost_display)

                with cols[idx * 2 + 1]: 
                    sale = round(
                        st.number_input(
                            f'Sale of {surcharge}',
                            min_value=0.0,
                            step=0.01,
                            format="%.2f",
                            key=f'value_{surcharge}_{cont}_{contrato_id}'
                        ),
                        2
                    )
                    surcharge_values[surcharge][cont] = sale

                profit = sale - cost_value
                total_profit += profit

                surcharge_values[surcharge][cont] = {
                    "cost": cost_value,
                    "sale": sale
                }

        st.write("### Add Additional Surcharges")
        if "additional_surcharges" not in st.session_state:
            st.session_state["additional_surcharges"] = []

        if st.button("Add Surcharge"):
            st.session_state["additional_surcharges"].append({"concept": "", "cost": 0.0, "sale": 0.0})

        def remove_surcharge(index):
            if 0 <= index < len(st.session_state["additional_surcharges"]):
                del st.session_state["additional_surcharges"][index]

        to_remove = []
        for i, surcharge in enumerate(st.session_state["additional_surcharges"]):
            col1, col2, col3, col4 = st.columns([2.5, 1, 1, 0.5])
            with col1:
                surcharge["concept"] = st.text_input(f"Concept", surcharge["concept"], key=f'concept_{i}_{contrato_id}')
            with col2:
                surcharge["cost"] = st.number_input(f"Cost", min_value=0.0, step=0.01, key=f'cost_{i}_{contrato_id}')
            with col3:
                surcharge["sale"] = round(
                    st.number_input(
                        "Sale",
                        min_value=0.0,
                        step=0.01,
                        format="%.2f",
                        key=f'sale_{i}_{contrato_id}'
                    ),
                    2
                )
            with col4:
                st.write(" ")
                st.write(" ")
                st.button("❌", key=f'remove_{i}', on_click=remove_surcharge, args=(i,)) 

            total_profit += surcharge["sale"] - surcharge["cost"]
        
        for i in sorted(to_remove, reverse=True):
            del st.session_state["additional_surcharges"][i]
        
        default_notes = st.session_state["selected_data"].get("Notes", "")
        edited_notes = st.text_area("**Notes**", value=default_notes, height=150)
        
        st.write(f'**Total Profit: ${total_profit:.2f}**')

        if st.button("Generate Quotation"):
            errors = validate_inputs(client, cargo_types, incoterm, cargo_value, selected_surcharges, surcharge_values)

            if errors:
                for error in errors:
                    st.error(error)
                return

            if not st.session_state.get("request_id"): 
                st.session_state["request_id"] = generate_request_id()

            quotation_data = {
                "request_id": st.session_state.get("request_id"),
                "client": st.session_state.get("client", client),
                "customer_name": customer_name,
                "incoterm": incoterm,
                "validity": validity.strftime("%d/%m/%Y"),
                "cargo_types": cargo_types,
                "cargo_value": cargo_value,
                "insurance_sale": insurance_sale,
                "surcharges": surcharge_values,
                "additional_surcharges": st.session_state["additional_surcharges"],
                "total_profit": total_profit,
                "pol": st.session_state["selected_data"].get("POL", ""),
                "pod": st.session_state["selected_data"].get("POD", ""),
                "commodity": st.session_state["selected_data"].get("Details", {}).get("Commodities", ""),
                "commercial": st.session_state["selected_data"].get("Commercial", ""),
                "contract_id": contrato_id,
                "Details": st.session_state["selected_data"].get("Details", {}),
                "Notes": edited_notes
            }
            #st.write(quotation_data)

            save_to_google_sheets(quotation_data, start_time)

            st.success("Information succesfully saved!")

            client_normalized = st.session_state.get("client", client).strip().lower() if client else ""

            client_norm = st.session_state.get("client"," ").strip().lower()
            if client_norm and all(c.lower()!=client_norm for c in st.session_state["clients_list"]):
                ss_time = open_spreadsheet("time_sheet_id")
                ws_cl = get_or_create_worksheet(ss_time, "clientes")
                ws_cl.append_row([client_norm])
                st.session_state["clients_list"].append(client_norm)
                st.session_state["client"] = None
                load_clients.clear()
                st.rerun()

            pdf_filename = generate_quotation(quotation_data)

            with open(pdf_filename, "rb") as f:
                pdf_bytes = f.read()

            st.download_button(
                label="Download Quotation",
                data=pdf_bytes,
                file_name="quotation.pdf",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.write('You cannot to download quotations. Please contact the support team')
        st.write('sjaafar@tradingsolutions.com')

def show(role):
    key, sheet = SHEETS["mejoras_q2"]
    df1 = load_all_records(key, sheet)

    key, sheet = SHEETS["tarifas_scrap_expo"]
    df2 = load_all_records(key, sheet)

    for df in (df1, df2):
        df.columns = df.columns.str.strip()
    contratos_df = df1.copy()
    tarifas_scrap = df2.copy()

    contratos_df["POL"] = contratos_df["POL"].astype(str)
    contratos_df["POD"] = contratos_df["POD"].astype(str)
    tarifas_scrap["POL"] = tarifas_scrap["POL"].astype(str)
    tarifas_scrap["POD"] = tarifas_scrap["POD"].astype(str)

    contratos_df['FECHA FIN FLETE'] = contratos_df['FECHA FIN FLETE'].str.strip() 
    contratos_df['FECHA FIN FLETE'] = pd.to_datetime(contratos_df['FECHA FIN FLETE'], format='%d/%m/%Y', errors='coerce')
    tarifas_scrap['FECHA FIN FLETE'] = pd.to_datetime(tarifas_scrap['FECHA FIN FLETE'], format='%d/%m/%Y', errors='coerce')

    common_columns = list(set(contratos_df.columns) & set(tarifas_scrap.columns))

    merged_df = pd.merge(contratos_df, tarifas_scrap, on=common_columns, how="outer")
    commodity = merged_df['COMMODITIES'].dropna().unique()

    st.header("Contracts Management")

    col1, col2 = st.columns(2)

    if "p_origen"   not in st.session_state: st.session_state.p_origen = None
    if "p_destino"  not in st.session_state: st.session_state.p_destino = None
    if "commodity_contracts" not in st.session_state: st.session_state.commodity_contracts = []
    if "tipo_cont"  not in st.session_state: st.session_state.tipo_cont = []

    with col1:
            opciones_origen = merged_df["POL"].unique().tolist()
            opciones_origen.insert(0, "") 
            st.selectbox(
                "**Port of Origin**",
                opciones_origen,
                index=0,
                key="p_origen"
            )

    with col2:
        if st.session_state.get("p_origen"):
            opciones_destino = merged_df[merged_df["POL"] == st.session_state.p_origen]["POD"].unique().tolist()
            opciones_destino.insert(0, "") 

            st.selectbox(
                "**Port of Destination**",
                opciones_destino,
                index=0,
                key="p_destino"
            )

    col1, col2 = st.columns(2)

    with col1:
        if st.session_state.get("p_origen") and st.session_state.get("p_destino"):
            filtered_commodities = merged_df[
                (merged_df["POL"] == st.session_state.p_origen) & 
                (merged_df["POD"] == st.session_state.p_destino)
            ]["COMMODITIES"].dropna().unique()

            st.session_state.commodity_contracts = st.multiselect("**Select Commodities**", 
            options=filtered_commodities, 
            default=list(filtered_commodities))
    with col2:
        if st.session_state.get("p_origen") and st.session_state.get("p_destino"):
            filtered_cont = merged_df[
                (merged_df["POL"] == st.session_state.p_origen) & 
                (merged_df["POD"] == st.session_state.p_destino) &
                (merged_df["COMMODITIES"].isin(st.session_state.commodity_contracts))
            ]["TIPO CONT"].dropna().unique()
            st.session_state.tipo_cont = st.multiselect("**Select Container Type**", 
                                            options=filtered_cont, 
                                            default=list(filtered_cont))

    if st.session_state.get("p_origen") and st.session_state.get("p_destino"):
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
                            with st.expander(f"🚢 **{linea} - {str(contrato_id).strip()}**", expanded=True):
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

                                traducciones = {
                                    "ORIGEN": "ORIGIN",
                                    "FLETE": "FREIGHT",
                                    "DESTINO": "DESTINATION",
                                    "TOTAL FLETE Y ORIGEN": "TOTAL FREIGHT AND ORIGIN",
                                    "HBL": "HBL",
                                    "Switch": "SWITCH",
                                    "TOTAL FLETE, ORIGEN Y DESTINO": "TOTAL FREIGHT, ORIGIN AND DESTINATION",
                                    "TOTAL FLETE, ORIGEN Y SWITCH O HBL": "TOTAL FREIGHT, ORIGIN AND SWITCH OR HBL"
                                }

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
                                    tabla_pivot.index = tabla_pivot.index.map(lambda x: traducciones.get(x, x))
                                    tabla_pivot.index = tabla_pivot.index.map(lambda x: x.capitalize() if isinstance(x, str) else x)
                                    tabla_pivot.dropna(how="all", inplace=True)
                                    tabla_pivot = tabla_pivot.astype(str)

                                    tabla_pivot = tabla_pivot.loc[
                                            ~(tabla_pivot
                                            .apply(lambda x: x.astype(str).str.strip())
                                            .eq("")
                                            .all(axis=1))
                                        ]

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

                                if st.button('Select', key=f"select_{linea}_{contrato_id}"):
                                    st.session_state["selected_contract"] = contrato_id
                                    st.session_state["selected_data"] = {
                                        "Commercial": st.experimental_user.name,
                                        "POL": p_origen,
                                        "POD": p_destino,
                                        "Contract ID": contrato_id,
                                        "Details": fields,
                                        "Notes": notas_formateadas
                                    }
                                    select_options(role, contrato_id, available_cargo_types, tabla_pivot)

                    st.write("\n")
            else:
                st.warning("⚠️ There are not active contracts")
        else:
            st.warning("⚠️ There are not active contracts")
