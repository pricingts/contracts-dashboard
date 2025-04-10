import streamlit as st
from google.oauth2.service_account import Credentials
import gspread
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import csv
import pytz
from datetime import datetime
import json
import os
import pandas as pd

SERVICES_FILE = "services.json"
TEMP_DIR = "temp_uploads"

all_quotes_columns =[
    "request_id", "time", "commercial", "service", "client", "client_reference", "incoterm", "commodity", "hs_code", "transport_type", "modality", "routes_info", "ground_routes", "country_origin", "country_destination", "pickup_address", "zip_code_origin", "delivery_address", "zip_code_destination", "addresses",
    "type_container", "info_flatrack", "container_characteristics", "imo", "ground_service", "reefer_details", "additional_costs", "cargo_value", "weight", "positioning", "pickup_city", "lcl_fcl_mode",
    "info_pallets_str", "lcl_description", "stackable", "final_comments",
]

sheet_id = st.secrets["general"]["quotations_requested"]
DRIVE_ID = st.secrets["general"]["drive_id"]
time_sheet_id = st.secrets["general"]["time_sheet_id"]
PARENT_FOLDER_ID = st.secrets["general"]["parent_folder"]

sheets_creds= Credentials.from_service_account_info(
    st.secrets["google_sheets_credentials"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
)

sheets_service = build('sheets', 'v4', credentials=sheets_creds)

drive_creds = Credentials.from_service_account_info(
    st.secrets["google_drive_credentials"],
    scopes=["https://www.googleapis.com/auth/drive"]
)

drive_service = build('drive', 'v3', credentials=drive_creds)
client_gcp = gspread.authorize(sheets_creds)

def save_file_locally(file, temp_dir=TEMP_DIR):
    try:
        os.makedirs(temp_dir, exist_ok=True)

        temp_file_path = os.path.join(temp_dir, file.name)

        with open(temp_file_path, "wb") as temp_file:
            temp_file.write(file.getbuffer())  

        return temp_file_path

    except Exception as e:
        st.error(f"⚠️ Error al guardar el archivo: {e}")
        return None

@st.cache_data(ttl=3600000)
def load_csv(file):
    df = pd.read_csv(file)
    return df

def save_csv(file, new_client):
    file_exists = os.path.exists(file)
    
    with open(file, "a") as f:
        f.write(f"{new_client}\n")

def folder(request_id):
    if validate_shared_drive_folder(PARENT_FOLDER_ID):
        folder_id = create_folder(request_id, PARENT_FOLDER_ID)
        if not folder_id:
            st.error("Failed to create folder for this request.")
        else:
            folder_link = f"https://drive.google.com/drive/folders/{folder_id}"

    return folder_id, folder_link

def cargo(service):
    temp_details = st.session_state.get("temp_details", {})
    transport_type = temp_details.get("transport_type", "")

    weight = None
    commercial_invoices = st.file_uploader("Attach Commercial Invoices", accept_multiple_files=True, key="commercial_invoices")
    packing_lists = st.file_uploader("Attach Packing Lists", accept_multiple_files=True, key="packing_lists")

    ci_files = []
    if commercial_invoices:
        ci_files = [save_file_locally(file) for file in commercial_invoices]

    pl_files = []
    if packing_lists:
        pl_files = [save_file_locally(file) for file in packing_lists]

    if service != "Customs Brokerage" and transport_type != "Air":
        weight = st.number_input("Total Weight", key="weight",  value=temp_details.get("weight") or 0.0,  
                                step=0.01,  min_value=0.0)

    return {
        "commercial_invoice_files": ci_files,
        "packing_list_files": pl_files,
        "weight": weight
    }

def dimensions():
    temp_details = st.session_state.get("temp_details", {})
    transport_type = st.session_state["temp_details"].get("transport_type", None)

    if "packages" not in st.session_state:
        st.session_state.packages = []
    if "total_weight" not in st.session_state:
        st.session_state["total_weight"] = 0.0

    def add_package():
        st.session_state.packages.append({
            "type_packaging": "Pallet",
            "quantity": 0,
            "weight_lcl": 0.0,
            "length": 0.0,
            "width": 0.0,
            "height": 0.0,
            "volume": 0.0,
            "kilovolume": 0.0,
            "weight_unit": "KG",
            "length_unit": "CM",
            "total_weight": 0.0
        })

    def remove_package(index):
        if 0 <= index < len(st.session_state.packages):
            del st.session_state.packages[index]

    def copy_package(index):
        if 0 <= index < len(st.session_state.packages):
            copied_package = st.session_state.packages[index].copy()
            st.session_state.packages.append(copied_package)
        else:
            st.error("Invalid index. Cannot copy package.")

    weight_conversion = {
        "KG": 1,
        "Ton": 1000,
        "Lbs": 0.453592
    }
    
    length_conversion = {
        "CM": 1,
        "M": 100,
        "MM": 0.1,
        "Inches": 2.54
    }

    for i in range(len(st.session_state.packages)):
        st.markdown(f"**Package {i + 1}**")

        col1, col2, col3, col4 = st.columns(4)
        col5, col6, col7, col8, col9 = st.columns(5)
        col10, col11 = st.columns([0.04, 0.3])

        with col1:
            st.session_state.packages[i]["type_packaging"] = st.selectbox(
                "Packaging Type*", ["Pallet", "Box", "Bag"], 
                index=["Pallet", "Box", "Bag"].index(st.session_state.packages[i].get("type_packaging", "Pallet")),
                key=f"type_packaging_{i}"
            )

        with col2:
            st.session_state.packages[i]["quantity"] = st.number_input(
                "Quantity*", key=f"quantity_{i}", value=st.session_state.packages[i].get("quantity", 0), step=1, min_value=0)
        
        with col3:
            st.session_state.packages[i]["weight_unit"] = st.selectbox(
                "Weight Unit", ["KG", "Ton", "Lbs"],
                index=["KG", "Ton", "Lbs"].index(st.session_state.packages[i].get("weight_unit", "KG")),
                key=f"weight_unit_{i}"
            )
        with col4:
            st.session_state.packages[i]["weight_lcl"] = st.number_input(
                "Weight per Unit*", key=f"weight_lcl_{i}", 
                value=float(st.session_state.packages[i].get("weight_lcl", 0.0)), 
                step=0.01, min_value=0.0
            )

        with col5:
            st.session_state.packages[i]["length_unit"] = st.selectbox(
                "Length Unit", ["CM", "M", "MM", "Inches"],
                index=["CM", "M", "MM", "Inches"].index(st.session_state.packages[i].get("length_unit", "CM")),
                key=f"length_unit_{i}"
            )
        with col6:
            st.session_state.packages[i]["length"] = st.number_input(
                "Length", key=f"length_{i}", 
                value=float(st.session_state.packages[i].get("length", 0.0)), 
                step=0.01, min_value=0.0
            )

        with col7:
            st.session_state.packages[i]["width"] = st.number_input(
                "Width", key=f"width_{i}", 
                value=float(st.session_state.packages[i].get("width", 0.0)), 
                step=0.01, min_value=0.0
            )

        with col8:
            st.session_state.packages[i]["height"] = st.number_input(
                "Height", key=f"height_{i}", 
                value=float(st.session_state.packages[i].get("height", 0.0)), 
                step=0.01, min_value=0.0
            )

        # Conversión de valores a CM y KG
        weight_kg = st.session_state.packages[i]["weight_lcl"] * weight_conversion[st.session_state.packages[i]["weight_unit"]]
        total_weight = weight_kg * st.session_state.packages[i]["quantity"]
        st.session_state.packages[i]["total_weight"] = total_weight

        length_cm = st.session_state.packages[i]["length"] * length_conversion[st.session_state.packages[i]["length_unit"]]
        width_cm = st.session_state.packages[i]["width"] * length_conversion[st.session_state.packages[i]["length_unit"]]
        height_cm = st.session_state.packages[i]["height"] * length_conversion[st.session_state.packages[i]["length_unit"]]

        total_volume = 0
        if length_cm > 0 and width_cm > 0 and height_cm > 0:
            unit_volume = (length_cm * width_cm * height_cm) / 1000000  # Convertir a m³
            total_volume = unit_volume * st.session_state.packages[i]["quantity"]
            st.session_state.packages[i]["volume"] = total_volume

        with col9:
            if transport_type == "Air":
                calculated_kvm = total_volume * 166.6 if total_volume > 0 else 0 

                if total_volume > 0:
                    st.session_state.packages[i]["kilovolume"] = calculated_kvm
                    st.number_input(
                        "Kilovolume (KVM)*",
                        key=f"kilovolume_{i}",
                        value=calculated_kvm,
                        step=0.01,
                        min_value=0.0,
                        disabled=True
                    )

                else:
                    st.session_state.packages[i]["kilovolume"] = st.number_input(
                        "Kilovolume (KVM)*",
                        key=f"kilovolume_{i}",
                        value=st.session_state.packages[i].get("kilovolume", 0.0),
                        step=0.01,
                        min_value=0.0
                    )

            else:
                st.session_state.packages[i]["volume"] = st.number_input(
                    "Volume (CBM)*", key=f"volume_{i}", 
                    value=float(st.session_state.packages[i].get("volume", 0.0)), 
                    step=0.01, min_value=0.0
                )

        with col10:
            st.button("Copy", on_click=lambda i=i: copy_package(i), key=f"copy_{i}")
        with col11:
            st.button("Remove", on_click=lambda i=i: remove_package(i), key=f"remove_{i}")

    st.button("Add Package", on_click=add_package)

    return {"packages": st.session_state.packages}


def common_questions():
    temp_details = st.session_state.get("temp_details", {})

    if not temp_details.get("dimensions_flatrack"):
            temp_details["dimensions_flatrack"] = [{"weight": 0.0, "length": 0.0, " width": 0.0, "height": 0.0, 
                                                    "weight_unit": "KG", "length_unit": "CM"}]

    container_types = temp_details.get("type_container", ["20' Dry Standard"])
    if not isinstance(container_types, list):
        container_types = [container_types] 

    type_container = st.multiselect(
        "Type of container*",
        options=[
            "20' Dry Standard",
            "40' Dry Standard",
            "40' Dry High Cube",
            "Reefer 20'",
            "Reefer 40'",
            "Open Top 20'",
            "Open Top 40'",
            "Flat Rack 20'",
            "Flat Rack 40'",
            "Ro Ro",
            "Break Bulk"

        ],
        default=[], 
        key="type_container"
    )

    if any(tc in ["Flat Rack 20'", "Flat Rack 40'", "Ro Ro", "Break Bulk"] for tc in type_container):

        col1, col2, col3, col4, col5, col6 = st.columns(6)

        with col1:
            st.session_state.temp_details["dimensions_flatrack"][0]["weight_unit"] = st.selectbox(
                "Weight Unit", ["KG", "Ton", "Lbs"],
                index=["KG", "Ton", "Lbs"].index(st.session_state.temp_details["dimensions_flatrack"][0].get("weight_unit", "KG")),
                key="weight_unit_flatrack"
            )
        with col2:
            st.session_state.temp_details["dimensions_flatrack"][0]["weight"] = st.number_input(
                "Weight*", key="weight_0",
                value=float(st.session_state.temp_details["dimensions_flatrack"][0].get("weight", 0.0)),
                step=0.01, min_value=0.0
            )

        with col3:
            st.session_state.temp_details["dimensions_flatrack"][0]["length_unit"] = st.selectbox(
                "Length Unit", ["CM", "M", "MM", "Inches"],
                index=["CM", "M", "MM", "Inches"].index(st.session_state.temp_details["dimensions_flatrack"][0].get("length_unit", "CM")),
                key="length_unit_flatrack"
            )
        
        with col4:
            st.session_state.temp_details["dimensions_flatrack"][0]["length"] = st.number_input(
                "Length*", key="length_0",
                value=float(st.session_state.temp_details["dimensions_flatrack"][0].get("length", 0.0)),
                step=0.01, min_value=0.0
            )
        with col5:
            st.session_state.temp_details["dimensions_flatrack"][0]["width"] = st.number_input(
                "Width*", key="width_0",
                value=float(st.session_state.temp_details["dimensions_flatrack"][0].get("width", 0.0)),
                step=0.01, min_value=0.0
            )
        with col6:
            st.session_state.temp_details["dimensions_flatrack"][0]["height"] = st.number_input(
                "Height*", key="height_0",
                value=float(st.session_state.temp_details["dimensions_flatrack"][0].get("height", 0.0)),
                step=0.01, min_value=0.0
            )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        reinforced = st.checkbox("Reinforced", key="reinforced", value=temp_details.get("reinforced", False))
    with col2:
        food_grade = st.checkbox("Foodgrade", key="food_grade", value=temp_details.get("food_grade", False))
    with col3:
        isotank = st.checkbox("Isotank", key="isotank", value=temp_details.get("isotank", False))
    with col4:
        flexitank = st.checkbox("Flexitank", key="flexitank", value=temp_details.get("flexitank", False))

    msds_files_tank = []
    ts_files = []

    if isotank or flexitank:
        msds_files = temp_details.get("msds_files", "")
        if not msds_files:
            msds = st.file_uploader("Attach Safety Sheet or MSDS*", accept_multiple_files=True, key="msds_tank")
            if msds:
                msds_files_tank = [save_file_locally(file) for file in msds]

        technical_sheets = st.file_uploader("Attach Technical Sheets*", accept_multiple_files=True, key="technical_sheets")
        ts_files = []
        if technical_sheets:
            ts_files = [save_file_locally(file) for file in technical_sheets]

    positioning = st.radio(
        "Container Positioning",
        ["In yard", "At port", "Not Applicable"],
    key="positioning", index=["In yard", "At port", "Not Applicable"].index(temp_details.get("positioning", "In yard"))
    )

    pickup_city = temp_details.get("pickup_city", "")

    if positioning == "In yard":
        pickup_city = st.text_input("Pick up City*", key="pickup_city", value=pickup_city)

    lcl_fcl_mode = st.checkbox("LCL - FCL", key="lcl_fcl_mode", value=temp_details.get("lcl_fcl_mode", False))

    return {
        "type_container": type_container,
        "reinforced": reinforced,
        "food_grade": food_grade,
        "isotank": isotank,
        "flexitank": flexitank,
        "ts_files": ts_files,
        "msds_files_tank": msds_files_tank,
        "positioning": positioning,
        "pickup_city": pickup_city,
        "lcl_fcl_mode": lcl_fcl_mode,
        "dimensions_flatrack": temp_details["dimensions_flatrack"]
    }

def handle_refrigerated_cargo(reefer_containers, incoterm):
    temp_details = st.session_state.get("temp_details", {})
    reefer_cont_type, drayage_reefer = None, None
    pickup_thermo_king = None

    for cont_type in reefer_containers:
        if cont_type == "Reefer 40'":
            st.markdown(f"Details for {cont_type}")
            reefer_types = ["Controlled Atmosphere", "Cold Treatment", "Operating Reefer"]
            default_reefer_type = temp_details.get(f"reefer_type_{cont_type}", "Controlled Atmosphere")

            reefer_cont_type = st.radio(
                f"Specify the type for {cont_type}",
                reefer_types,
                index=reefer_types.index(default_reefer_type),
                key=f"reefer_cont_type_{cont_type}"
            )
    
    temperature = st.text_input("Temperature range °C", key="temperature", value=temp_details.get("temperature", ""))

    if incoterm in ["EXW", "DDP", "DAP"]:
        pickup_thermo_king = st.checkbox("Thermo King Pick up", 
                                    key="pickup_thermo_king", value=temp_details.get("pickup_thermo_king", False))

        drayage_reefer = st.checkbox("Drayage Reefer", 
                                    key="drayage_reefer", value=temp_details.get("drayage_reefer", False))
        return {
            "temperature": temperature,
            "reefer_cont_type": reefer_cont_type,
            "pickup_thermo_king": pickup_thermo_king,
            "drayage_reefer": drayage_reefer
        }

    return {
        "temperature": temperature,
        "reefer_cont_type": reefer_cont_type,
        "pickup_thermo_king": pickup_thermo_king,
    }

def insurance_questions():
    commercial_invoice = st.file_uploader("Attach Commercial Invoices", accept_multiple_files=True, key="commercial_invoices")

    ci_files = []
    if commercial_invoice:
        ci_files = [save_file_locally(file) for file in commercial_invoice]

    return {
        "commercial_invoice_files": ci_files
    }

def imo_questions():
    temp_details = st.session_state.get("temp_details", {})
    temp_details = st.session_state["temp_details"]

    imo_cargo = st.checkbox(
        "**IMO**", 
        key="imo_cargo", 
        value=temp_details.get("imo_cargo", False)
    )

    un_code = temp_details.get("un_code", "")
    imo_type = temp_details.get("imo_type", "")

    if "msds_files" not in temp_details:
        temp_details["msds_files"] = []

    msds_files = temp_details["msds_files"]

    if imo_cargo:
        col1, col2 = st.columns(2)
        with col1:
            imo_type = st.text_input("IMO type*", key="imo_type", value=imo_type)
        with col2:
            un_code = st.text_input("UN Code*", key="un_code", value=un_code)

        if not msds_files:
            msds = st.file_uploader("Attach MSDS*", accept_multiple_files=True, key="msds")

            if msds:
                new_files = []
                for file in msds:
                    file_path = save_file_locally(file)
                    if file_path:
                        new_files.append(file_path)

                msds_files.extend(new_files)
        
        st.session_state["temp_details"]["msds_files"] = msds_files

        st.session_state["temp_details"].update({
            "imo_cargo": imo_cargo,
            "imo_type": imo_type,
            "un_code": un_code,
            "msds_files": msds_files
        })

    return {
        "imo_cargo": imo_cargo,
        "imo_type": imo_type,
        "un_code": un_code,
        "msds_files": msds_files
    }

#------------------------ ROUTES MARITIME --------------------------
def initialize_routes():
    if "routes" not in st.session_state:
        st.session_state["routes"] = [{"country_origin": "", "port_origin": "", "country_destination": "", "port_destination": ""}]

def add_route():
    st.session_state["routes"].append({"country_origin": "", "port_origin": "", "country_destination": "", "port_destination": ""})

def handle_remove_route(index):
    if 0 <= index < len(st.session_state["routes"]):
        del st.session_state["routes"][index]

def copy_route(index):
    if 0 <= index < len(st.session_state["routes"]):
        route_to_copy = st.session_state["routes"][index].copy()
        st.session_state["routes"].append(route_to_copy)

def handle_routes(transport_type):
    initialize_routes()
    
    if transport_type == "Air":
        if "cities_csv" not in st.session_state or st.session_state["cities_csv"] is None:
            try:
                st.session_state["cities_csv"] = load_csv("cities_world.csv")
            except Exception as e:
                st.error(f"⚠️ Error cargando cities_world.csv: {e}")
                return
        csv_data = st.session_state["cities_csv"]
        csv_data = st.session_state.get("cities_csv", {})
        route_options = csv_data.get("Country", pd.Series()).dropna().astype(str).unique().tolist()

    elif transport_type == "Maritime":
        if "ports_csv" not in st.session_state or st.session_state["ports_csv"] is None:
            try:
                st.session_state["ports_csv"] = load_csv("output_port_world.csv")
            except Exception as e:
                st.error(f"⚠️ Error cargando output_port_world.csv: {e}")
                return
        csv_data = st.session_state["ports_csv"]
        csv_data = st.session_state.get("ports_csv", {})
        route_options = csv_data.get("country", pd.Series()).dropna().astype(str).unique().tolist()
    else:
        route_options = []

    for i in range(len(st.session_state["routes"])):
        route = st.session_state["routes"][i]
        st.markdown(f"### Route {i+1}")
        cols = st.columns([0.45, 0.45, 0.09, 0.09])

        with cols[0]: 
            col1, col2 = st.columns(2)
            with col1:
                country_origin = st.selectbox(
                    "Country of Origin*",
                    options=[""] + route_options,
                    key=f"country_origin_{i}",
                    index=(route_options.index(route["country_origin"]) + 1) if route["country_origin"] in route_options else 0,
                )
                st.session_state["routes"][i]["country_origin"] = country_origin
            
            with col2:
                filtered_ports = csv_data[csv_data["Country"] == country_origin]["City"].dropna().unique().tolist() if transport_type == "Air" and country_origin else []
                if transport_type == "Maritime" and country_origin:
                    filtered_ports = csv_data[csv_data["country"] == country_origin]["port name"].dropna().unique().tolist()
                port_origin = st.selectbox(
                    "Port of Origin*",
                    options=[""] + filtered_ports,
                    key=f"port_origin_{i}",
                    index=(filtered_ports.index(route["port_origin"]) + 1) if route["port_origin"] in filtered_ports else 0,
                )
                st.session_state["routes"][i]["port_origin"] = port_origin
        
        with cols[1]: 
            col1, col2 = st.columns(2)
            with col1:
                country_destination = st.selectbox(
                    "Country of Destination*",
                    options=[""] + route_options,
                    key=f"country_destination_{i}",
                    index=(route_options.index(route["country_destination"]) + 1) if route["country_destination"] in route_options else 0,
                )
                st.session_state["routes"][i]["country_destination"] = country_destination
            
            with col2:
                filtered_ports = csv_data[csv_data["Country"] == country_destination]["City"].dropna().unique().tolist() if transport_type == "Air" and country_destination else []
                if transport_type == "Maritime" and country_destination:
                    filtered_ports = csv_data[csv_data["country"] == country_destination]["port name"].dropna().unique().tolist()
                port_destination = st.selectbox(
                    "Port of Destination*",
                    options=[""] + filtered_ports,
                    key=f"port_destination_{i}",
                    index=(filtered_ports.index(route["port_destination"]) + 1) if route["port_destination"] in filtered_ports else 0,
                )
                st.session_state["routes"][i]["port_destination"] = port_destination
            
        with cols[2]:
            st.write("")
            st.write("")
            st.button(
                "**X**", 
                on_click=lambda i=i: handle_remove_route(i), 
                key=f"remove_route_{i}", 
                use_container_width=True
            )
        with cols[3]:
            st.write("")
            st.write("")
            st.button(
                "**Copy**",
                on_click=lambda i=i: copy_route(i), 
                key=f"copy_route_{i}", 
                use_container_width=True
            )

    st.button("➕ Add another route", on_click=add_route)

def questions_by_incoterm(incoterm, details, service, transport_type):
    routes_formatted = []
    if details is None:
        details = {}

    handle_routes(transport_type)
    routes = st.session_state.get("routes", [])
    routes_formatted = [
        {"country_origin": route["country_origin"], "port_origin":route["port_origin"],"country_destination": route["country_destination"], "port_destination":route["port_destination"]}
        for route in routes ]

    commodity = st.text_input("Commodity*", key="commodity", value=details.get("commodity", ""))

    p_imo = imo_questions()
    details.update(p_imo)      

    pickup_address = details.get("pickup_address", None)
    zip_code_origin = details.get("zip_code_origin", None)
    customs_origin = details.get("customs_origin", False)
    delivery_address = details.get("delivery_address", None)
    zip_code_destination = details.get("zip_code_destination", None)
    insurance_required = details.get("insurance_required", False)
    cargo_value = details.get("cargo_value", 0.0)
    hs_code = details.get("hs_code", None)
    customs_info = {}
    destination_cost = details.get("destination_cost", False)

    if incoterm in ["FCA", "EXW", "DDP", "DAP"]:
        hs_code_label = "HS Code*" if incoterm != "DAP" else "HS Code"
        hs_code = st.text_input(hs_code_label, key="hs_code", value=details.get("hs_code", ""))
        if incoterm in ["DDP", "EXW"]:
            pickup_address = st.text_input("Pickup Address*", key="pickup_address", value=pickup_address)
        else: 
            pickup_address = st.text_input("Pickup Address", key="pickup_address", value=pickup_address)
        zip_code_origin = st.text_input("Zip Code City of Origin", key="zip_code_origin", value=zip_code_origin)

        if incoterm == "FCA":
            st.write("Under this term, the responsibility for customs clearance at origin typically lies with the shipper. However, in certain cases, the consignee assumes this responsibility. In our quotation, we include the origin costs when applicable.")
            customs_origin = st.checkbox("Quote customs at origin", key="customs_origin", value=customs_origin)

            if customs_origin:
                customs_info = customs_questions(service, customs=True)

        if incoterm in ["EXW", "DDP", "DAP"]:
            if incoterm in ["DDP", "DAP"]:
                delivery_address = st.text_input("Delivery Address*", key="delivery_address", value=delivery_address)
            elif incoterm == "EXW":
                delivery_address = st.text_input("Delivery Address", key="delivery_address", value=delivery_address)
            zip_code_destination = st.text_input("Zip Code City of Destination", key="zip_code_destination", value=zip_code_destination)
            cargo_value = st.number_input("Cargo Value (USD)*", key="cargo_value", value=float(details.get("cargo_value", 0.0)),
                                        step=0.01, min_value=0.0)
            customs_info = customs_questions(service, customs=True)
            
            destination_cost = st.checkbox("Quote surcharges at destination", key="destination_cost", value=details.get("destination_cost", False))

    elif incoterm in ["CIF", "CFR", "CPT"]:
        hs_code = st.text_input("HS Code", key="hs_code", value=details.get("hs_code", ""))
        destination_cost = st.checkbox("Quote surcharges at destination", key="destination_cost", value=details.get("destination_cost", False))

    elif incoterm == "FOB":
        hs_code = st.text_input("HS Code", key="hs_code", value=details.get("hs_code", ""))

    insurance_required = st.checkbox("Insurance Required", key="insurance_required", value=insurance_required)
    if insurance_required:
        if incoterm not in ["EXW", "DDP", "DAP", "FCA"]:
            cargo_value = st.number_input("Cargo Value (USD)*", key="cargo_value", value=float(details.get("cargo_value", 0)),
                                        step=0.01, min_value=0.0)
            if not customs_origin:
                insurance = insurance_questions()
                details.update(insurance)

    if incoterm == "FCA" and insurance_required or customs_origin:
        cargo_value = st.number_input("Cargo Value (USD)*", key="cargo_value", value=float(details.get("cargo_value", 0.0)),
                                    step=0.01, min_value=0.0)

    details["destination_cost"] = destination_cost

    details.update({
        "incoterm": incoterm,
        "routes": routes_formatted,
        "commodity": commodity,
        "hs_code": hs_code,
        **p_imo,
        "pickup_address": pickup_address,
        "zip_code_origin": zip_code_origin,
        "delivery_address": delivery_address,
        "zip_code_destination": zip_code_destination,
        "cargo_value": cargo_value,
        **customs_info,
        "customs_origin": customs_origin,
        "insurance_required": insurance_required,
    })

    return details, routes

def initialize_ground_routes():
    if "ground_routes" not in st.session_state:
        st.session_state["ground_routes"] = [{
            "country_origin": "", "city_origin": "", "pickup_address": "", "zip_code_origin": "",
            "country_destination": "", "city_destination": "", "delivery_address": "", "zip_code_destination": ""
        }]

def add_ground_route():
    st.session_state["ground_routes"].append({
        "country_origin": "", "city_origin": "", "pickup_address": "", "zip_code_origin": "",
        "country_destination": "", "city_destination": "", "delivery_address": "", "zip_code_destination": ""
    })

def remove_ground_route(index):
    if 0 <= index < len(st.session_state["ground_routes"]):
        del st.session_state["ground_routes"][index]

def ground_transport():
    initialize_ground_routes()
    temp_details = st.session_state.get("temp_details", {})
    data = st.session_state.get("cities_csv", [])
    countries = data["Country"].dropna().unique().tolist()
    routes = [] 

    for i, route in enumerate(st.session_state["ground_routes"]):
        st.markdown(f"### Route {i+1}")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            country_origin = st.selectbox(
                f"Country of Origin*", options=[""] + countries, key=f"country_origin_{i}",
                index=(countries.index(temp_details.get("country_origin", "")) + 1)
                if temp_details.get("country_origin", "") in countries else 0,
            )

        filtered_cities = []
        if country_origin:
            filtered_cities = (data[data["Country"] == country_origin]["City"].dropna().unique().tolist())

        with col2:
            city_origin = st.selectbox(
                f"City of Origin*", options=[""] + filtered_cities, key=f"city_origin_{i}",
                index=(filtered_cities.index(temp_details.get("city_origin", "")) + 1)
                if temp_details.get("city_origin", "") in filtered_cities else 0,
            )
        with col3:
            pickup_address = st.text_input(
                f"Pickup Address*", key=f"pickup_address_{i}", value=temp_details.get("pickup_address", ""))
        with col4:
            zip_code_origin = st.text_input(
                f"Zip Code Origin*", key=f"zip_code_origin_{i}", value=temp_details.get("zip_code_origin", ""))

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            country_destination = st.selectbox(
                f"Country of Destination*", options=[""] + countries, key=f"country_destination_{i}",
                index=(countries.index(temp_details.get("country_destination", "")) + 1)
                if temp_details.get("country_destination", "") in countries else 0,
            )

        filtered_cities_destination = []
        if country_destination:
            filtered_cities_destination = (data[data["Country"] == country_destination]["City"].dropna().unique().tolist())

        with col2:
            city_destination = st.selectbox(
                f"City of Destination*", options=[""] + filtered_cities_destination, key=f"city_destination_{i}",
                index=(filtered_cities_destination.index(temp_details.get("city_destination", "")) + 1)
                if temp_details.get("city_destination", "") in filtered_cities_destination else 0,
            )

        with col3:
            delivery_address = st.text_input(
                f"Delivery Address*", key=f"delivery_address_{i}", value=temp_details.get("delivery_address", ""))
        with col4:
            zip_code_destination = st.text_input(
                f"Zip Code Destination*", key=f"zip_code_destination_{i}", value=temp_details.get("zip_code_destination", ""))

        routes.append({
            "country_origin": country_origin,
            "city_origin": city_origin,
            "pickup_address": pickup_address,
            "zip_code_origin": zip_code_origin,
            "country_destination": country_destination,
            "city_destination": city_destination,
            "delivery_address": delivery_address,
            "zip_code_destination": zip_code_destination
        })

        st.button(f"❌ Remove Route {i+1}", on_click=lambda idx=i: remove_ground_route(idx), key=f"remove_route_{i}")

    st.button("➕ Add another route", on_click=add_ground_route)

    commodity = st.text_input("Commodity*", key="commodity", value=temp_details.get("commodity", ""))
    hs_code = st.text_input("HS Code", key="hs_code", value=temp_details.get("hs_code", ""))
    imo = imo_questions()
    temp_details.update(imo)
    cargo_value = st.number_input("Cargo Value (USD)*", key="cargo_value", value=float(temp_details.get("cargo_value", 0.0)), 
                                step=0.01, min_value=0.0)
    weight = st.number_input("Total Weight*", key="weight", value=float(temp_details.get("weight", 0.0)), 
                            step=0.01, min_value=0.0)
    
    temperature, dimensions_info = None, None

    options = [
        "Drayage 20 STD", "Drayage 40 STD/40 HC", "Dryvan", "FTL 53 FT", "Flat Bed", "Box Truck",
        "Drayage Reefer 20 STD", "Drayage Reefer 40 STD", "Tractomula", "Mula Refrigerada", "LTL"
    ]
    default_value = temp_details.get("ground_service", "Drayage 20 STD")
    index = options.index(default_value) if default_value in options else 0

    ground_service = st.selectbox(
        "Select Ground Service*",
        options,
        key="ground_service",
        index=index
    )

    if ground_service in ["Mula Refrigerada", "Drayage Reefer 20 STD", "Drayage Reefer 40 STD"]:
        temperature = st.text_input(
            "Temperature range °C*", key="temperature", value=temp_details.get("temperature", ""))
        return {
            "ground_routes": routes,
            "commodity": commodity,
            "hs_code": hs_code,
            **imo,
            "cargo_value": cargo_value,
            "weight": weight,
            "ground_service": ground_service,
            "temperature": temperature
        }
    if ground_service == "LTL":
        dimensions_info = dimensions() or {}
        return {
            "ground_routes": routes,
            "commodity": commodity,
            "hs_code": hs_code,
            **imo,
            "cargo_value": cargo_value,
            "weight": weight,
            "ground_service": ground_service,
            "temperature": temperature,
            **dimensions_info
        }

    return {
        "ground_routes": routes,
        "commodity": commodity,
        "hs_code": hs_code,
        **imo,
        "cargo_value": cargo_value,
        "weight": weight,
        "ground_service": ground_service
    }


def lcl_questions(transport_type):
    temp_details = st.session_state.get("temp_details", {})
    temperature, temperature_control = None, None

    dimensions_info = dimensions()

    if transport_type == "Air":
        temperature_control = st.checkbox(
            "Temperature control required",
            key="temperature_control",
            value=temp_details.get("temperature_control", False)
        )
        if temperature_control:
            temperature = st.text_input(
                "Temperature range °C*",
                key="temperature",
                value=temp_details.get("temperature", "")
            )

    stackable = st.radio(
        "**Stackable***",
        options=["Yes", "No"],
        index=0 if temp_details.get("stackable", "") else 1,
        key="stackable"
    )

    lcl_description = st.text_area(
        "Relevant Information",
        key="lcl_description",
        value=temp_details.get("lcl_description", "")
    )

    return {
        **dimensions_info,
        "temperature_control": temperature_control,
        "temperature": temperature,
        "lcl_description": lcl_description,
        "stackable": stackable
    }

def customs_questions(service, customs=False):
    temp_details = st.session_state.get("temp_details", {})
    data = st.session_state.get("cities_csv", [])
    countries = data["Country"].dropna().unique().tolist()
    customs_data = {}
    if not customs:
        col1, col2 = st.columns(2)
        with col1:
            country_origin = st.selectbox("Country of Origin*", options=[""] + countries, key="country_origin",
                index=(countries.index(temp_details.get("country_origin", "")) + 1)
                if temp_details.get("country_origin", "") in countries else 0,
            )
        with col2:
            country_destination = st.selectbox(
            "Country of Destination", options=[""] + countries, key="country_destination",
            index=(countries.index(temp_details.get("country_destination", "")) + 1)
            if temp_details.get("country_destination", "") in countries else 0,
        )
        commodity = st.text_input("Commodity*", key="commodity", value=temp_details.get("commodity", ""))
        hs_code = st.text_input("HS Code*", key="hs_code", value=temp_details.get("hs_code", ""))
        imo = imo_questions()
        cargo_value = st.number_input("Cargo Value (USD)*", key="cargo_value", value=float(temp_details.get("cargo_value", 0)),
                                    step=0.01, min_value=0.0)

        dimensions_info = dimensions()
        customs_data.update({
            "country_origin": country_origin,
            "country_destination": country_destination,
            "commodity": commodity,
            "hs_code": hs_code,
            "cargo_value": cargo_value,
            **imo,
            **dimensions_info,
        })

    cargo_info = cargo(service)
    origin_certificates = st.file_uploader("Certificate of Origin", accept_multiple_files=True, key="origin_certificates")

    origin_certificate_files = []
    if origin_certificates:
        origin_certificate_files = [save_file_locally(file) for file in origin_certificates]

    customs_data.update({
        **cargo_info,
        "origin_certificate_files": origin_certificate_files,
    })
    return customs_data

def final_questions():

    if "final_comments" not in st.session_state:
        st.session_state.final_comments = st.session_state.get("temp_details", {}).get("final_comments", "")

    # if "volumen_num" not in st.session_state or not isinstance(st.session_state.get("volumen_num"), int):
    #     st.session_state.volumen_num = st.session_state.get("temp_details", {}).get("volumen_num", 0) or 0
    
    # if "volumen_frequency" not in st.session_state:
    #     st.session_state.volumen_frequency = st.session_state.get("temp_details", {}).get("volumen_frequency", "")
    
    # freq_op = ["Weekly", "Monthly"]

    # st.write("**Cargo Volume**")
    # col1, col2 = st.columns(2)
    # with col1:
    #     volumen_num = st.number_input(
    #         "Quantity", key="volumen_num", value=int(st.session_state.volumen_num), min_value=0, step=1
    #     ) 

    # with col2:
    #     volumen_frequency = st.selectbox(
    #         "Frequency",
    #         options=[""] + freq_op,
    #         index=([""] + freq_op).index(st.session_state.volumen_frequency) if st.session_state.volumen_frequency in freq_op else 0,
    #         key="volumen_frequency"
    #     ) 
    final_comments = st.text_area("Final Comments", key="final_comments")

    additional_documents = st.file_uploader("Attach Additional Documents", accept_multiple_files=True, key="additional_documents_files")

    additional_documents_files = []
    if additional_documents:
        additional_documents_files = [save_file_locally(file) for file in additional_documents]

    return {
        # "volumen_num": volumen_num,
        # "volumen_frequency": volumen_frequency,
        "final_comments": final_comments,
        "additional_documents_files": additional_documents_files
    }

def validate_service_details(temp_details):
    errors = []
    if not isinstance(temp_details, dict):
        errors.append("The 'temp_details' object is missing or not properly initialized.")
        return errors

    service = temp_details.get("service", "")
    modality = temp_details.get("modality", "")
    hs_code = temp_details.get("hs_code", "")
    commodity = temp_details.get("commodity")
    imo = temp_details.get("imo_cargo", False)
    transport_type = temp_details.get("transport_type", "")

    if not commodity:
        errors.append("Commodity is required.")
    if imo:
        imo_type = temp_details.get("imo_type", "")
        un_code = temp_details.get("un_code", "")
        msds_files = st.session_state["temp_details"].get("msds_files", [])
        if not msds_files:
            errors.append("MSDS is required.")
        if not imo_type:
            errors.append("IMO type is required.")
        if not un_code:
            errors.append("UN Code is required.")

    if service == "International Freight":
        insurance_required = temp_details.get("insurance_required", False)
        if insurance_required:
            cargo_value = temp_details.get("cargo_value", 0.0) or 0
            if cargo_value <= 0:
                errors.append("Cargo value is required.")

        routes = temp_details.get("routes", [])
        if not routes:
            errors.append("At least one route is required.")
        else:
            for idx, route in enumerate(routes):
                if not route.get("country_origin"):
                    errors.append(f"The origin country of route {idx + 1} is required.")
                if not route.get("port_origin"):
                    errors.append(f"The origin port of route {idx + 1} is required.")
                if not route.get("country_destination"):
                    errors.append(f"The destination country of route {idx + 1} is required.")
                if not route.get("port_destination"):
                    errors.append(f"The destination port of route {idx + 1} is required.")

        if modality == "FCL":
            type_container = temp_details.get("type_container", "")
            if not type_container:
                errors.append("Choose a container type")
            if type_container in ["Flat Rack 20'", "Flat Rack 40'"]:
                dimensions_flatrack = temp_details.get("dimensions_flatrack", [])

                if not dimensions_flatrack or not isinstance(dimensions_flatrack, list) or len(dimensions_flatrack) == 0:
                    errors.append("Flat Rack dimensions must be provided.")
                else:
                    flatrack = dimensions_flatrack[0] 

                    if flatrack.get("weight", 0.0) <= 0:
                        errors.append("Weight must be greater than 0.")
                    if flatrack.get("height", 0.0) <= 0:
                        errors.append("Height must be greater than 0.")
                    if flatrack.get("length", 0.0) <= 0:
                        errors.append("Length must be greater than 0.")
                    if flatrack.get("width", 0.0) <= 0:
                        errors.append("Width must be greater than 0.")

            positioning = temp_details.get("positioning", "")
            if positioning == "In yard":
                pickup_city = temp_details.get("pickup_city", "")
                if not pickup_city:
                    errors.append("Pick up city is required.")

            isotank = temp_details.get("isotank", False)
            flexitank = temp_details.get("flexitank", False)

            if isotank or flexitank:
                msds_files = temp_details.get("msds_files", [])
                if not msds_files:
                    msds_files_tank = temp_details.get("msds_files_tank", "")
                    if not msds_files_tank:
                        errors.append("MSDS is required.")
                ts_files = temp_details.get("ts_files", "")
                if not ts_files:
                    errors.append("Technical Sheet is required.")

        elif modality == "LCL" or transport_type == "Air":
            packages = temp_details.get("packages", [])
            if not packages:
                errors.append("At least one package is required.")
            else:
                if transport_type == "Air":
                    for idx, package in enumerate(packages):
                        if package.get("quantity", 0) <= 0:
                            errors.append(f"The quantity of package {idx + 1} must be greater than 0.")
                        if package.get("weight_lcl", 0.0) <= 0 and package.get("kilovolume", 0) <= 0:
                            errors.append(f"The weight or kilovolume of package {idx + 1} must be greater than 0.")
                        if package.get("weight_lcl", 0.0) > 0 and package.get("kilovolume", 0) > 0:
                            continue
                        if (
                            package.get("length", 0.0) <= 0 or 
                            package.get("width", 0.0) <= 0 or 
                            package.get("height", 0.0) <= 0
                        ):
                            errors.append(f"The dimensions of package {idx + 1} must be greater than 0 if weight and kilovolume are not specified.")
                else:
                    for idx, package in enumerate(packages):
                        if package.get("quantity", 0) <= 0:
                            errors.append(f"The quantity of package {idx + 1} must be greater than 0.")
                        if package.get("weight_lcl", 0.0) <= 0 and package.get("volume", 0) <= 0:
                            errors.append(f"The weight or volume of package {idx + 1} must be greater than 0.")
                        if package.get("weight_lcl", 0.0) > 0 and package.get("volume", 0) > 0:
                            continue
                        if (
                            package.get("length", 0.0) <= 0 or 
                            package.get("width", 0.0) <= 0 or 
                            package.get("height", 0.0) <= 0
                        ):
                            errors.append(f"The dimensions of package {idx + 1} must be greater than 0 if weight and volume are not specified.")

        incoterm = temp_details.get("incoterm", "")
        customs_origin = temp_details.get("customs_origin", False)
        insurance_required = temp_details.get("insurance_required", False)

        if incoterm in ["FCA", "EXW", "DDP", "DAP"]:
            hs_code = temp_details.get("hs_code", "")
            cargo_value = temp_details.get("cargo_value", 0.0) or 0

            if incoterm == "FCA" and (customs_origin or insurance_required) and cargo_value <= 0:
                errors.append("Cargo value is required.")
            elif incoterm in ["EXW", "DDP", "DAP"] and cargo_value <= 0:
                errors.append("Cargo value is required.")

            if not hs_code and incoterm != "DAP":
                errors.append("HS Code is required.")

            if incoterm in ["EXW", "DDP"]:
                pickup_address = temp_details.get("pickup_address", "")
                if not pickup_address:
                    errors.append("Pick up Address is required.")

            if incoterm in ["DDP", "DAP"]: 
                delivery_address = temp_details.get("delivery_address", "")
                if not delivery_address:
                    errors.append("Delivery address is required.")

    elif service == "Ground Transportation":
        cargo_value = temp_details.get("cargo_value", 0.0)
        weight = temp_details.get("weight", 0.0)

        routes = temp_details.get("ground_routes", [])
        if not routes:
            errors.append("At least one route is required.")
        else:
            for idx, route in enumerate(routes):
                if not route.get("country_origin"):
                    errors.append(f"The country of origin of the route {idx + 1} is required.")
                if not route.get("city_origin"):
                    errors.append(f"The city of origin of the route {idx + 1} is required.")
                if not route.get("pickup_address"):
                    errors.append(f"The pickup address of origin of the route {idx + 1} is required.")
                if not route.get("zip_code_origin"):
                    errors.append(f"The zip code of origin of the route {idx + 1} is required.")

                if not route.get("country_destination"):
                    errors.append(f"The country of destination of the route {idx + 1} is required.")
                if not route.get("city_destination"):
                    errors.append(f"The city of destination of the route {idx + 1} is required.")
                if not route.get("delivery_address"):
                    errors.append(f"The delivery address of the route {idx + 1} is required.")
                if not route.get("zip_code_destination"):
                    errors.append(f"The zip code of destination of the route {idx + 1} is required.")

        if cargo_value <= 0.0:
            errors.append("Cargo value is required.")
        if weight <= 0.0:
            errors.append("Weight is required.")


    elif service == "Customs Brokerage":
        country_origin = temp_details.get("country_origin", [])
        country_destination = temp_details.get("country_destination", [])
        hs_code = temp_details.get("hs_code", "")
        cargo_value = temp_details.get("cargo_value", 0.0)

        if not country_origin:
            errors.append("Origin Country is required.")
        if not country_destination:
            errors.append("Destination Country is required.")
        if not hs_code:
            errors.append("HS Code is required.")
        if cargo_value <= 0:
            errors.append("Cargo Value is required.")

    return errors


def handle_add_service():
    prefill_temp_details()
    temp_details = st.session_state.get("temp_details", {})

    if not temp_details:
        st.error("No se encontraron detalles del servicio. Por favor, completa la información.")
        return

    service = temp_details.get("service")
    if not service or service == "-- Services --":
        st.error("Selecciona un servicio válido antes de continuar.")
        return

    services = st.session_state.get("services", [])
    edit_index = st.session_state.get("edit_index")

    temp_details = clean_service_data(temp_details)

    validation_errors = validate_service_details(temp_details)
    if validation_errors:
        for error in validation_errors:
            st.error(error)
        return

    if edit_index is not None and 0 <= edit_index < len(services):
        st.session_state["services"][edit_index] = {
            "service": service,
            "details": temp_details
        }
        st.success("Servicio succesfully edited.")
        del st.session_state["edit_index"]
    else:
        st.session_state["services"].append({
            "service": service,
            "details": temp_details
        })
        st.success("Service succesfully added.")

    save_services(st.session_state["services"])
    st.session_state["temp_details"] = {}
    change_page("requested_services")

def change_page(new_page):
    st.session_state["page"] = new_page

def save_to_google_sheets(dataframe, sheet_id, max_attempts=5):
    has_pickup = dataframe["pickup_address"].notna() & (dataframe["pickup_address"].astype(str).str.strip() != "")
    has_delivery = dataframe["delivery_address"].notna() & (dataframe["delivery_address"].astype(str).str.strip() != "")

    if has_pickup.any() or has_delivery.any():
        has_routes_info = dataframe["routes_info"].notna() & (dataframe["routes_info"].astype(str).str.strip() != "")
        pattern = r"(?i)(colombia|united states)"
        routes_matches = dataframe["routes_info"].astype(str).str.contains(pattern, na=False, regex=True)
        contains_routes_match = (has_routes_info & routes_matches).any()
    else:
        contains_routes_match = False

    temp_service = dataframe["service"].astype(str).str.replace("\n", ", ")
    is_ground = temp_service.str.contains(r"\bGround Transportation\b", na=False, regex=True)
    contains_ground = is_ground.any()

    attempts = 0
    while attempts < max_attempts:
        try:
            if contains_routes_match:
                save_data_to_google_sheets(dataframe, sheet_id, "Ground Quotations") #cambiar a Ground Quotations
                save_data_to_google_sheets(dataframe, sheet_id, "All Quotes")  # CAMBIAR A All Quotes si es necesario
            elif contains_ground:
                save_data_to_google_sheets(dataframe, sheet_id, "Ground Quotations") #cambiar a Ground Quotations
                if temp_service.str.contains(",").any():
                    save_data_to_google_sheets(dataframe, sheet_id, "All Quotes")  # CAMBIAR A All Quotes si es necesario
            else:
                save_data_to_google_sheets(dataframe, sheet_id, "All Quotes")  # CAMBIAR A All Quotes si es necesario
            return 

        except Exception as e:
            attempts += 1
            st.error(f"Intento {attempts}/{max_attempts}: Error al guardar en Google Sheets: {e}")
            if attempts == max_attempts:
                st.error("Se alcanzó el máximo de intentos. No se pudo guardar la cotización.")
                raise e

def save_data_to_google_sheets(dataframe, sheet_id, sheet_name, max_attempts=5):
    attempts = 0
    while attempts < max_attempts:
        try:
            sheet = client_gcp.open_by_key(sheet_id)

            try:
                worksheet = sheet.worksheet(sheet_name)
                if worksheet.row_count == 0:
                    worksheet.append_row([col.upper() for col in dataframe.columns])

            except gspread.exceptions.WorksheetNotFound:
                worksheet = sheet.add_worksheet(title=sheet_name, rows="10000", cols="50")
                worksheet.append_row([col.upper() for col in dataframe.columns])

            dataframe.columns = dataframe.columns.str.upper()
            new_data = dataframe.fillna("").values.tolist()
            worksheet.append_rows(new_data, table_range="A2")

            return

        except Exception as e:
            attempts += 1
            st.error(f"Intento {attempts}/{max_attempts}: Error al guardar en Google Sheets ({sheet_name}): {e}")
            if attempts == max_attempts:
                st.error(f"Se alcanzó el máximo de intentos. No se pudo guardar la cotización en {sheet_name}.")
                raise e

def validate_shared_drive_folder(parent_folder_id):
    try:
        folder = drive_service.files().get(
            fileId=parent_folder_id,
            fields='id',
            supportsAllDrives=True
        ).execute()
        return folder is not None
    except Exception as e:
        st.error(f"Parent folder not found or inaccessible: {e}")
        return False

def get_folder_id(folder_name, parent_folder_id):
    try:
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and '{parent_folder_id}' in parents and trashed = false"
        response = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            supportsAllDrives=True
        ).execute()
        files = response.get('files', [])
        if files:
            return files[0]['id']
        return None
    except Exception as e:
        st.error(f"Failed to search for folder: {e}")
        return None

