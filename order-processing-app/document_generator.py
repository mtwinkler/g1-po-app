# document_generator.py
from datetime import datetime, timezone
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepInFrame, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from io import BytesIO
import os
import traceback
import re
from xml.sax.saxutils import escape
from functools import partial

# --- FONT REGISTRATION ---
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONTS_DIR_IN_CONTAINER = '/app/fonts'

try:
    # Register individual TTF files
    pdfmetrics.registerFont(TTFont('EloquiaDisplay-Regular', os.path.join(FONTS_DIR_IN_CONTAINER, 'eloquia-display-regular.ttf')))
    pdfmetrics.registerFont(TTFont('EloquiaDisplay-SemiBold', os.path.join(FONTS_DIR_IN_CONTAINER, 'eloquia-display-semibold.ttf')))
    pdfmetrics.registerFont(TTFont('EloquiaDisplay-ExtraBold', os.path.join(FONTS_DIR_IN_CONTAINER, 'eloquia-display-extrabold.ttf')))
    pdfmetrics.registerFont(TTFont('EloquiaText-ExtraLight', os.path.join(FONTS_DIR_IN_CONTAINER, 'eloquia-text-extralight.ttf')))

    # Map EloquiaDisplay variants to Helvetica
    pdfmetrics.addMapping('Helvetica', 0, 0, 'EloquiaDisplay-Regular')    # Normal Helvetica uses EloquiaDisplay-Regular
    pdfmetrics.addMapping('Helvetica', 1, 0, 'EloquiaDisplay-SemiBold') # Bold Helvetica uses EloquiaDisplay-SemiBold

    # Map EloquiaText-ExtraLight to Times-Roman
    pdfmetrics.addMapping('Times-Roman', 0, 0, 'EloquiaText-ExtraLight')

    pdfmetrics.registerFontFamily('EloquiaDisplay', normal='EloquiaDisplay-Regular', bold='EloquiaDisplay-SemiBold')
    pdfmetrics.registerFontFamily('EloquiaText', normal='EloquiaText-ExtraLight')

    print("DEBUG DOC_GEN: Successfully registered Eloquia fonts and mapped to Helvetica/Times-Roman.")

except Exception as e:
    print(f"ERROR DOC_GEN: Failed to register/map custom Eloquia fonts. PDFs may use a default font. Error: {e}")
    traceback.print_exc()
# --- END FONT REGISTRATION ---

try:
    from PIL import Image as PILImage
    print("DEBUG DOC_GEN: Pillow library imported successfully.")
except ImportError:
    print("ERROR DOC_GEN: Pillow library (PIL) not found. Image processing will fail. Please install it (`pip install Pillow`).")
    PILImage = None

try:
    from google.cloud import storage
    storage_client = storage.Client()
    print("DEBUG DOC_GEN: Google Cloud Storage client initialized successfully.")
except ImportError:
    print("WARN DOC_GEN: google-cloud-storage library not found. Logo download from GCS will fail.")
    storage = None
    storage_client = None
except Exception as gcs_e:
    print(f"ERROR DOC_GEN: Failed to initialize Google Cloud Storage client: {gcs_e}")
    traceback.print_exc()
    storage_client = None

COMPANY_NAME = "GLOBAL ONE TECHNOLOGY"
COMPANY_ADDRESS_PO_HEADER = ""
COMPANY_ADDRESS_PACKING_SLIP_FOOTER_LINE1 = "4916 S 184th Plaza - Omaha, NE 68135"
COMPANY_ADDRESS_PACKING_SLIP_HEADER_LINE1 = "GLOBAL ONE TECHNOLOGY"
COMPANY_ADDRESS_PACKING_SLIP_HEADER_LINE2 = "4916 S 184th Plaza - Omaha, NE 68135"

COMPANY_PHONE = "(877) 418-3246"
COMPANY_FAX = "(866) 921-1032"
COMPANY_EMAIL = "sales@globalonetechnology.com"
COMPANY_WEBSITE = "www.globalonetechnology.com"

def format_currency(value):
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        try:
            return f"${float(str(value)):,.2f}"
        except:
             return "$0.00"

def _format_shipping_method_for_display(method_string):
    if not method_string or not isinstance(method_string, str):
        return "N/A"
    match = re.search(r'\(([^)]+)\)[^(]*$', method_string)
    if match:
        return match.group(1).strip()
    return method_string.strip()

