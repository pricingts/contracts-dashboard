import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread
from src.services.utils import *
from googleapiclient.discovery import build
import pytz
from datetime import datetime
import random
import string
import os

def show(role):

    sheet_id = st.secrets["general"]["quotations_requested"]
    DRIVE_ID = st.secrets["general"]["drive_id"]
    PARENT_FOLDER_ID = st.secrets["general"]["parent_folder"]
    time_sheet_id = st.secrets["general"]["time_sheet_id"]

    sheets_creds = Credentials.from_service_account_info(
        st.secrets["google_sheets_credentials"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
    )

    sheets_service = build('sheets', 'v4', credentials=sheets_creds)

    drive_creds = Credentials.from_service_account_info(
        st.secrets["google_drive_credentials"],
        scopes=["https://www.googleapis.com/auth/drive"]
    )

    drive_service = build('drive', 'v3', credentials=drive_creds)

    client_gcp = gspread.authorize(sheets_creds)
    colombia_timezone = pytz.timezone('America/Bogota')

    #--------------------------------------UTILITY FUNCTIONS--------------------------------
    @st.cache_data(ttl=3600)
    def clear_temp_directory():
        for root, _, files in os.walk(TEMP_DIR):
            for file_name in files:
                os.remove(os.path.join(root, file_name))

    def initialize_state():
        default_values = {
            "page": "client_name",
            "sales_rep": None,
            "services": [],
            "client": None,
            "client_reference": None,
            "completed": True,
            "start_time": None,
            "end_time": None,
            "uploaded_files": {},
            "temp_details": {"routes": [], "packages": [], "dimensions_flatrack": [], "ground_routes": []},
            "generated_ids": set(),
            "request_id": None,
            "final_comments": "",
            "volume_num": "",
            "volume_frequency": "",
            "initialized": True,
            "ports_csv": None,
            "cities_csv": None,
            "clients_list": []
        }
        for key, value in default_values.items():
            if key not in st.session_state:
                st.session_state[key] = value

        st.session_state["request_id"] = None

        reset_json()
        clear_temp_directory()

        if "ports_csv" not in st.session_state or st.session_state["ports_csv"] is None:
            try:
                st.session_state["ports_csv"] = load_csv("resources/data/output_port_world.csv")
            except Exception as e:
                st.error("Error loading CSV data. Please check the file path or format.")

        if "cities_csv" not in st.session_state or st.session_state["cities_csv"] is None:
            try:
                st.session_state["cities_csv"] = load_csv("resources/data/cities_world.csv")
            except Exception as e:
                st.error("Error loading CSV data. Please check the file path or format.")

        if "clients_list" not in st.session_state or not st.session_state["clients_list"]:
            try:
                client_data = load_clients()
                st.session_state["clients_list"] = client_data if client_data else []
            except Exception as e:
                st.error(f"Error al cargar la lista de clientes: {e}")
                st.session_state["clients_list"] = []

        if "uploaded_files" not in st.session_state:
            st.session_state.uploaded_files = []
        
        if "submitted" not in st.session_state:
            st.session_state["submitted"] = False

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

    #------------------------------------APP----------------------------------------
    col1, col2, col3 = st.columns([1, 2, 1])

    if "initialized" not in st.session_state or not st.session_state["initialized"]:
        initialize_state()

    if st.session_state["completed"]:
        if st.session_state.get("start_time") is None:
            st.session_state["start_time"] = datetime.now(colombia_timezone)

        start_time = st.session_state["start_time"]

        email = st.experimental_user.email
        name = get_name(email)
        st.write(name)

        st.session_state["sales_rep"] = name

        if st.session_state["page"] == "client_name":

            sales_rep = st.session_state.get("sales_rep", "-- Sales Representative --")
            #st.subheader(f"Hello, {sales_rep}!")

            if "clients_list" not in st.session_state or not st.session_state["clients_list"]:
                try:
                    clients_list = load_clients() 
                    st.session_state["clients_list"] = clients_list if clients_list else []
                except Exception as e:
                    st.error(f"⚠️ Error cargando la lista de clientes desde Google Sheets: {e}")
                    st.session_state["clients_list"] = []


            clients_list = st.session_state.get("clients_list", [])

            client = st.selectbox("Who is your client?*", [" "] + ["+ Add New"] + clients_list, key="client_input")
            reference = st.text_input("Client reference", key="reference")

            new_client_saved = st.session_state.get("new_client_saved", False)

            if client == "+ Add New":
                st.write("### Add a New Client")
                new_client_name = st.text_input("Enter the client's name:", key="new_client_name")

                if st.button("Save Client"):
                    if new_client_name:
                        if new_client_name not in st.session_state["clients_list"]:
                            st.session_state["client"] = new_client_name
                            st.session_state["new_client_saved"] = True
                            st.success(f"✅ Client '{new_client_name}' saved!")
                        else:
                            st.warning(f"⚠️ Client '{new_client_name}' already exists in the list.")
                    else:
                        st.error("⚠️ Please enter a valid client name.")

            def handle_next_client():
                selected_client = st.session_state.get("client_input", "").strip()

                if selected_client == "+ Add New":
                    if not st.session_state.get("new_client_saved", False):
                        st.warning("Please save the new client before proceeding.")
                        return
                    if not new_client_name.strip():
                        st.warning("Please enter a valid client name before proceeding.")
                        return
                    st.session_state["client"] = new_client_name

                elif selected_client and selected_client != " ":
                    st.session_state["client"] = selected_client 

                if "client" in st.session_state and st.session_state["client"]:
                    st.session_state["client_reference"] = reference
                    st.session_state["page"] = "add_services"
                else:
                    st.warning("Please enter or select a valid client before proceeding.")

            col1, col2 = st.columns([0.04, 0.3])
            with col1:
                st.button("Back", on_click=go_back, key="back_client_name") 
            with col2:
                st.button("Next", on_click=handle_next_client)

        elif st.session_state["page"] == "add_services":

            service = st.selectbox(
                        "What service would you like to quote?*",
                        ["-- Services --", "International Freight", "Ground Transportation", "Customs Brokerage"],
                        key="service"
            )

            def handle_next():
                if service == "-- Services --":
                    st.warning("Please select a valid service before proceeding.")
                else:
                    st.session_state["temp_details"]["service"] = service
                    change_page("client_data")

            col1, col2 = st.columns([0.04, 0.3])
            with col1:
                st.button("Back", on_click=go_back, key="back_choose_service") 
            with col2:
                st.button("Next", on_click=handle_next)
        
        elif st.session_state["page"] == "client_data":

            service = st.session_state["temp_details"].get("service", None)

            prefill_temp_details()
            temp_details = st.session_state["temp_details"]
        #------------------------------------INTERNATIONAL FREIGHT----------------------------
            if service == "International Freight":
                st.subheader("International Freight")

                transport_type = st.selectbox("Transport Type*", ["Maritime", "Air"], key="transport_type")
                st.session_state["temp_details"]["transport_type"] = transport_type

                if transport_type == "Air":
                    modality_options = []
                else:
                    modality_options = ["FCL", "LCL"]

                modality = st.selectbox("Modality*", modality_options, key="modality_op")
                st.session_state["temp_details"]["modality"] = modality

                if "cargo_details_expander" not in st.session_state:
                    st.session_state["cargo_details_expander"] = True
                if "transportation_details_expander" not in st.session_state:
                    st.session_state["transportation_details_expander"] = True
                if "final_details_expander" not in st.session_state:
                    st.session_state["final_details_expander"] = True

                with st.expander("**Cargo Details**", expanded=st.session_state["cargo_details_expander"]):

                    incoterms_list = ["FOB", "FCA", "CIF", "CFR", "EXW", "DDP", "DAP", "CPT"]
                    incoterm = st.selectbox("Select Incoterm*", incoterms_list, key="incoterm")

                    if incoterm:
                        incoterm_result = questions_by_incoterm(incoterm, st.session_state["temp_details"], service, transport_type)

                        if isinstance(incoterm_result, tuple):
                            incoterm_details, routes = incoterm_result
                        else:
                            incoterm_details, routes = incoterm_result, []

                        if isinstance(incoterm_details, dict):
                            st.session_state["temp_details"].update(incoterm_details)

                        if routes:
                            st.session_state["routes"] = routes

                with st.expander("**Transportation Details**", expanded=st.session_state["transportation_details_expander"]):
                    if modality == "FCL":
                        common_details = common_questions()
                        st.session_state["temp_details"].update(common_details)

                        reefer_containers = [ct for ct in common_details.get("type_container", []) if ct in ["Reefer 40'", "Reefer 20'"]]
                        if reefer_containers:
                            st.markdown("**-----Refrigerated Cargo Details-----**")
                            refrigerated_cargo = handle_refrigerated_cargo(reefer_containers, incoterm)
                            st.session_state["temp_details"].update(refrigerated_cargo)
                    if modality == "LCL" or transport_type == "Air":
                        lcl_details = lcl_questions(transport_type)
                        st.session_state["temp_details"].update(lcl_details)

                with st.expander("**Final Details**", expanded=st.session_state["final_details_expander"]):
                    final_details = final_questions()
                    st.session_state["temp_details"].update(final_details)
                
                col1, col2 = st.columns([0.04, 0.3])
                with col1:
                    st.button("Back", on_click=go_back, key="back_service") 
                with col2:
                    st.button("Add Service", key="add_service", on_click=handle_add_service)

        #-----------------------------------------GROUND TRANSPORTATION-----------------------------------------
            elif service == "Ground Transportation": 
                st.subheader("Ground Transportation")

                if "cargo_details_expander" not in st.session_state:
                    st.session_state["cargo_details_expander"] = True
                if "final_details_expander" not in st.session_state:
                    st.session_state["final_details_expander"] = True

                with st.expander("**Cargo Details**", expanded=st.session_state["cargo_details_expander"]):
                    lcl_details = ground_transport()
                    st.session_state["temp_details"].update(lcl_details)
                
                temp_details = st.session_state.get("temp_details", {})
                with st.expander("**Final Details**", expanded=st.session_state["final_details_expander"]):
                    final_details = final_questions()
                    st.session_state["temp_details"].update(final_details)

                col1, col2 = st.columns([0.04, 0.3])
                with col1:
                    st.button("Back", on_click=go_back, key="back_service") 
                with col2:
                    st.button("Add Service", key="add_service", on_click=handle_add_service)

            elif service == "Customs Brokerage":
                st.subheader("Customs Brokerage")

                if "customs_details_expander" not in st.session_state:
                    st.session_state["customs_details_expander"] = True
                if "final_details_expander" not in st.session_state:
                    st.session_state["final_details_expander"] = True

                with st.expander("**Customs Details**", expanded=st.session_state["customs_details_expander"]):
                    customs_details = customs_questions(service)
                    st.session_state["temp_details"].update(customs_details)
                
                temp_details = st.session_state.get("temp_details", {})
                with st.expander("**Final Details**", expanded=st.session_state["final_details_expander"]):
                    final_details = final_questions()
                    st.session_state["temp_details"].update(final_details)

                col1, col2 = st.columns([0.04, 0.3])
                with col1:
                    st.button("Back", on_click=go_back, key="back_service") 
                with col2:
                    st.button("Add Service", key="add_service", on_click=handle_add_service)

        elif st.session_state["page"] == "requested_services":

            if st.session_state["services"]:
                st.subheader("Requested Services")
                services = st.session_state["services"]

                def handle_edit(service_index):
                    st.session_state["edit_index"] = service_index
                    service = services[service_index]
                    st.session_state["temp_details"] = service["details"].copy()
                    st.session_state["temp_details"]["service"] = service["service"]
                    #save_services(updated_services)
                    change_page("client_data")

                def handle_delete(service_index):
                    removed_service = st.session_state["services"].pop(service_index)
                    services_json = load_services()

                    updated_services = [
                        s for s in services_json
                        if s["details"] != removed_service["details"] or s["service"] != removed_service["service"]
                    ]
                    save_services(updated_services)
                    st.success(f"Service {service_index + 1} has been removed!")
                    if not st.session_state["services"]:
                        change_page("client_name")

                def button(service):
                    if service:
                        handle_edit(i)

                for i, service in enumerate(services):
                    col1, col2, col3 = st.columns([0.8, 0.1, 0.1]) 
                    service_name = service.get("service", "Unknown Service")

                    with col1:
                        st.write(f"{i + 1}. {service_name}")
                    with col2:
                        st.button(
                            f"✏️",
                            key=f"edit_{i}",
                            on_click=lambda index=i: handle_edit(index)
                        )
                    with col3:
                        st.button(
                            f"🗑️",
                            key=f"delete_{i}",
                            on_click=lambda index=i: handle_delete(index) 
                        )

                col1, col2 = st.columns([0.04, 0.1])

                with col1:
                    def handle_another_service():
                        change_page("add_services")
                    st.button("Add Another Service", on_click=handle_another_service)

                with col2:
                    with col2:
                        if "df_all_quotes" not in st.session_state:
                            st.session_state["df_all_quotes"] = pd.DataFrame()

                        if st.session_state.get("quotation_completed", False):
                            st.session_state.clear()
                            change_page("select_sales_rep")
                            st.stop()

                        def handle_finalize_quotation():
                            if st.session_state.get("submitted", False):
                                st.warning("This quotation has already been submitted.")
                                return
                            
                            if not st.session_state.get("request_id"): 
                                st.session_state["request_id"] = generate_request_id()

                            request_id = st.session_state["request_id"]

                            services = load_services()
                            if services:
                                try:
                                    if "folder_request_id" not in st.session_state:
                                        st.session_state["folder_request_id"] = None

                                    if "folder_id" not in st.session_state or st.session_state["folder_request_id"] != request_id:
                                        if st.session_state["folder_request_id"] is None:
                                            folder_id, folder_link = folder(request_id)
                                            st.session_state["folder_id"] = folder_id
                                            st.session_state["folder_link"] = folder_link
                                            st.session_state["folder_request_id"] = request_id

                                            st.session_state["end_time"] = datetime.now(colombia_timezone)
                                            end_time = st.session_state.get("end_time", None)
                                            if end_time is not None:
                                                end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
                                            else:
                                                st.error("Error: 'end_time' no fue asignado correctamente.")
                                                return

                                            # ✅ Asegurar que 'start_time' existe antes de calcular la duración
                                            start_time = st.session_state.get("start_time", None)
                                            if start_time and end_time:
                                                duration = (end_time - start_time).total_seconds()
                                            else:
                                                st.error("Error: 'start_time' o 'end_time' no están definidos. No se puede calcular la duración.")
                                                return

                                            log_time(st.session_state["start_time"], end_time, duration, st.session_state["request_id"], quotation_type="Requested Quotation")
                                            st.session_state["submitted"] = True
                                        else:
                                            folder_id = st.session_state["folder_id"]
                                            folder_link = st.session_state["folder_link"]

                                    folder_id = st.session_state.get("folder_id", "No folder created")

                                    if not folder_id:
                                        st.error("Failed to create or retrieve folder. Aborting finalization.")
                                        return

                                    commercial = st.session_state.get("sales_rep", "Unknown")
                                    client = st.session_state["client"]
                                    client_reference = st.session_state.get("client_reference", "N/A")
                                    folder_link = st.session_state.get("folder_link", "N/A")

                                    if client and client not in st.session_state["clients_list"]:
                                        sheet = client_gcp.open_by_key(time_sheet_id)
                                        worksheet = sheet.worksheet("clientes")
                                        worksheet.append_row([client])
                                        st.session_state["clients_list"].append(client)
                                        st.success(f"✅ Client '{client}' successfully saved")
                                        load_clients.clear()

                                    grouped_record = {
                                        "time": end_time_str,
                                        "request_id": f'=HYPERLINK("{folder_link}"; "{st.session_state["request_id"]}")',
                                        "commercial": commercial,
                                        "client": client,
                                        "client_reference": client_reference,
                                        "service": set(),
                                        "routes_info": set(),
                                        "type_container": set(),
                                        "container_characteristics": set(),
                                        "imo": set(),
                                        "info_flatrack": set(),
                                        "info_pallets_str": set(),
                                        "reefer_details": [],
                                        "additional_costs": [],
                                        "ground_routes": [],     
                                        "addresses_ground": [],   
                                        "country_origin": "",
                                        "country_destination": "",
                                        "pickup_address": "",
                                        "delivery_address": "",
                                        "zip_code_origin": "",
                                        "zip_code_destination": ""
                                    }

                                    all_details = {}

                                    for service in services:
                                        details = service["details"]
                                        grouped_record["service"].add(service["service"]) 

                                        if "type_container" in details:
                                            if isinstance(details["type_container"], list):
                                                grouped_record["type_container"].update(details["type_container"])
                                            else:
                                                grouped_record["type_container"].add(details["type_container"]) 

                                        # **1️⃣ Características del Contenedor**
                                        characteristics = []
                                        if details.get("reinforced", False):
                                            characteristics.append("Reinforced")
                                        if details.get("food_grade", False):
                                            characteristics.append("Food Grade")
                                        if details.get("isotank", False):
                                            characteristics.append("Isotank")
                                        if details.get("flexitank", False):
                                            characteristics.append("Flexitank")
                                        
                                        if characteristics:
                                            grouped_record["container_characteristics"].add("\n".join(characteristics))

                                        # **2️⃣ Información IMO**
                                        imo_info = "Sí, IMO Type: {imo_type}, UN Code: {un_code}".format(
                                            imo_type=details.get("imo_type", "N/A"),
                                            un_code=details.get("un_code", "N/A")
                                        ) if details.get("imo_cargo", False) else "No"
                                        grouped_record["imo"].add(imo_info)

                                        # **3️⃣ Información de Rutas**
                                        if "routes" in details:
                                            routes = details["routes"]
                                            if len(routes) == 1:
                                                grouped_record["country_origin"] = routes[0]["country_origin"]
                                                grouped_record["country_destination"] = routes[0]["country_destination"]
                                                grouped_record["routes_info"].add(f"Route 1: {routes[0]['country_origin']} ({routes[0]['port_origin']}) → {routes[0]['country_destination']} ({routes[0]['port_destination']})")
                                            else:
                                                for i, r in enumerate(routes):
                                                    grouped_record["routes_info"].add(
                                                        f"Route {i + 1}: {r['country_origin']} ({r['port_origin']}) → {r['country_destination']} ({r['port_destination']})"
                                                    )

                                        # **4️⃣ Información de Paquetes**
                                        if "packages" in details:
                                            pallets_info = details.get("packages", [])
                                            transport_type = details.get("transport_type", "") 

                                            unique_pallets = set()
                                            total_weight_all = 0 

                                            for i, p in enumerate(pallets_info):
                                                weight_unit = p.get("weight_unit", "KG") 
                                                length_unit = p.get("length_unit", "CM")
                                                total_weight_all += p.get("total_weight", 0)

                                                if transport_type == "Air":
                                                    volume_value = p.get("kilovolume", 0)
                                                    volume_label = "KVM"
                                                else:
                                                    volume_value = p.get("volume", 0)
                                                    volume_label = "CBM"

                                                pallet_str = (
                                                    f"{p['quantity']} {p['type_packaging']},  "
                                                    f"Unit Weight: {p['weight_lcl']:.2f} {weight_unit}, Total Weight: {p['total_weight']:.2f} KG,"
                                                    f"Volume: {volume_value:.2f} {volume_label}, "
                                                    f"Dimensions: {p['length']:.2f} {length_unit} x {p['width']:.2f} {length_unit} x {p['height']:.2f} {length_unit}"
                                                )
                                                unique_pallets.add(pallet_str)

                                            if unique_pallets:
                                                grouped_record["info_pallets_str"].add("\n".join(sorted(unique_pallets)))

                                            grouped_record["info_pallets_str"].add(f"Total weight of all packages: {total_weight_all:.2f} KG")

                                        # **5️⃣ Información de Flatrack**
                                        if "dimensions_flatrack" in details:
                                            flatrack_info = details.get("dimensions_flatrack", [])
                                            if any(any(v > 0 for v in f.values() if isinstance(v, (int, float))) for f in flatrack_info):
                                                flatrack_str = "\n".join(
                                                    f"Weight: {f['weight']:.2f} {f.get('weight_unit', 'KG')}, "
                                                    f"Dimensions: {f['length']:.2f} {f.get('length_unit', 'CM')} x "
                                                    f"{f['width']:.2f} {f.get('length_unit', 'CM')} x {f['height']:.2f} {f.get('length_unit', 'CM')}"
                                                    for f in flatrack_info
                                                )
                                                grouped_record["info_flatrack"].add(flatrack_str)
                                            else:
                                                grouped_record["info_flatrack"].add("")
                                        
                                        if service.get("service", "").strip().lower() == "international freight":
                                            grouped_record["pickup_address"] = details.get("pickup_address", "N/A")
                                            grouped_record["delivery_address"] = details.get("delivery_address", "N/A")
                                            grouped_record["zip_code_origin"] = details.get("zip_code_origin", "N/A")
                                            grouped_record["zip_code_destination"] = details.get("zip_code_destination", "N/A")

                                        # ** GROUND ROUTES ***
                                        if service.get("service", "").strip().lower() == "ground transportation":
                                            ground_routes = details.get("ground_routes", [])

                                            if ground_routes:
                                                ground_routes_list = []
                                                addresses_list = []

                                                first_route = ground_routes[0] if ground_routes else {}

                                                grouped_record["country_origin"] = first_route.get("country_origin", "").strip()
                                                grouped_record["country_destination"] = first_route.get("country_destination", "").strip()

                                                for idx, route in enumerate(ground_routes, start=1):
                                                    country_origin = route.get("country_origin", "").strip()
                                                    city_origin = route.get("city_origin", "").strip()
                                                    pickup_address = route.get("pickup_address", "").strip()
                                                    zip_code_origin = route.get("zip_code_origin", "").strip()
                                                    country_destination = route.get("country_destination", "").strip()
                                                    city_destination = route.get("city_destination", "").strip()
                                                    delivery_address = route.get("delivery_address", "").strip()
                                                    zip_code_destination = route.get("zip_code_destination", "").strip()

                                                    if city_origin and country_origin and city_destination and country_destination:
                                                        ground_routes_list.append(f"Route {idx}: {city_origin} ({country_origin}) → {city_destination} ({country_destination})")

                                                    if pickup_address and zip_code_origin and delivery_address and zip_code_destination:
                                                        addresses_list.append(f"Address {idx}: {pickup_address} ({zip_code_origin}) → {delivery_address} ({zip_code_destination})")

                                                grouped_record["ground_routes"] = str("\n".join(ground_routes_list)) if ground_routes_list else ""
                                                grouped_record["addresses"] = "\n".join(addresses_list) if addresses_list else ""

                                            else:
                                                grouped_record["ground_routes"] = ""
                                                grouped_record["addresses"] = ""
                                                grouped_record["country_origin"] = ""
                                                grouped_record["country_destination"] = ""
                                        else:
                                            grouped_record["ground_routes"] = ""
                                            grouped_record["addresses"] = ""

                                        # **6️⃣ Reefer Details (Freight & Ground Refrigerado)**
                                        reefer_containers = ["Reefer 20'", "Reefer 40'"]
                                        reefer_ground_services = ["Mula Refrigerada", "Drayage Reefer 20 STD", "Drayage Reefer 40 STD"]
                                        reefer_details = []

                                        container_type = details.get("type_container", [])
                                        ground_service = details.get("ground_service", "")
                                        is_reefer_container = any(ct in reefer_containers for ct in container_type)

                                        if not is_reefer_container and ground_service not in reefer_ground_services:
                                            grouped_record["reefer_details"] = "No reefer details"
                                        else:
                                            if details.get("drayage_reefer", False):  
                                                reefer_details.append("Drayage Reefer Required")

                                            if details.get("pickup_thermo_king", False):  
                                                reefer_details.append("Thermo King Pickup Required")

                                            if details.get("reefer_cont_type"):  
                                                reefer_details.append(f"Reefer Container Type: {details['reefer_cont_type']}")

                                            if details.get("temperature_control", False):  
                                                reefer_details.append("Temperature Control Required")

                                            if details.get("temperature"):  
                                                reefer_details.append(f"Temperature Range: {details['temperature']}°C")

                                            grouped_record["reefer_details"] = "\n".join(reefer_details) if reefer_details else "No reefer details"

                                        if isinstance(grouped_record["reefer_details"], list):
                                            grouped_record["reefer_details"] = "\n".join(grouped_record["reefer_details"])

                                        # **6️⃣ Additional Costs (destination_cost + customs_origin)**
                                        additional_costs = []

                                        if details.get("destination_cost", False):
                                            additional_costs.append("Destination Cost Required")

                                        if details.get("customs_origin", False):
                                            additional_costs.append("Customs at Origin Required")

                                        if details.get("insurance_required", False):
                                            additional_costs.append("Insurance Required")

                                        grouped_record["additional_costs"] = "\n".join(additional_costs) if additional_costs else "No additional costs"

                                        # **7️⃣ Agregar detalles adicionales**
                                        for key, value in details.items():
                                            if key in ["reinforced", "food_grade", "isotank", "flexitank", "imo_cargo", "imo_type", "un_code", "routes", "packages", 
                                                    "dimensions_flatrack", "customs_origin", "destination_cost", "type_container", "ground_routes"]:
                                                continue
                                            if value is None or value == "" or (isinstance(value, (int, float)) and value == 0):
                                                continue
                                            if isinstance(value, bool):
                                                value = "Sí" if value else "No"

                                            if key in all_details:
                                                all_details[key].add(str(value))
                                            else:
                                                all_details[key] = {str(value)}
                                    
                                    # volumen = st.session_state.get("volumen_num", 0)
                                    # print(volumen)
                                    # frequency = st.session_state.get("volumen_frequency", "")
                                    # print(frequency)
                                    # user_comments = st.session_state.get("final_comments", "").strip()
                                    # print(user_comments)

                                    # volumen_info = f"Volumen estimado: {volumen} {frequency}" if volumen > 0 or frequency else ""
                                    # print(volumen_info)

                                    # if volumen_info and user_comments:
                                    #     grouped_record["final_comments"] = f"{volumen_info}\n{user_comments}"
                                    # elif volumen_info:
                                    #     grouped_record["final_comments"] = volumen_info
                                    # else:
                                    #     grouped_record["final_comments"] = user_comments
                                    
                                    # print(grouped_record["final_comments"])

                                    # **8️⃣ Convertir sets a cadenas separadas por saltos de línea**
                                    for key in ["service", "container_characteristics", "imo", "routes_info", "info_pallets_str", "info_flatrack", "type_container"]:
                                        grouped_record[key] = "\n".join(sorted(grouped_record[key])) if grouped_record[key] else ""

                                    for key, value_set in all_details.items():
                                        grouped_record[key] = "\n".join(sorted(value_set))

                                    # **9️⃣ Crear DataFrame y guardar**
                                    new_df = pd.DataFrame([grouped_record])

                                    new_df = new_df.reindex(columns=all_quotes_columns, fill_value="")

                                    st.session_state["df_all_quotes"] = pd.concat(
                                        [st.session_state.get("df_all_quotes", pd.DataFrame()), new_df],
                                        ignore_index=True
                                    )

                                    save_to_google_sheets(st.session_state["df_all_quotes"], sheet_id)

                                    del st.session_state["request_id"]
                                    upload_all_files_to_google_drive(folder_id, drive_service)
                                    clear_temp_directory()
                                    reset_json()
                                    st.session_state["services"] = []
                                    st.session_state["start_time"] = None
                                    st.session_state["end_time"] = None
                                    st.session_state["quotation_completed"] = False
                                    st.session_state["page"] = "client_name"
                                    st.success(f"Quotation completed! Your request ID is {request_id}")
                                    st.session_state.clear()
                                    change_page("client_name")

                                except Exception as e:
                                    st.error(f"An error occurred: {str(e)}")
                                    st.session_state["submitted"] = False

                            else:
                                st.warning("No services have been added to finalize the quotation.")

                    st.button("Finalize Quotation", on_click=handle_finalize_quotation)