def create_folder(folder_name, parent_folder_id):
    existing_folder_id = get_folder_id(folder_name, parent_folder_id)
    if existing_folder_id:
        st.info(f"Folder '{folder_name}' already exists with ID: {existing_folder_id}")
        return existing_folder_id

    try:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder_id]
        }
        folder = drive_service.files().create(
            body=file_metadata,
            fields='id',
            supportsAllDrives=True
        ).execute()
        
        folder_id = folder.get('id')

        return folder_id
    
    except Exception as e:
        st.error(f"Failed to create folder: {e}")
        return None, None

def log_time(start_time, end_time, duration, request_id, quotation_type):
    sheet_name = "Duration Time Quotation" #Cambiar a Duration Time Quotation
    try:
        sheet = client_gcp.open_by_key(time_sheet_id)
        try:
            worksheet = sheet.worksheet(sheet_name)
            start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
            end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
            worksheet.append_row([request_id, quotation_type, start_time_str, end_time_str, duration])
        
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
            worksheet.append_row(["request_id", "quotation_type", "Start Time", "End Time", "Duration (seconds)"])
            start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
            end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
            worksheet.append_row([request_id, quotation_type, start_time_str, end_time_str, duration])

    except Exception as e:
        st.error(f"Failed to save data to Google Sheets: {e}")