def get_custom_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(name='Normal_Eloquia', fontName='Helvetica', fontSize=9, leading=11))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Small', parent=styles['Normal_Eloquia'], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Bold', fontName='Helvetica-Bold', fontSize=9, leading=11))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Right', parent=styles['Normal_Eloquia'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Center', parent=styles['Normal_Eloquia'], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Bold_Right', parent=styles['Normal_Eloquia_Bold'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Bold_Center', parent=styles['Normal_Eloquia_Bold'], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='H1_Eloquia', fontName='Helvetica-Bold', fontSize=16, leading=18, parent=styles['h1']))
    styles.add(ParagraphStyle(name='H1_Eloquia_Right', parent=styles['H1_Eloquia'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='H2_Eloquia', fontName='Helvetica-Bold', fontSize=14, leading=16, parent=styles['h2']))
    styles.add(ParagraphStyle(name='H3_Eloquia', fontName='Helvetica-Bold', fontSize=10, leading=12, parent=styles['h3']))
    styles.add(ParagraphStyle(name='ItemDesc_Eloquia', parent=styles['Normal_Eloquia'], fontSize=9, leading=11))
    styles.add(ParagraphStyle(name='FulfillmentNoteStyle_Eloquia', parent=styles['Normal_Eloquia'], fontSize=9, leading=11, textColor=colors.HexColor("#666666")))
    styles.add(ParagraphStyle(name='ItemDesc_ShippingSeparately_Eloquia', parent=styles['ItemDesc_Eloquia'], textColor=colors.HexColor("#777777")))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Center_ShippingSeparately', parent=styles['Normal_Eloquia_Center'], textColor=colors.HexColor("#777777")))
    styles.add(ParagraphStyle(name='CustomerNotesStyle_Eloquia', parent=styles['Normal_Eloquia'], spaceBefore=6, spaceAfter=6, leading=12, leftIndent=0.25*inch, rightIndent=0.25*inch))
    styles.add(ParagraphStyle(name='FooterStyle_Eloquia', fontName='Times-Roman', fontSize=8, leading=10, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='EnvironmentNoteStyle_Eloquia', fontName='Times-Roman', fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#888888")))
    styles.add(ParagraphStyle(name='Normal_Helvetica', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=11))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Small', parent=styles['Normal_Helvetica'], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Bold', parent=styles['Normal_Helvetica'], fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='H1_Helvetica_Right', parent=styles['Normal_Helvetica_Bold'], fontSize=16, alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='H2_Helvetica', parent=styles['Normal_Helvetica_Bold'], fontSize=14))
    styles.add(ParagraphStyle(name='H3_Helvetica', parent=styles['Normal_Helvetica_Bold'], fontSize=10))
    styles.add(ParagraphStyle(name='ItemDesc', parent=styles['Normal_Helvetica']))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Right', parent=styles['Normal_Helvetica'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Bold_Right', parent=styles['Normal_Helvetica_Bold'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Center', parent=styles['Normal_Helvetica'], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='FulfillmentNoteStyle', parent=styles['Normal_Helvetica'], fontSize=9, textColor=colors.HexColor("#666666")))
    return styles

def _get_logo_element_from_gcs(styles, logo_gcs_uri=None, desired_logo_width=1.5*inch, is_blind_slip=False):
    if is_blind_slip:
        # For blind slips, return an empty paragraph or a minimal placeholder if absolutely necessary
        # Removing "SHIPPING DOCUMENT" text
        return Paragraph("", styles['H2_Eloquia']) # Empty string

    if not logo_gcs_uri:
        print("WARN _get_logo_element_from_gcs: No logo_gcs_uri provided. Using company name text.")
        return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Eloquia'])

    if not storage_client:
        print("WARN _get_logo_element_from_gcs: GCS storage client not available. Using company name text.")
        return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Eloquia'])
    logo_stream = None
    try:
        print(f"DEBUG _get_logo_element_from_gcs: Attempting to download logo from: {logo_gcs_uri}")
        if not logo_gcs_uri.startswith("gs://"): raise ValueError("Invalid GCS URI format. Must start with 'gs://'.")
        parts = logo_gcs_uri[5:].split('/', 1)
        if len(parts) != 2: raise ValueError("Invalid GCS URI format. Could not parse bucket and blob name.")
        bucket_name, blob_name = parts
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists(): raise FileNotFoundError(f"Logo not found at {logo_gcs_uri}")
        logo_bytes = blob.download_as_bytes()
        logo_stream = BytesIO(logo_bytes)
        logo_stream.seek(0)
        actual_logo_width = desired_logo_width
        actual_logo_height = None
        if PILImage:
            try:
                pillow_img = PILImage.open(logo_stream)
                pillow_img.verify()
                logo_stream.seek(0)
                pillow_img = PILImage.open(logo_stream)
                img_width_px, img_height_px = pillow_img.size
                if not img_width_px or not img_height_px or img_width_px == 0 or img_height_px == 0:
                    raise ValueError("Pillow reported invalid image dimensions (0 or None).")
                aspect_ratio = float(img_height_px) / float(img_width_px)
                actual_logo_height = desired_logo_width * aspect_ratio
                logo_stream.seek(0)
            except Exception as pil_e:
                print(f"ERROR _get_logo_element_from_gcs: Pillow failed: {pil_e}"); traceback.print_exc()
                return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Eloquia'])
        else:
            logo_stream.seek(0)
            actual_logo_height = 0.75 * inch

        logo = Image(logo_stream, width=actual_logo_width, height=actual_logo_height)
        if not logo.imageWidth or not logo.imageHeight or logo.imageWidth == 0 or logo.imageHeight == 0:
            print(f"WARN _get_logo_element_from_gcs: ReportLab Image dimensions seem invalid for '{logo_gcs_uri}'. Attempting fallback render.")
            raise ValueError("ReportLab image dimensions invalid after Pillow processing or Pillow unavailable.")
        return logo
    except Exception as e:
        print(f"ERROR _get_logo_element_from_gcs: Failed to load logo: {e}"); traceback.print_exc()
        if logo_stream and not logo_stream.closed: logo_stream.close()
        return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Eloquia'])


def generate_purchase_order_pdf(order_data, supplier_data, po_number, po_date, po_items,
                                payment_terms, payment_instructions, logo_gcs_uri=None,
                                is_partial_fulfillment=False):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=0.75*inch, rightMargin=0.75*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = get_custom_styles()
    story = []
    logo_element = _get_logo_element_from_gcs(styles, logo_gcs_uri, desired_logo_width=2.6*inch, is_blind_slip=False)
    if isinstance(po_date, str):
        try:
            po_date = datetime.fromisoformat(po_date.replace('Z', '+00:00'))
        except ValueError:
            print(f"WARN: po_date is a string '{po_date}' and could not be parsed to datetime. Using as string.")
    formatted_po_date = po_date.strftime("%m/%d/%Y") if hasattr(po_date, 'strftime') else str(po_date)
    header_data = [
        [logo_element, Paragraph("<b>PURCHASE ORDER</b>", styles['H1_Helvetica_Right'])],
        [Paragraph(COMPANY_ADDRESS_PO_HEADER, styles['Normal_Helvetica']),
         Paragraph(f"Date: {formatted_po_date}<br/>P.O. No.: {po_number}", styles['Normal_Helvetica_Right'])]
    ]
    header_table = Table(header_data, colWidths=[4*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (0,0), 6),
        ('BOTTOMPADDING', (0,1), (0,1), 6), ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0), ('SPAN', (0,0), (0,0)),
    ]))
    story.append(header_table); story.append(Spacer(1, 0.25 * inch))
    vendor_ship_to_content = [
        [Paragraph("<b>Vendor</b>", styles['H3_Helvetica']), Paragraph("<b>Ship To</b>", styles['H3_Helvetica'])],
        [Paragraph(f"{escape(supplier_data.get('name', 'N/A'))}<br/>"
                   f"{escape(supplier_data.get('address_line1', ''))}<br/>"
                   f"{escape(supplier_data.get('address_line2', '') or '')}<br/>"
                   f"{escape(supplier_data.get('city', ''))}, {escape(supplier_data.get('state', ''))} {escape(supplier_data.get('zip', ''))}<br/>"
                   f"{escape(supplier_data.get('country', ''))}", styles['Normal_Helvetica']),
         Paragraph(f"PLEASE BLIND DROP SHIP<br/>USING ATTACHED LABEL<br/>AND PACKING SLIP<br/><br/>"
                   f"<b>{escape(order_data.get('customer_company', ''))}</b><br/>"
                   f"{escape(order_data.get('customer_name', ''))}<br/>"
                   f"{escape(order_data.get('customer_shipping_address_line1', ''))}<br/>"
                   f"{escape(order_data.get('customer_shipping_address_line2', '') or '')}<br/>"
                   f"{escape(order_data.get('customer_shipping_city', ''))}, {escape(order_data.get('customer_shipping_state', ''))} {escape(order_data.get('customer_shipping_zip', ''))}<br/>"
                   f"{escape(order_data.get('customer_shipping_country', ''))}", styles['Normal_Helvetica'])]
    ]
    vendor_ship_to_table = Table(vendor_ship_to_content, colWidths=[3.5*inch, 3.5*inch])
    vendor_ship_to_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(vendor_ship_to_table); story.append(Spacer(1, 0.25 * inch))
    items_header = [
        Paragraph('<b>Item</b>', styles['Normal_Helvetica_Bold']),
        Paragraph('<b>Qty</b>', styles['Normal_Helvetica_Center']),
        Paragraph('<b>Rate</b>', styles['Normal_Helvetica_Bold_Right']),
        Paragraph('<b>Amount</b>', styles['Normal_Helvetica_Bold_Right'])
    ]
    items_table_data = [items_header]
    total_po_amount = 0
    for item in po_items:
        item_amount = float(item.get('quantity', 0)) * float(item.get('unit_cost', 0.00))
        total_po_amount += item_amount
        description_text = f"{escape(item.get('description', 'N/A'))}"
        items_table_data.append([
            Paragraph(description_text, styles['ItemDesc']),
            Paragraph(str(item.get('quantity', 0)), styles['Normal_Helvetica_Center']),
            Paragraph(format_currency(item.get('unit_cost', 0.00)), styles['Normal_Helvetica_Right']),
            Paragraph(format_currency(item_amount), styles['Normal_Helvetica_Right'])
        ])
    items_table = Table(items_table_data, colWidths=[4.0*inch, 0.5*inch, 1.0*inch, 1.5*inch])
    items_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black), ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4), ('TOPPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(items_table); story.append(Spacer(1, 0.1 * inch))
    notes_and_total_data = []
    if payment_instructions:
        notes_and_total_data.append([Paragraph(escape(payment_instructions).replace('\n', '<br/>'), styles['ItemDesc']), '', '', ''])
    if order_data.get('bigcommerce_order_id'):
        fulfillment_text_prefix = "Partial fulfillment of G1 Order #" if is_partial_fulfillment else "Fulfillment of G1 Order #"
        bc_order_id_str = str(order_data.get('bigcommerce_order_id', 'N/A'))
        notes_and_total_data.append([
            Paragraph(f"{fulfillment_text_prefix}{escape(bc_order_id_str)}", styles['FulfillmentNoteStyle']),
            '', '', ''
        ])
    if notes_and_total_data:
        notes_and_total_data.append(['', '', '', ''])
    notes_and_total_data.append([
        '', '',
        Paragraph("<b>Total</b>", styles['Normal_Helvetica_Bold_Right']),
        Paragraph(f"<b>USD {format_currency(total_po_amount)}</b>", styles['Normal_Helvetica_Bold_Right'])
    ])
    if notes_and_total_data:
        notes_total_table = Table(notes_and_total_data, colWidths=[4.0*inch, 0.5*inch, 1.0*inch, 1.5*inch])
        style_cmds = [('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (0,-1), 0)]
        current_row_for_span = 0
        if payment_instructions:
            style_cmds.append(('SPAN', (0,current_row_for_span), (3,current_row_for_span)))
            current_row_for_span +=1
        if order_data.get('bigcommerce_order_id'):
            style_cmds.append(('SPAN', (0,current_row_for_span), (3,current_row_for_span)))
        total_row_idx = len(notes_and_total_data) - 1
        style_cmds.append(('TOPPADDING', (2, total_row_idx), (3, total_row_idx), 10))
        notes_total_table.setStyle(TableStyle(style_cmds))
        story.append(notes_total_table)
    story.append(Spacer(1, 0.3 * inch))
    doc.build(story)
    pdf_bytes = buffer.getvalue(); buffer.close()
    return pdf_bytes

def _draw_packing_slip_footer(canvas, doc, is_blind_slip=False):
    canvas.saveState()
    styles = get_custom_styles()
    if not is_blind_slip:
        available_width = doc.width
        current_y = 0.3 * inch
        env_text = """In an effort to minimize our footprint on the environment,<br/>Global One Technology uses clean, recycled packaging materials."""
        p_env = Paragraph(env_text, styles['EnvironmentNoteStyle_Eloquia'])
        p_env.wrapOn(canvas, available_width, doc.bottomMargin); p_env.drawOn(canvas, doc.leftMargin, current_y)
        current_y += p_env.height + 0.1 * inch
        company_footer_text = f"<b>{COMPANY_NAME}</b><br/>Voice: {COMPANY_PHONE} Fax: {COMPANY_FAX}<br/>{COMPANY_ADDRESS_PACKING_SLIP_FOOTER_LINE1}<br/>Email: {COMPANY_EMAIL} Website: {COMPANY_WEBSITE}"
        p_company = Paragraph(company_footer_text, styles['FooterStyle_Eloquia'])
        p_company.wrapOn(canvas, available_width, doc.bottomMargin); p_company.drawOn(canvas, doc.leftMargin, current_y)
        current_y += p_company.height + 0.15 * inch
        faq_text = f"""<b>FAQ's:</b><br/>1. We ordered the wrong part or have a defective item. How would we arrange a return?<br/>
        Please visit http://www.globalonetechnology.com/returns for information on how to return an item.<br/><br/>
        2. How can I get a copy of our invoice for bookkeeping/accounting?<br/>
        Please email sales@globalonetechnology.com to request a copy of your invoice."""
        p_faq = Paragraph(faq_text, styles['Normal_Eloquia_Small'])
        p_faq.wrapOn(canvas, available_width, doc.bottomMargin); p_faq.drawOn(canvas, doc.leftMargin, current_y)
    else:
        print("DEBUG DOC_GEN (Footer): Blind slip, footer skipped.")
    canvas.restoreState()


def generate_packing_slip_pdf(order_data, items_in_this_shipment, items_shipping_separately,
                              logo_gcs_uri=None, is_g1_onsite_fulfillment=False,
                              is_blind_slip=False, custom_ship_from_address=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.5*inch, bottomMargin=1.9*inch)
    styles = get_custom_styles()
    story = []

    logo_element_to_use = None
    company_address_display_ps_para = None
    packing_slip_title_text = "PACKING SLIP"
    order_ref_text = "" # Initialize to empty

    if is_blind_slip:
        print("DEBUG DOC_GEN (Packing Slip): Generating BLIND slip.")
        logo_element_to_use = Paragraph("", styles['H2_Eloquia']) # Empty string for logo area
        packing_slip_title_text = "PACKING SLIP" # Keep title for blind, or make it generic like "SHIPMENT CONTENTS"

        if custom_ship_from_address:
            company_address_text_blind = f"{escape(custom_ship_from_address.get('name', ''))}<br/>" \
                                         f"{escape(custom_ship_from_address.get('street_1', ''))}<br/>"
            if custom_ship_from_address.get('street_2'):
                company_address_text_blind += f"{escape(custom_ship_from_address.get('street_2', ''))}<br/>"
            company_address_text_blind += f"{escape(custom_ship_from_address.get('city', ''))}, {escape(custom_ship_from_address.get('state', ''))} {escape(custom_ship_from_address.get('zip', ''))}<br/>" \
                                          f"{escape(custom_ship_from_address.get('country', ''))}"
            company_address_display_ps_para = Paragraph(company_address_text_blind, styles['Normal_Eloquia_Small'])
        else:
            company_address_display_ps_para = Paragraph("", styles['Normal_Eloquia_Small'])
        # order_ref_text remains empty for blind slips
    else: # Not a blind slip
        logo_element_to_use = _get_logo_element_from_gcs(styles, logo_gcs_uri, desired_logo_width=2.6*inch, is_blind_slip=False)
        company_header_address_text_non_blind = f"{COMPANY_ADDRESS_PACKING_SLIP_HEADER_LINE1}<br/>{COMPANY_ADDRESS_PACKING_SLIP_HEADER_LINE2}"
        company_address_display_ps_para = Paragraph(escape(company_header_address_text_non_blind).replace('\n', '<br/>'), styles['Normal_Eloquia_Small'])
        if is_g1_onsite_fulfillment:
            packing_slip_title_text = "PACKING SLIP"

        current_date_obj = datetime.now(timezone.utc)
        formatted_current_date = current_date_obj.strftime("%m/%d/%Y")
        bc_order_id_ps_str = str(order_data.get('bigcommerce_order_id', 'N/A'))
        order_ref_text = f"Date: {formatted_current_date}<br/>Order #: {escape(bc_order_id_ps_str)}"

    header_data = [
        [logo_element_to_use, Paragraph(f"<b>{packing_slip_title_text}</b>", styles['H1_Eloquia_Right'])],
        [company_address_display_ps_para, Paragraph(order_ref_text, styles['Normal_Eloquia_Right'])] # order_ref_text will be empty for blind
    ]
    header_table = Table(header_data, colWidths=[4*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (0,0), 6),
        ('SPAN', (0,0), (0,0)),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceBefore=0.05*inch, spaceAfter=0.1*inch))

    ship_to_address_parts = []
    customer_company = order_data.get('customer_company', '')
    if customer_company: ship_to_address_parts.append(escape(customer_company))
    ship_to_address_parts.append(escape(order_data.get('customer_name', '')))
    ship_to_address_parts.append(escape(order_data.get('customer_shipping_address_line1', '')))
    if order_data.get('customer_shipping_address_line2'):
        ship_to_address_parts.append(escape(order_data.get('customer_shipping_address_line2', '')))
    ship_to_address_parts.append(f"{escape(order_data.get('customer_shipping_city', ''))}, {escape(order_data.get('customer_shipping_state', ''))} {escape(order_data.get('customer_shipping_zip', ''))}")
    ship_to_address_parts.append(escape(order_data.get('customer_shipping_country', '')))

    ship_to_address_text = "<br/>".join(filter(None, ship_to_address_parts))
    ship_to_para = Paragraph(ship_to_address_text, styles['Normal_Eloquia'])

    formatted_shipping_method_display = _format_shipping_method_for_display(order_data.get('customer_shipping_method', 'N/A'))
    
    right_column_content = [
        Paragraph(f"<b>Shipping Method:</b> {escape(formatted_shipping_method_display)}", styles['Normal_Eloquia_Right']),
    ]
    if not is_blind_slip: # Only add payment method if not a blind slip
        raw_payment_method = order_data.get('payment_method', 'N/A')
        formatted_payment_method_display = _format_shipping_method_for_display(raw_payment_method)
        right_column_content.extend([
            Spacer(1, 0.05 * inch),
            Paragraph(f"<b>Payment Method:</b> {escape(formatted_payment_method_display)}", styles['Normal_Eloquia_Right'])
        ])

    shipping_details_data = [
        [Paragraph("<b>Ship To:</b>", styles['H3_Eloquia']), ""],
        [ship_to_para, KeepInFrame(3.5*inch, 1.2*inch, right_column_content)]
    ]
    shipping_details_table = Table(shipping_details_data, colWidths=[3.5*inch, 3.5*inch])
    shipping_details_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('SPAN', (1,0), (1,0)),
    ]))
    story.append(shipping_details_table)
    story.append(Spacer(1, 0.15 * inch))

    if not is_blind_slip: # Only add customer notes if not a blind slip
        customer_notes = order_data.get('customer_notes', '').strip()
        if customer_notes:
            story.append(Paragraph("<b>Customer Notes:</b>", styles['Normal_Eloquia_Bold']))
            notes_paragraph_content = escape(customer_notes).replace('\n', '<br/>\n')
            story.append(Paragraph(notes_paragraph_content, styles['CustomerNotesStyle_Eloquia']))
            story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("<b>IN THIS SHIPMENT:</b>", styles['H3_Eloquia']))
    story.append(Spacer(1, 0.05 * inch))

    items_header_shipped = [
        Paragraph('<b>Qty</b>', styles['Normal_Eloquia_Bold_Center']),
        Paragraph('<b>Item</b>', styles['Normal_Eloquia_Bold'])
    ]
    items_table_data_shipped = [items_header_shipped]
    if items_in_this_shipment:
        for item in items_in_this_shipment:
            item_description_for_slip = item.get('name', 'N/A')
            items_table_data_shipped.append([
                Paragraph(str(item.get('quantity', 0)), styles['Normal_Eloquia_Center']),
                Paragraph(escape(item_description_for_slip), styles['ItemDesc_Eloquia'])
            ])
    else:
        items_table_data_shipped.append([
            Paragraph("<i>(No items in this specific shipment segment)</i>", styles['ItemDesc_Eloquia'], colSpan=2)
        ])

    items_table_shipped = Table(items_table_data_shipped, colWidths=[0.75*inch, 6.25*inch])
    style_cmds_shipped = [
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (0,0), 'CENTER'), ('ALIGN', (1,0), (1,0), 'LEFT'),
        ('ALIGN', (0,1), (0,-1), 'CENTER'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4), ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f0f0f0")),
    ]
    if not items_in_this_shipment:
        style_cmds_shipped.append(('SPAN', (0, len(items_table_data_shipped)-1), (1, len(items_table_data_shipped)-1)))
        style_cmds_shipped.append(('ALIGN', (0, len(items_table_data_shipped)-1), (0, len(items_table_data_shipped)-1), 'CENTER'))

    items_table_shipped.setStyle(TableStyle(style_cmds_shipped))
    story.append(items_table_shipped)
    story.append(Spacer(1, 0.2 * inch))

    if items_shipping_separately:
        story.append(Paragraph("<b>SHIPPING SEPARATELY:</b>", styles['H3_Eloquia']))
        story.append(Spacer(1, 0.05 * inch))
        items_header_separate = [
            Paragraph('<b>Qty</b>', styles['Normal_Eloquia_Bold_Center']),
            Paragraph('<b>Item</b>', styles['Normal_Eloquia_Bold'])
        ]
        items_table_data_separate = [items_header_separate]
        for item in items_shipping_separately:
            item_description_for_slip_sep = item.get('name', 'N/A')
            items_table_data_separate.append([
                Paragraph(str(item.get('quantity', 0)), styles['Normal_Eloquia_Center_ShippingSeparately']),
                Paragraph(escape(item_description_for_slip_sep), styles['ItemDesc_ShippingSeparately_Eloquia'])
            ])
        items_table_separate = Table(items_table_data_separate, colWidths=[0.75*inch, 6.25*inch])
        items_table_separate.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.darkgrey),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (0,0), (0,0), 'CENTER'), ('ALIGN', (1,0), (1,0), 'LEFT'),
            ('ALIGN', (0,1), (0,-1), 'CENTER'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4), ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f0f0f0")),
            ('TEXTCOLOR', (0,1), (-1,-1), colors.HexColor("#777777")),
        ]))
        story.append(items_table_separate)

    draw_footer_with_flag = partial(_draw_packing_slip_footer, is_blind_slip=is_blind_slip)
    doc.build(story, onFirstPage=draw_footer_with_flag, onLaterPages=draw_footer_with_flag)

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

