import json
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import PyPDF2
from reportlab.platypus import Table, TableStyle
import streamlit as st
from reportlab.pdfbase.ttfonts import TTFont
import os
from reportlab.pdfbase import pdfmetrics
from datetime import date
from src.services.auth import user_data

font_path = "resources/fonts/OpenSauceSans-Regular.ttf"
font_bold = "resources/fonts/OpenSauceSans-Bold.ttf"

if os.path.exists(font_path):
    pdfmetrics.registerFont(TTFont("OpenSauce", font_path))
else:
    print("⚠️ Advertencia: La fuente 'Open Sauce' no se encontró. Se usará 'Helvetica' como alternativa.")

if os.path.exists(font_bold):
    pdfmetrics.registerFont(TTFont("OpenSauceBold", font_bold))
else:
    print("⚠️ Advertencia: La fuente 'Open Sauce Bold' no se encontró. Se usará 'Helvetica' como alternativa.")


def create_overlay(data, overlay_path):

    commercial_data = user_data()
    c = canvas.Canvas(overlay_path, pagesize=letter)

    fecha = date.today()
    fecha_str = fecha.strftime("%d/%m/%Y")

    c.setFont("OpenSauceBold", 10)

    c.drawString(480, 688, f"{data.get('request_id', '')}")
    c.drawString(440, 675, fecha_str)
    c.drawString(460, 665,f"{data.get('validity', '')}")

    c.setFont("OpenSauce", 10)
    c.drawString(90, 585, f"{commercial_data.get('name', '')}")
    c.drawString(90, 573, f"{commercial_data.get('position', '')}")
    c.drawString(90, 561, f"{commercial_data.get('tel', '')}")
    c.drawString(90, 549, f"{commercial_data.get('email', '')}")

    c.drawString(400, 585, f"{data.get('customer_name', '')}")

    c.drawString(160, 495, f"MARITIME")
    c.drawString(160, 482, f"{data.get('incoterm', '')}")
    c.drawString(160, 469, f"{data.get('pol', '').upper()} - {data.get('pod', '').upper()}")

    c.setFont("OpenSauceBold", 10) 
    c.drawString(400, 603, f"{data.get('client', '').upper()}")

    table_data = []
    total_sale = 0.0

    # Procesar los surcharges (cada clave es una categoría, por ejemplo "Origen" o "Flete")
    surcharges = data.get("surcharges", {})
    for category, details in surcharges.items():
        for container, values in details.items():
            sale = values.get("sale", 0)
            sale_str = f"${sale:.2f}"
            total_sale += sale
            row = [
                category,                   # Concepto
                "USD",                      # Moneda
                container,                  # Contenedor
                sale_str                  # Venta (con el signo $)
            ]
            table_data.append(row)

    # Procesar los additional_surcharges
    for additional in data.get("additional_surcharges", []):
        sale = additional.get("sale", 0)
        sale_str = f"${sale:.2f}"
        total_sale += sale
        row = [
            additional.get("concept", ""),  # Concepto
            "USD",                          # Moneda
            "",                             # Contenedor (no aplica)
            sale_str,                     # Costo (con el signo $)
        ]
        table_data.append(row)
    
    insurance = data.get("insurance_sale", 0)
    if insurance:
        total_sale += insurance
        row = [
            "Insurance",
            "USD",
            "",
            f"${insurance}"
        ]
        table_data.append(row)

    
    col_widths = [80, 140, 120, 85]

    table = Table(table_data, colWidths=col_widths)

    style = TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'OpenSauce'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ])
    table.setStyle(style)

    x = 100
    y = 425
    table_width, table_height = table.wrapOn(c, 0, 0)
    table.drawOn(c, x, y - table_height)

    c.setFont("OpenSauceBold", 10)
    c.drawString(400, 200, f"TOTAL ${total_sale} USD")

    y_position = 150
    notes = data.get("Notes", " ")
    notes_separated = ",".join(notes.splitlines())

    left_x = 88            
    right_x = 300          
    start_y = y_position   
    line_space = 10        
    c.setFont("OpenSauceBold", 9)
    c.drawString(left_x, start_y, "Transit Time:")

    c.setFont("OpenSauce", 9)
    transit = data.get('Details', {}).get('Transit Time', 'N/A')
    c.drawString(left_x + 65, start_y, f"{transit} days")

    c.setFont("OpenSauceBold", 9)
    c.drawString(left_x, start_y - line_space, "Route:")
    c.setFont("OpenSauce", 9)
    route = data.get('Details', {}).get('Route', 'N/A')
    c.drawString(left_x + 38, start_y - line_space, route)

    c.setFont("OpenSauceBold", 9)
    c.drawString(right_x, start_y, "Free Days in Origin:")
    c.setFont("OpenSauce", 9)
    free_origin = data.get('Details', {}).get('Free Days in Origin', 'N/A')
    free_origin_str = str(free_origin)
    c.drawString(right_x + 95, start_y, free_origin_str)

    c.setFont("OpenSauceBold", 9)
    c.drawString(right_x, start_y - line_space, "Free Days in Destination:")
    c.setFont("OpenSauce", 9)
    free_dest = data.get('Details', {}).get('Free Days in Destination', 'N/A')
    ree_dest_str = str(free_dest)
    c.drawString(right_x + 115, start_y - line_space, ree_dest_str)

    x = 88                   
    y = y_position - 25          
    max_width = 500               
    font_name = "OpenSauce"
    font_size = 9

    words = [w.strip() for w in notes_separated.split(",")]
    line = ""

    for word in words:
        sep = ", " if line != "" else ""
        test_line = line + sep + word
        if c.stringWidth(test_line, font_name, font_size) <= max_width:
            line = test_line
        else:
            c.drawString(x, y, line)
            y -= font_size * 1.2 
            line = word

    if line:
        c.drawString(x, y, line)

    c.save()

def merge_pdfs(template_path, overlay_path, output_path):
    template_pdf = PyPDF2.PdfReader(template_path)
    overlay_pdf = PyPDF2.PdfReader(overlay_path)
    output = PyPDF2.PdfWriter()

    for page_number in range(len(template_pdf.pages)):
        template_page = template_pdf.pages[page_number]
        if page_number < len(overlay_pdf.pages):
            overlay_page = overlay_pdf.pages[page_number]
            template_page.merge_page(overlay_page)
        output.add_page(template_page)
    
    with open(output_path, "wb") as f_out:
        output.write(f_out)

def generate_quotation(data, template_path="resources/documents/Quotations forms.pdf", output_path="resources/documents/quotation.pdf", overlay_path="resources/documents/overlay.pdf"):
    create_overlay(data, overlay_path)
    merge_pdfs(template_path, overlay_path, output_path)
    return output_path