def load_services():
    if os.path.exists(SERVICES_FILE):
        with open(SERVICES_FILE, "r") as file:
            return json.load(file)
    return []

def save_services(services):
    with open(SERVICES_FILE, "w") as file:
        json.dump(services, file, indent=4)

def reset_json():
    if os.path.exists(SERVICES_FILE):
        os.remove(SERVICES_FILE)
    with open(SERVICES_FILE, "w") as file:
        json.dump([], file)

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

def handle_file_uploads(file_uploader_key, label="Attach Files*", temp_dir=TEMP_DIR):
    os.makedirs(temp_dir, exist_ok=True)

    if file_uploader_key not in st.session_state:
        st.session_state[file_uploader_key] = {}

    uploaded_files = st.file_uploader(label, accept_multiple_files=True, key=file_uploader_key)

    if uploaded_files:
        for uploaded_file in uploaded_files:
            if uploaded_file.name not in st.session_state[file_uploader_key]:
                file_path = save_file_locally(uploaded_file, temp_dir=temp_dir)
                if file_path:
                    st.session_state[file_uploader_key][uploaded_file.name] = file_path

    current_uploaded_files = set(
        [file.name for file in uploaded_files] if uploaded_files else []
    )
    session_uploaded_files = set(st.session_state[file_uploader_key].keys())

    files_to_remove = session_uploaded_files - current_uploaded_files
    for file_name in files_to_remove:
        file_path = st.session_state[file_uploader_key].pop(file_name, None)
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

    return list(st.session_state[file_uploader_key].values())