if __name__ == '__main__':
    print("Running document_generator.py in local test mode.")
    print("NOTE: Logo will be text unless GCS is configured and test_logo_gcs_uri is set.")

    sample_order_data_po = {
        'bigcommerce_order_id': 12345,
        'customer_company': 'Customer Company LLC',
        'customer_name': 'Alice Wonderland',
        'customer_shipping_address_line1': '123 Main St',
        'customer_shipping_address_line2': 'Apt 4B',
        'customer_shipping_city': 'Anytown',
        'customer_shipping_state': 'AS',
        'customer_shipping_zip': '12345',
        'customer_shipping_country': 'USA',
        'customer_phone': '555-0101'
    }
    sample_supplier_data = { 'name': 'Test Supplier Inc.', 'address_line1': '123 Test St', 'city': 'Testville', 'state': 'TS', 'zip': '12345', 'country': 'USA', 'payment_terms': 'Net 30' }
    sample_po_items = [{'sku': 'TEST-SKU-1', 'description': 'Test Item One (Condition Suffix)', 'quantity': 2, 'unit_cost': 10.50, 'condition': 'New'}, {'sku': 'TEST-SKU-2', 'description': 'Test Item Two', 'quantity': 1, 'unit_cost': 25.00, 'condition': 'Used'}]
    po_specific_notes = "Test payment instructions.\nSecond line."

    sample_order_data_ps = {
        'bigcommerce_order_id': 'PS-5678',
        'order_date': datetime.now(timezone.utc).isoformat(),
        'customer_company': 'Multi-Ship Company',
        'customer_name': 'Multi-Ship Customer',
        'customer_shipping_address_line1': '789 Split Ship Rd',
        'customer_shipping_city': 'Partsburg',
        'customer_shipping_state': 'PS',
        'customer_shipping_zip': '54321',
        'customer_shipping_country': 'USA',
        'customer_shipping_method': 'Standard Ground (UPS Ground)',
        'payment_method': 'Net 30 Terms',
        'customer_notes': "This is a test customer note.\nPlease handle with care.\nThird line of notes."
    }
    sample_items_in_shipment = [
        {'quantity': 1, 'name': 'Widget A - Main Part (Black Font Test)', 'sku': 'WIDGET-A'},
        {'quantity': 2, 'name': 'Bolt Set for Widget A (More Details Here)', 'sku': 'BOLT-SET'}
    ]
    sample_items_shipping_separately = [
        {'quantity': 1, 'name': 'Widget B - Accessory (Ships Later in Grey)', 'sku': 'WIDGET-B'},
        {'quantity': 5, 'name': 'Extra Screws - Backordered (Grey Font Test)', 'sku': 'SCREW-XTRA'}
    ]
    test_logo_gcs_uri = os.getenv("COMPANY_LOGO_GCS_URI")
    if not test_logo_gcs_uri: print("WARN: COMPANY_LOGO_GCS_URI not set in .env for local logo test.")

    print("\nGenerating Sample Purchase Order (Local Test - Mapped Eloquia via Helvetica)...")
    po_pdf_bytes = generate_purchase_order_pdf(
        order_data=sample_order_data_po, supplier_data=sample_supplier_data,
        po_number='TEST-PO-123', po_date=datetime.now(timezone.utc),
        po_items=sample_po_items, payment_terms=sample_supplier_data['payment_terms'],
        payment_instructions=po_specific_notes, logo_gcs_uri=test_logo_gcs_uri
    )
    po_filename = "LOCAL_TEST_purchase_order_mapped_eloquia.pdf"
    with open(po_filename, "wb") as f: f.write(po_pdf_bytes)
    print(f"Sample Purchase Order PDF generated: {po_filename}")

    print("\nGenerating Sample Packing Slip (Local Test - Mapped Eloquia)...")
    packing_slip_pdf_bytes = generate_packing_slip_pdf(
        order_data=sample_order_data_ps,
        items_in_this_shipment=sample_items_in_shipment,
        items_shipping_separately=sample_items_shipping_separately,
        logo_gcs_uri=test_logo_gcs_uri,
        is_g1_onsite_fulfillment=False,
        is_blind_slip=False
    )
    ps_filename = "LOCAL_TEST_packing_slip_mapped_eloquia.pdf"
    with open(ps_filename, "wb") as f: f.write(packing_slip_pdf_bytes)
    print(f"Sample Packing Slip PDF generated: {ps_filename}")

    print("\nGenerating BLIND Sample Packing Slip (Local Test - Mapped Eloquia)...")
    blind_ship_from_details = {
        'name': sample_order_data_ps.get('customer_company', 'Your Shipper Name'),
        'street_1': 'PO Box 1000',
        'city': 'Some City',
        'state': 'XX',
        'zip': '00000',
        'country': 'USA'
    }
    blind_packing_slip_pdf_bytes = generate_packing_slip_pdf(
        order_data=sample_order_data_ps,
        items_in_this_shipment=sample_items_in_shipment,
        items_shipping_separately=sample_items_shipping_separately,
        logo_gcs_uri=None,
        is_g1_onsite_fulfillment=False,
        is_blind_slip=True,
        custom_ship_from_address=blind_ship_from_details
    )
    blind_ps_filename = "LOCAL_TEST_BLIND_packing_slip_mapped_eloquia.pdf"
    with open(blind_ps_filename, "wb") as f: f.write(blind_packing_slip_pdf_bytes)
    print(f"Sample BLIND Packing Slip PDF generated: {blind_ps_filename}")