def upload_all_files_to_google_drive(folder_id, drive_service):
    try:
        file_list = drive_service.files().list(q=f"'{folder_id}' in parents", fields="files(name)").execute()
        existing_files = {file['name'] for file in file_list.get('files', [])}

        for root, _, files in os.walk(TEMP_DIR):
            for file_name in files:
                file_path = os.path.join(root, file_name)
                
                if file_name not in existing_files: 
                    with open(file_path, "rb") as file:
                        file_metadata = {'name': file_name, 'parents': [folder_id]}
                        media = MediaFileUpload(file_path, resumable=True)

                        drive_service.files().create(
                            body=file_metadata,
                            media_body=media,
                            fields='id',
                            supportsAllDrives=True
                        ).execute()

                        #st.success(f"Uploaded file: {file_name}")

                    try:
                        os.remove(file_path)
                    except Exception as e:
                        st.error(f"Error al eliminar {file_name}: {e}")

                else:
                    st.warning(f"El archivo {file_name} ya existe en Google Drive. No se subirá de nuevo.")

    except Exception as e:
        st.error(f"Error al subir archivos a Google Drive: {e}")

def load_existing_ids_from_sheets():
    sheet_name = "Duration Time Quotation" 
    while True: 
        try:
            sheet = client_gcp.open_by_key(time_sheet_id)

            worksheet_list = [ws.title for ws in sheet.worksheets()]
            if sheet_name not in worksheet_list:
                return set()

            worksheet = sheet.worksheet(sheet_name)
            existing_ids = worksheet.col_values(1)
            return set(existing_ids[1:]) 

        except gspread.exceptions.SpreadsheetNotFound:
            st.error("The spreadsheet with the provided ID was not found. Retrying...")

        except gspread.exceptions.WorksheetNotFound:
            st.error(f"The worksheet '{sheet_name}' was not found in the spreadsheet. Retrying...")

        except Exception as e:
            st.error(f"Error while loading IDs from Google Sheets: {e}. Retrying...")

@st.cache_data(ttl=3600)
def load_clients():
    sheet_name = "clientes"
    
    try:
        sheet = client_gcp.open_by_key(time_sheet_id)
        worksheet_list = [ws.title for ws in sheet.worksheets()]
        
        if sheet_name not in worksheet_list:
            return []

        worksheet = sheet.worksheet(sheet_name)
        clientes = worksheet.col_values(1)

        return clientes[1:]

    except gspread.exceptions.SpreadsheetNotFound:
        st.error("No se encontró la hoja de cálculo con el ID proporcionado.")
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"No se encontró la pestaña '{sheet_name}' en la hoja de cálculo.")
    except Exception as e:
        st.error(f"Error al cargar los clientes desde Google Sheets: {e}")
    
    return []

def go_back():
    navigation_flow = [
        "select_sales_rep",
        "client_name",
        "add_services",
        "client_data",
        "requested_services"
    ]
    current_page = st.session_state.get("page", "select_sales_rep")
    if current_page in navigation_flow:
        current_index = navigation_flow.index(current_page)
        if current_index > 0: 
            st.session_state["page"] = navigation_flow[current_index - 1]

def load_shared_values_from_services():
    services = load_services()
    shared_values = {}

    priority_fields = ["country_origin", "country_destination"]
    field_values = {field: None for field in priority_fields}

    for service in services:
        details = service.get("details", {})

        if service["service"] == "International Freight" and "routes" in details:
            routes = details["routes"]
            if routes and len(routes) > 0:
                if not field_values["country_origin"]:
                    field_values["country_origin"] = routes[0].get("country_origin", "")
                if not field_values["country_destination"]:
                    field_values["country_destination"] = routes[0].get("country_destination", "")

        if service["service"] in ["Ground Transportation", "Customs Brokerage"]:
            for field in priority_fields:
                if field_values[field] is None and details.get(field) not in [None, ""]:
                    field_values[field] = details[field]

        for key, value in details.items():
            if key in shared_values and shared_values[key] != value:
                continue
            shared_values[key] = value

    for field, value in field_values.items():
        if value is not None:
            shared_values[field] = value

    return shared_values

def prefill_temp_details():
    shared_values = load_shared_values_from_services()
    temp_details = st.session_state.get("temp_details", {})

    for key, value in shared_values.items():
        if key not in temp_details or not temp_details[key]:  
            temp_details[key] = value

    services = load_services()
    for service in services:
        details = service.get("details", {})

        if service["service"] == "International Freight" and "routes" in details:
            routes = details["routes"]
            if routes and len(routes) > 0:
                freight_country_origin = routes[0].get("country_origin", "")
                freight_country_destination = routes[0].get("country_destination", "")

                if not temp_details.get("country_origin"):
                    temp_details["country_origin"] = freight_country_origin
                if not temp_details.get("country_destination"):
                    temp_details["country_destination"] = freight_country_destination
        if not temp_details.get("cargo_value"):
            temp_details["cargo_value"] = details.get("cargo_value", 0)

    st.session_state["temp_details"] = temp_details


def clean_service_data(service_data):
    service_type = service_data.get("service", "")
    modality = service_data.get("modality", "")
    transport_type = service_data.get("transport_type", "")

    common_keys = [
        "commodity", "hs_code", "cargo_value", "final_comments", "additional_documents_files", "service", "volumen_num", "volumen_frequency"
    ]

    freight_common__keys = [
        "routes", "transport_type", "modality", "incoterm",
        "imo_cargo", "imo_type", "un_code", "msds_files", "ts_files",
        "msds_files_tank", "temperature", "customs_origin",
        "insurance_required", "pickup_address", "zip_code_origin", "delivery_address",
        "zip_code_destination", "commercial_invoice_files", "packing_list_files", "origin_certificate_files", "weight",
        "destination_cost"
    ]

    fcl_keys = [
        "type_container", "reinforced", "food_grade", "dimensions_flatrack", "isotank", "flexitank", "positioning", "pickup_city",
        "lcl_fcl_mode", "reefer_cont_type", "pickup_thermo_king", "drayage_reefer", 
    ]

    lcl_keys = [
        "packages", "lcl_description", "stackable", "temperature_control"
    ]

    ground_keys = [
        "ground_routes", "imo_cargo", "imo_type", "un_code", "weight", "ground_service", "temperature", "lcl_description", "stackable", "packages"
    ]

    customs_keys = [
        "packages", "country_origin", "country_destination", "imo_cargo", "imo_type", "un_code", "msds_files",
        "commercial_invoice_files", "packing_list_files", "origin_certificate_files"
    ]

    if service_type == "International Freight":
        allowed_keys = common_keys + freight_common__keys
        if transport_type == "Maritime":
            if modality == "FCL":
                allowed_keys += fcl_keys
            elif modality == "LCL":
                allowed_keys += lcl_keys
        elif transport_type == "Air":
            allowed_keys = [key for key in allowed_keys if key != "modality"]
            allowed_keys += lcl_keys
    elif service_type == "Customs Brokerage":
        allowed_keys = common_keys + customs_keys
    elif service_type == "Ground Transportation":
        allowed_keys = common_keys + ground_keys
    else:
        allowed_keys = common_keys 

    return {key: value for key, value in service_data.items() if key in allowed_keys}

def get_name(user):
    user_mapping = {
        "pricing": "Shadia Jaafar",
        "sales2": "Sharon Zuñiga",
        "sales1": "Irina Paternina",
        "sales3": "Johnny Farah", 
        "sales4": "Jorge Sánchez",
        "sales": "Pedro Luis Bruges",
        "sales5": "Ivan Zuluaga", 
        "sales6": "Felipe Hoyos",
        "manager": "Andrés Consuegra",
        "bds": "Stephanie Bruges",
        "insidesales": "Catherine Silva"
    }

    username = user.split("@")[0]
    return user_mapping.get(username, None)

