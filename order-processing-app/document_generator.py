# document_generator.py
from dotenv import load_dotenv # Add this import
load_dotenv() # Add this line to load the .env file
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
from decimal import Decimal # ADDED THIS IMPORT

# --- FONT REGISTRATION ---
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- For Rotated Text ---
from reportlab.graphics.shapes import String, Drawing, Group # For rotated text
from reportlab.graphics.renderPDF import GraphicsFlowable # To wrap graphics for Platypus

try:
    from svglib.svglib import svg2rlg
    from reportlab.graphics.shapes import Drawing # Drawing is a flowable
    SVGLIB_AVAILABLE = True
    print("DEBUG DOC_GEN: svglib imported successfully.")
except ImportError:
    SVGLIB_AVAILABLE = False
    svg2rlg = None
    Drawing = None # To prevent NameError if not imported
    print("WARN DOC_GEN: svglib library not found. SVG processing will rely on Pillow or fail.")


try:
    # Get the absolute path of the directory where this script is located
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Build a robust path to the 'fonts' directory relative to this file
    FONTS_DIR = os.path.join(_this_dir, 'fonts')

    # Construct the full path to each font file
    eloquia_regular_path = os.path.join(FONTS_DIR, 'eloquia-display-regular-fixed.ttf')
    # If you have a bold version, its path would be defined here too
    # eloquia_bold_path = os.path.join(FONTS_DIR, 'eloquia-display-bold.ttf') 

    # Register the fonts with ReportLab
    pdfmetrics.registerFont(TTFont('EloquiaDisplay-Regular', eloquia_regular_path))
    # pdfmetrics.registerFont(TTFont('EloquiaDisplay-Bold', eloquia_bold_path))
    
    print("DEBUG DOC_GEN: Successfully registered custom Eloquia fonts.")

except Exception as e:
    print(f"ERROR DOC_GEN: Failed to register/map custom Eloquia fonts. PDFs may use a default font. Error: {e}")
    traceback.print_exc()

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
COMPANY_ADDRESS_PACKING_SLIP_HEADER_LINE2 = ""

COMPANY_PHONE = "(877) 418-3246"
COMPANY_FAX = "(866) 921-1032"
COMPANY_EMAIL = "sales@globalonetechnology.com"
COMPANY_WEBSITE = "www.globalonetechnology.com"

def format_currency(value): # Existing function
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        try:
            return f"${float(str(value)):,.2f}"
        except:
             return "$0.00"

def _format_shipping_method_for_display(method_string): # Existing function
    if not method_string or not isinstance(method_string, str):
        return "N/A"
    match = re.search(r'\(([^)]+)\)[^(]*$', method_string)
    if match:
        return match.group(1).strip()
    return method_string.strip()

# NEW HELPER FUNCTION for payment method formatting
def _format_payment_method_for_packing_slip(payment_method_string):
    if not payment_method_string or not isinstance(payment_method_string, str):
        return "N/A"
    
    # Find the first occurrence of '['
    bracket_index = payment_method_string.find('[')
    
    if bracket_index != -1:
        # If '[' is found, take the substring before it and strip whitespace
        return payment_method_string[:bracket_index].strip()
    else:
        # If no '[' is found, return the original string, stripped of whitespace
        return payment_method_string.strip()
    
def get_custom_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(name='Normal_Eloquia', fontName='Helvetica', fontSize=9, leading=11))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Small', parent=styles['Normal_Eloquia'], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Bold', fontName='Helvetica-Bold', fontSize=9, leading=11))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Right', parent=styles['Normal_Eloquia'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Center', parent=styles['Normal_Eloquia'], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Bold_Right', parent=styles['Normal_Eloquia_Bold'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Bold_Center', parent=styles['Normal_Eloquia_Bold'], alignment=TA_CENTER))
    
    styles.add(ParagraphStyle(name='Invoice_Num_Eloquia_Bold_Right', 
                               parent=styles['Normal_Eloquia_Bold_Right'], 
                               fontSize=12, 
                               leading=14))

    # MODIFIED: TOTAL Label size back to normal bold or slightly larger
    styles.add(ParagraphStyle(name='Total_Label_Eloquia_Bold_Right', 
                               parent=styles['Normal_Eloquia_Bold_Right'], 
                               fontSize=10, # Adjusted from 13pt back to 10pt (9pt is base)
                               leading=12))
    # Value can remain larger if desired
    styles.add(ParagraphStyle(name='Total_Value_Eloquia_Bold_Right', 
                               parent=styles['Normal_Eloquia_Bold_Right'], 
                               fontSize=13, 
                               leading=15))

    # NEW: Style for the enlarged "Please send payment..." message
    styles.add(ParagraphStyle(name='Payment_Message_Enlarged_Center',
                               parent=styles['Normal_Eloquia_Center'],
                               fontSize=10, # Approx 15% > 9pt (9 * 1.15 = 10.35)
                               leading=12))

    styles.add(ParagraphStyle(name='H1_Eloquia', fontName='Helvetica-Bold', fontSize=16, leading=18, parent=styles['h1']))
    styles.add(ParagraphStyle(name='H1_Eloquia_Right', parent=styles['H1_Eloquia'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='H2_Eloquia', fontName='Helvetica-Bold', fontSize=14, leading=16, parent=styles['h2'])) # Used for text logo fallback
    styles.add(ParagraphStyle(name='H3_Eloquia', fontName='Helvetica-Bold', fontSize=10, leading=12, parent=styles['h3']))
    
    styles.add(ParagraphStyle(name='ItemDesc_Eloquia', parent=styles['Normal_Eloquia'], fontSize=9, leading=11))
    styles.add(ParagraphStyle(name='FulfillmentNoteStyle_Eloquia', parent=styles['Normal_Eloquia'], fontSize=9, leading=11, textColor=colors.HexColor("#666666")))
    styles.add(ParagraphStyle(name='ItemDesc_ShippingSeparately_Eloquia', parent=styles['ItemDesc_Eloquia'], textColor=colors.HexColor("#777777")))
    styles.add(ParagraphStyle(name='Normal_Eloquia_Center_ShippingSeparately', parent=styles['Normal_Eloquia_Center'], textColor=colors.HexColor("#777777")))
    styles.add(ParagraphStyle(name='CustomerNotesStyle_Eloquia', parent=styles['Normal_Eloquia'], spaceBefore=6, spaceAfter=6, leading=12, leftIndent=0.25*inch, rightIndent=0.25*inch))
    styles.add(ParagraphStyle(name='FooterStyle_Eloquia', fontName='Times-Roman', fontSize=8, leading=10, alignment=TA_CENTER)) # Matched your sample
    styles.add(ParagraphStyle(name='EnvironmentNoteStyle_Eloquia', fontName='Times-Roman', fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#888888"))) # From packing slip

    # Original Helvetica styles from your file (if still needed for PO, otherwise review if Eloquia is primary for all)
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

        if logo_gcs_uri.lower().endswith(".svg") and SVGLIB_AVAILABLE:
            print(f"DEBUG _get_logo_element_from_gcs: Processing {logo_gcs_uri} as SVG with svglib.")
            logo_file_like_object = BytesIO(logo_bytes)
            drawing = svg2rlg(logo_file_like_object) # svg2rlg expects a file path or file-like object
            logo_file_like_object.close() # Close BytesIO object

            if drawing:
                # Scale the drawing
                original_width = drawing.width
                original_height = drawing.height

                if original_width == 0 or original_height == 0: # Should not happen for valid SVGs
                    print(f"WARN _get_logo_element_from_gcs: SVG {logo_gcs_uri} has zero width/height after svg2rlg.")
                    return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Eloquia'])

                scale_factor = desired_logo_width / original_width
                drawing.width = desired_logo_width
                drawing.height = original_height * scale_factor
                drawing.scale(scale_factor, scale_factor) # Scale the drawing contents
                
                # The drawing object itself is a flowable
                return drawing 
            else:
                print(f"WARN _get_logo_element_from_gcs: svg2rlg failed to convert {logo_gcs_uri}.")
                return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Eloquia'])
        else: # Fallback to Pillow for other image types (PNG, JPG) or if SVG but svglib is not available
            if logo_gcs_uri.lower().endswith(".svg") and not SVGLIB_AVAILABLE:
                print(f"WARN _get_logo_element_from_gcs: SVG detected but svglib not available. Attempting with Pillow (may fail).")

            print(f"DEBUG _get_logo_element_from_gcs: Processing {logo_gcs_uri} with Pillow.")

        logo_stream = BytesIO(logo_bytes)
        
        actual_logo_width = desired_logo_width
        actual_logo_height = None
        if PILImage:
            try:
                logo_stream.seek(0)
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
    order_ref_text = ""

    if is_blind_slip:
        logo_element_to_use = Paragraph("", styles['H2_Eloquia'])
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
    else: # Not a blind slip
        logo_element_to_use = _get_logo_element_from_gcs(styles, logo_gcs_uri, desired_logo_width=2.6*inch, is_blind_slip=False)
        company_header_address_text_non_blind = f"{COMPANY_ADDRESS_PACKING_SLIP_HEADER_LINE2}"
        company_address_display_ps_para = Paragraph(escape(company_header_address_text_non_blind).replace('\n', '<br/>'), styles['Normal_Eloquia_Small'])
        if is_g1_onsite_fulfillment:
            packing_slip_title_text = "PACKING SLIP"

        current_date_obj = datetime.now(timezone.utc)
        formatted_current_date = current_date_obj.strftime("%m/%d/%Y")
        bc_order_id_ps_str = str(order_data.get('bigcommerce_order_id', 'N/A'))
        order_ref_text = f"Date: {formatted_current_date}<br/>Order #: {escape(bc_order_id_ps_str)}"

    header_data = [
        [logo_element_to_use, Paragraph(f"<b>{packing_slip_title_text}</b>", styles['H1_Eloquia_Right'])],
        [company_address_display_ps_para, Paragraph(order_ref_text, styles['Normal_Eloquia_Right'])]
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
    if not is_blind_slip:
        raw_payment_method = order_data.get('payment_method', 'N/A')
        formatted_payment_method_display = _format_payment_method_for_packing_slip(raw_payment_method) 
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


    if not is_blind_slip:
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

# --- START OF INVOICE PDF FUNCTION ---
def _draw_invoice_footer(canvas, doc, styles): # Renamed from _draw_paid_invoice_footer
    canvas.saveState()
    page_width = doc.width 
    
    paid_message_text = "This invoice has been paid and is for your records only.<br/>Thank you for your order!"
    p_paid_message = Paragraph(paid_message_text, styles['Normal_Eloquia_Center'])
    
    hr_footer = HRFlowable(width=doc.width, thickness=0.5, color=colors.lightgrey, spaceBefore=3, spaceAfter=3)

    company_footer_lines = [
        f"<b>{COMPANY_NAME}</b>",
        f"Voice: {COMPANY_PHONE} &nbsp;&nbsp;&nbsp;&nbsp; Fax: {COMPANY_FAX}",
        COMPANY_ADDRESS_PACKING_SLIP_FOOTER_LINE1,
        f"Email: {COMPANY_EMAIL} &nbsp;&nbsp;&nbsp;&nbsp; Website: {COMPANY_WEBSITE}"
    ]
    p_company_footer = Paragraph("<br/>".join(company_footer_lines), styles['FooterStyle_Eloquia'])

    # Calculate heights of the elements
    w_comp, h_comp = p_company_footer.wrapOn(canvas, page_width, doc.bottomMargin)
    hr_footer.wrapOn(canvas, page_width, 0) 
    h_hr = hr_footer.height # This includes spaceBefore/After of the HRFlowable itself
    w_paid, h_paid = p_paid_message.wrapOn(canvas, page_width, doc.bottomMargin)

    # Start drawing from a fixed point from the bottom page edge
    current_y = 0.30 * inch # Start company footer details here

    p_company_footer.drawOn(canvas, doc.leftMargin, current_y)
    current_y += h_comp # Move Y position up by the height of the company footer

    # Draw HR line above company footer
    # The HRFlowable's spaceBefore will add space above the company footer
    hr_footer.drawOn(canvas, doc.leftMargin, current_y) 
    current_y += h_hr # Move Y position up by height of HR (which includes its internal spacing)

    # Draw the "This invoice has been paid..." message above the HR line
    # To move this message up by 1/4 inch, we add 0.25 * inch to its current_y position
    # relative to where it would have been drawn.
    # The current_y is now at the top of the HR line.
    # We want to draw the p_paid_message starting 0.25 inch higher than just above the HR line.
    
    # The previous current_y is the bottom of where p_paid_message would start.
    # Let's adjust where p_paid_message is drawn.
    # current_y is currently at the position where the bottom of p_paid_message would align with the top of h_hr.
    # To move it up 1/4 inch, we simply add that to current_y before drawing.

    p_paid_message_y_pos = current_y + (0.25 * inch) # Add 1/4 inch upwards shift

    p_paid_message.drawOn(canvas, doc.leftMargin, p_paid_message_y_pos) 
    
    canvas.restoreState()

# --- NEW FOOTER HELPER FUNCTION for Wire Transfer Invoice ---
def _draw_wire_transfer_invoice_footer(canvas, doc, styles, wire_instructions_included=False):
    canvas.saveState()
    page_width = doc.width 
    
    payment_message_text = "Please send payment using the included payment instructions. Thank you for your order!"
    # Use new enlarged style
    p_payment_message = Paragraph(payment_message_text, styles['Payment_Message_Enlarged_Center']) 
    
    hr_footer = HRFlowable(width=doc.width, thickness=0.5, color=colors.lightgrey, spaceBefore=2, spaceAfter=2)

    company_footer_lines = [
        f"<b>{COMPANY_NAME}</b>",
        f"Voice: {COMPANY_PHONE} &nbsp;&nbsp;&nbsp;&nbsp; Fax: {COMPANY_FAX}",
        COMPANY_ADDRESS_PACKING_SLIP_FOOTER_LINE1,
        f"Email: {COMPANY_EMAIL} &nbsp;&nbsp;&nbsp;&nbsp; Website: {COMPANY_WEBSITE}"
    ]
    p_company_footer = Paragraph("<br/>".join(company_footer_lines), styles['FooterStyle_Eloquia'])

    w_comp, h_comp = p_company_footer.wrapOn(canvas, page_width, doc.bottomMargin)
    hr_footer.wrapOn(canvas, page_width, 0) 
    h_hr = hr_footer.height 
    w_payment_msg, h_payment_msg = p_payment_message.wrapOn(canvas, page_width, doc.bottomMargin)
    
    current_y = 0.30 * inch 
    p_company_footer.drawOn(canvas, doc.leftMargin, current_y)
    current_y += h_comp 

    hr_footer.drawOn(canvas, doc.leftMargin, current_y + hr_footer.spaceBefore) 
    current_y += h_hr 
    
    # Previous adjustment moved it up. Let's ensure it's about 0.25 inches higher than default.
    # The "default" would be current_y. We had + (0.25 * inch)
    # The request is "move up about 1/4 inch" from where it *is now*.
    # If the previous adjustment was already made and found insufficient, we add more.
    # Assuming the base y_pos for message (current_y) is just above the HR.
    # The previous version had: p_payment_message_y_pos = current_y + (0.25 * inch)
    # If that wasn't enough, or if that was removed, let's ensure it's explicitly higher.
    # Let's set it relative to the HR line + desired additional space.
    p_payment_message_y_pos = current_y + (0.25 * inch) # This ensures it's 1/4 inch above the HR line's top boundary

    p_payment_message.drawOn(canvas, doc.leftMargin, p_payment_message_y_pos) 
    
    canvas.restoreState()
# --- END OF _draw_wire_transfer_invoice_footer ---

def generate_wire_transfer_invoice_pdf(order_data, line_items_data, apply_wire_fee=False, logo_gcs_uri=None):
    buffer = BytesIO()
    doc_bottom_margin = 2.1 * inch 
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.5*inch, bottomMargin=doc_bottom_margin)
    styles = get_custom_styles()
    story = []

    # --- 1. Top Header ---
    desired_logo_width_invoice = 1.8 * inch * 1.3 # 30% larger logo
    logo_element = _get_logo_element_from_gcs(styles, logo_gcs_uri, desired_logo_width=desired_logo_width_invoice)
    invoice_title_para = Paragraph("INVOICE", styles['H1_Eloquia_Right']) # Title is "INVOICE"

    top_header_data = [[logo_element, invoice_title_para]]
    top_header_table = Table(top_header_data, colWidths=[doc.width * 0.55, doc.width * 0.45]) 
    top_header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (0,0), (0,0), 'LEFT'),    
        ('ALIGN', (1,0), (1,0), 'RIGHT'), ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 6), 
    ]))
    story.append(top_header_table)
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceBefore=0.05*inch, spaceAfter=0.15*inch))

    # --- 2. Invoice # (larger), Date, Shipping Method (MODIFIED DISPLAY) ---
    invoice_date_str = order_data.get('invoice_date_display', '') # From API
    invoice_num_str = str(order_data.get('bigcommerce_order_id', 'N/A'))
    
    # Shipping Method: If "Value1 [Value2]", display "Value1"
    raw_shipping_method = order_data.get('customer_shipping_method', 'N/A')
    shipping_method_display = _format_payment_method_for_packing_slip(raw_shipping_method) # Re-use this helper for stripping "[...]"

    # Create paragraphs for each line, to be added sequentially
    invoice_num_para = Paragraph(f"Invoice #: {invoice_num_str}", styles['Invoice_Num_Eloquia_Bold_Right']) # Larger style
    date_para = Paragraph(f"Date: {invoice_date_str}", styles['Normal_Eloquia_Right'])
    shipping_method_para = Paragraph(f"Shipping Method: {escape(shipping_method_display)}", styles['Normal_Eloquia_Right'])
    
    story.append(invoice_num_para)
    story.append(date_para)
    story.append(shipping_method_para) # P.O., Payment Method, Due Date removed
    story.append(Spacer(1, 0.2 * inch))

    # --- 3. Addresses (Add customer name) ---
    billing_customer_name_parts = []
    if order_data.get('customer_billing_first_name'): billing_customer_name_parts.append(escape(order_data.get('customer_billing_first_name')))
    if order_data.get('customer_billing_last_name'): billing_customer_name_parts.append(escape(order_data.get('customer_billing_last_name')))
    billing_customer_name = " ".join(billing_customer_name_parts).strip()

    bill_to_parts = []
    if order_data.get('customer_billing_company'): bill_to_parts.append(escape(order_data.get('customer_billing_company')))
    if billing_customer_name: bill_to_parts.append(billing_customer_name) # ADDED CUSTOMER NAME
    bill_to_parts.append(escape(order_data.get('customer_billing_street_1', '')))
    if order_data.get('customer_billing_street_2'): bill_to_parts.append(escape(order_data.get('customer_billing_street_2')))
    bill_to_parts.append(f"{escape(order_data.get('customer_billing_city', ''))}, {escape(order_data.get('customer_billing_state', ''))} {escape(order_data.get('customer_billing_zip', ''))}")
    if order_data.get('customer_billing_country_iso2') and order_data.get('customer_billing_country_iso2').upper() != 'US':
        bill_to_parts.append(escape(order_data.get('customer_billing_country', '')))
    bill_to_text = "<br/>".join(filter(None, bill_to_parts))
    bill_to_para = Paragraph(bill_to_text, styles['Normal_Eloquia'])

    # Shipping Address - Customer Name
    # order_data.customer_name is usually full name from BC shipping.
    shipping_customer_name = escape(order_data.get('customer_name', ''))

    ship_to_parts = []
    if order_data.get('customer_company'): ship_to_parts.append(escape(order_data.get('customer_company'))) # Usually from shipping_addresses[0].company
    if shipping_customer_name: ship_to_parts.append(shipping_customer_name) # ADDED CUSTOMER NAME
    ship_to_parts.append(escape(order_data.get('customer_shipping_address_line1', '')))
    if order_data.get('customer_shipping_address_line2'): ship_to_parts.append(escape(order_data.get('customer_shipping_address_line2')))
    ship_to_parts.append(f"{escape(order_data.get('customer_shipping_city', ''))}, {escape(order_data.get('customer_shipping_state', ''))} {escape(order_data.get('customer_shipping_zip', ''))}")
    if order_data.get('customer_shipping_country_iso2') and order_data.get('customer_shipping_country_iso2').upper() != 'US':
        ship_to_parts.append(escape(order_data.get('customer_shipping_country', '')))
    ship_to_text = "<br/>".join(filter(None, ship_to_parts))
    ship_to_para = Paragraph(ship_to_text, styles['Normal_Eloquia'])
    
    address_data = [
        [Paragraph("<b>Bill To:</b>", styles['H3_Eloquia']), Paragraph("<b>Ship To:</b>", styles['H3_Eloquia'])],
        [bill_to_para, ship_to_para]
    ]
    address_table = Table(address_data, colWidths=[doc.width * 0.5, doc.width * 0.5])
    # ... (address_table style remains same)
    story.append(address_table)
    story.append(Spacer(1, 0.25 * inch)) # Space before items table (NO PAID STAMP HERE)

    # --- 4. Line Items Table (Description changes already made) ---
    # ... (items_table logic as previously updated for pdf_description - no changes here) ...
    current_line_items = list(line_items_data) 
    if apply_wire_fee:
        wire_fee_amount_for_pdf = Decimal("25.00")
        current_line_items.append({
            'pdf_description': 'Bank Wire Transfer Fee', 'quantity': 1,
            'sale_price': wire_fee_amount_for_pdf, 'is_fee': True 
        })
    items_header = [
        Paragraph('<b>Description</b>', styles['Normal_Eloquia_Bold']),
        Paragraph('<b>Qty</b>', styles['Normal_Eloquia_Bold_Center']),
        Paragraph('<b>Each</b>', styles['Normal_Eloquia_Bold_Right']),
        Paragraph('<b>Total</b>', styles['Normal_Eloquia_Bold_Right'])
    ]
    items_table_data = [items_header]
    subtotal = Decimal('0.00')
    for item in current_line_items:
        qty = Decimal(str(item.get('quantity', 0)))
        unit_price = Decimal(str(item.get('sale_price', '0.00')))
        line_total = qty * unit_price
        subtotal += line_total
        desc_text = escape(item.get('pdf_description', item.get('line_item_name', 'N/A')))
        items_table_data.append([
            Paragraph(desc_text, styles['ItemDesc_Eloquia']),
            Paragraph(str(qty), styles['Normal_Eloquia_Center']),
            Paragraph(format_currency(unit_price), styles['Normal_Eloquia_Right']),
            Paragraph(format_currency(line_total), styles['Normal_Eloquia_Right'])
        ])
    available_width_for_table = doc.width 
    desc_col_width = available_width_for_table * 0.60 
    qty_col_width = available_width_for_table * 0.10
    each_col_width = available_width_for_table * 0.15
    total_col_width = available_width_for_table * 0.15
    items_table = Table(items_table_data, colWidths=[desc_col_width, qty_col_width, each_col_width, total_col_width])
    items_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black), ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5), ('LEFTPADDING', (0,1), (0,-1), 2), 
        ('RIGHTPADDING', (0,1), (0,-1), 2),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.05 * inch))

    # --- 5. Financial Summary (TOTAL DUE label size adjusted) ---
    shipping_cost = Decimal(str(order_data.get('bc_shipping_cost_ex_tax', '0.00')))
    sales_tax = Decimal(str(order_data.get('bigcommerce_order_tax', '0.00')))
    grand_total_due = subtotal + shipping_cost + sales_tax

    summary_spacer_col_width = desc_col_width + qty_col_width 
    summary_label_col_width = each_col_width 
    summary_value_col_width = total_col_width 

    summary_data = [
        ['', Paragraph('Subtotal:', styles['Normal_Eloquia_Bold_Right']), Paragraph(format_currency(subtotal), styles['Normal_Eloquia_Right'])],
        ['', Paragraph('Shipping:', styles['Normal_Eloquia_Bold_Right']), Paragraph(format_currency(shipping_cost), styles['Normal_Eloquia_Right'])],
        ['', Paragraph('Sales Tax:', styles['Normal_Eloquia_Bold_Right']), Paragraph(format_currency(sales_tax), styles['Normal_Eloquia_Right'])],
        # Use modified 'Total_Label_Eloquia_Bold_Right' for the label (now smaller)
        # Value style 'Total_Value_Eloquia_Bold_Right' can remain larger if desired or also be adjusted
        ['', Paragraph('TOTAL DUE:', styles['Total_Label_Eloquia_Bold_Right']), Paragraph(f"<b>{format_currency(grand_total_due)}</b>", styles['Total_Value_Eloquia_Bold_Right'])],
    ]
    # ... (summary_table creation and styling as before) ...
    summary_table = Table(summary_data, 
                          colWidths=[summary_spacer_col_width, summary_label_col_width, summary_value_col_width])
    summary_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0), 
        ('BOTTOMPADDING', (0,0), (-1,-1), 2), ('TOPPADDING', (0,0), (-1,-1), 2),
        ('LINEABOVE', (1,3), (2,3), 0.5, colors.black), 
        ('TOPPADDING', (1,3), (2,3), 5), ('BOTTOMPADDING', (1,3), (2,3), 5)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.2 * inch))

    # --- 6. Wire Transfer Instructions (Remains the same) ---
    wire_instructions_text = """
        <b>Wire Transfer Info:</b><br/>
        Bank Name: U.S. Bank NA<br/>
        SWIFT Code: USBKUS44IMT (for international transfers)<br/>
        Routing Transit Number: 104000029<br/>
        Beneficiary Account Number: 105702224939<br/>
        Beneficiary Name: GLOBAL ONE TECHNOLOGY GROUP INC<br/>
        Bank Address:<br/>
        U.S. Bank NA<br/>
        800 NICOLLET MALL<br/>
        BC-MN-H201<br/>
        MINNEAPOLIS, MN 55402
    """
    wire_instructions_para = Paragraph(wire_instructions_text, styles['Normal_Eloquia_Small'])
    instruction_table_data = [[wire_instructions_para]]
    instruction_table = Table(instruction_table_data, colWidths=[doc.width])
    instruction_table.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 10)
    ]))
    story.append(instruction_table)

    # --- Build with fixed footer ---
    draw_footer_partial = partial(_draw_wire_transfer_invoice_footer, styles=styles, wire_instructions_included=True) 
    doc.build(story, onFirstPage=draw_footer_partial, onLaterPages=draw_footer_partial)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
# --- END OF generate_wire_transfer_invoice_pdf FUNCTION ---


def create_rotated_paid_stamp(styles): # styles argument might not be strictly needed if fonts hardcoded
    paid_text_content = "PAID"
    paid_text_font_name = 'Helvetica-Bold' 
    paid_text_size = 40 # Increased for "slightly larger" and no border makes it look smaller
    
    text_width = pdfmetrics.stringWidth(paid_text_content, paid_text_font_name, paid_text_size)
    text_height = paid_text_size 

    # Estimate drawing size (can be fine-tuned)
    # A slightly larger canvas for the rotated text helps prevent clipping
    rotated_width_estimate = (text_width + text_height) * 0.707 # Approximation for diagonal
    drawing_width = rotated_width_estimate + 20 # Add some padding
    drawing_height = rotated_width_estimate + 20

    d = Drawing(drawing_width, drawing_height)

    s = String(0, 0, paid_text_content) 
    s.fontName = paid_text_font_name
    s.fontSize = paid_text_size
    s.fillColor = colors.red
    s.textAnchor = 'middle' 

    g = Group()
    g.add(s)
    
    # Translate group so string's anchor (middle) is at the center of the drawing, then rotate.
    g.translate(drawing_width / 2, drawing_height / 2)
    g.rotate(30) # Positive for counter-clockwise

    d.add(g)
    return GraphicsFlowable(d)


def generate_receipt_pdf(order_data, line_items_data, logo_gcs_uri=None): # Renamed to generate_invoice_pdf if title is "INVOICE"
    buffer = BytesIO()
    # Increased bottom margin for footer (was 1.75, trying 2.0 or 2.1)
    doc_bottom_margin = 2.1 * inch 
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.5*inch, bottomMargin=doc_bottom_margin)
    styles = get_custom_styles()
    story = []

    # --- 1. Top Header (Logo on Left, "INVOICE" on Right) ---
    desired_logo_width_invoice = 1.8 * inch * 1.3 # 30% larger
    logo_element = _get_logo_element_from_gcs(styles, logo_gcs_uri, desired_logo_width=desired_logo_width_invoice)
    
    # Changed "PAID INVOICE" to "INVOICE"
    invoice_title_para = Paragraph("INVOICE", styles['H1_Eloquia_Right'])

    top_header_data = [[logo_element, invoice_title_para]]
    top_header_table = Table(top_header_data, colWidths=[doc.width * 0.55, doc.width * 0.45]) 
    top_header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), 
        ('ALIGN', (0,0), (0,0), 'LEFT'),    
        ('ALIGN', (1,0), (1,0), 'RIGHT'),   
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6), 
    ]))
    story.append(top_header_table)
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceBefore=0.05*inch, spaceAfter=0.15*inch))

    # --- 2. Invoice # (larger, above Date), Date, Shipping & Payment Method (All Right Justified) ---
    invoice_date_str = order_data.get('processed_date_display', datetime.now(timezone.utc).strftime("%m/%d/%Y"))
    invoice_num_str = str(order_data.get('bigcommerce_order_id', 'N/A'))
    shipping_method_display = _format_shipping_method_for_display(order_data.get('customer_shipping_method', 'N/A'))
    payment_method_display = _format_payment_method_for_packing_slip(order_data.get('payment_method', 'N/A'))

    invoice_num_para = Paragraph(f"Order #: {invoice_num_str}", styles['Invoice_Num_Eloquia_Bold_Right']) # Uses new larger style
    date_para = Paragraph(f"Date: {invoice_date_str}", styles['Normal_Eloquia_Right'])
    shipping_method_para = Paragraph(f"Shipping Method: {escape(shipping_method_display)}", styles['Normal_Eloquia_Right'])
    payment_method_para = Paragraph(f"Payment Method: {escape(payment_method_display)}", styles['Normal_Eloquia_Right'])
    
    story.append(invoice_num_para)
    story.append(date_para)
    story.append(shipping_method_para)
    story.append(payment_method_para)
    story.append(Spacer(1, 0.2 * inch))

    # --- 3. Addresses & Centered Rotated PAID Stamp ---
    bill_to_para = Paragraph( 
        "<br/>".join(filter(None, [
            escape(order_data.get('customer_billing_company', '') or order_data.get('customer_billing_first_name', '') + ' ' + order_data.get('customer_billing_last_name', '')),
            escape(order_data.get('customer_billing_street_1', '')),
            order_data.get('customer_billing_street_2') and escape(order_data.get('customer_billing_street_2')),
            f"{escape(order_data.get('customer_billing_city', ''))}, {escape(order_data.get('customer_billing_state', ''))} {escape(order_data.get('customer_billing_zip', ''))}",
            (order_data.get('customer_billing_country_iso2') and order_data.get('customer_billing_country_iso2').upper() != 'US') and escape(order_data.get('customer_billing_country', ''))
        ])), styles['Normal_Eloquia'])

    ship_to_para = Paragraph( 
        "<br/>".join(filter(None, [
            escape(order_data.get('customer_company', '') or order_data.get('customer_name', '')),
            escape(order_data.get('customer_shipping_address_line1', '')),
            order_data.get('customer_shipping_address_line2') and escape(order_data.get('customer_shipping_address_line2')),
            f"{escape(order_data.get('customer_shipping_city', ''))}, {escape(order_data.get('customer_shipping_state', ''))} {escape(order_data.get('customer_shipping_zip', ''))}",
            (order_data.get('customer_shipping_country_iso2') and order_data.get('customer_shipping_country_iso2').upper() != 'US') and escape(order_data.get('customer_shipping_country', ''))
        ])), styles['Normal_Eloquia'])
    
    address_data = [
        [Paragraph("<b>Bill To:</b>", styles['H3_Eloquia']), Paragraph("<b>Ship To:</b>", styles['H3_Eloquia'])],
        [bill_to_para, ship_to_para]
    ]
    address_table = Table(address_data, colWidths=[doc.width * 0.5, doc.width * 0.5])
    address_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(address_table)
    story.append(Spacer(1, 0.05 * inch)) 
    
    rotated_paid_stamp = create_rotated_paid_stamp(styles) 
    paid_stamp_table_data = [[rotated_paid_stamp]]
    paid_stamp_table = Table(paid_stamp_table_data, colWidths=[doc.width])
    paid_stamp_table.setStyle(TableStyle([('ALIGN', (0,0), (0,0), 'CENTER')]))
    story.append(paid_stamp_table)
    story.append(Spacer(1, 0.05 * inch))

    # --- 4. Line Items Table (Full Width, Uses pdf_description from orders.py) ---
    items_header = [
        Paragraph('', styles['Normal_Eloquia_Bold']),
        Paragraph('<b>Qty</b>', styles['Normal_Eloquia_Bold_Center']),
        Paragraph('<b>Each</b>', styles['Normal_Eloquia_Bold_Right']),
        Paragraph('<b>Total</b>', styles['Normal_Eloquia_Bold_Right'])
    ]
    items_table_data = [items_header]
    subtotal = Decimal('0.00')

    for item in line_items_data:
        qty = Decimal(str(item.get('quantity', 0)))
        unit_price = Decimal(str(item.get('sale_price', '0.00')))
        line_total = qty * unit_price
        subtotal += line_total
        desc_text = escape(item.get('pdf_description', item.get('line_item_name', 'N/A')))
        items_table_data.append([
            Paragraph(desc_text, styles['ItemDesc_Eloquia']),
            Paragraph(str(qty), styles['Normal_Eloquia_Center']),
            Paragraph(format_currency(unit_price), styles['Normal_Eloquia_Right']),
            Paragraph(format_currency(line_total), styles['Normal_Eloquia_Right'])
        ])
    
    available_width_for_table = doc.width 
    desc_col_width = available_width_for_table * 0.60 
    qty_col_width = available_width_for_table * 0.10
    each_col_width = available_width_for_table * 0.15
    total_col_width = available_width_for_table * 0.15
    
    items_table = Table(items_table_data, colWidths=[desc_col_width, qty_col_width, each_col_width, total_col_width])
    items_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black), ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5), ('LEFTPADDING', (0,1), (0,-1), 2), 
        ('RIGHTPADDING', (0,1), (0,-1), 2),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.05 * inch))

    # --- 5. Financial Summary (TOTAL line emphasized, labels aligned with "Each" column) ---
    shipping_cost = Decimal(str(order_data.get('bc_shipping_cost_ex_tax', '0.00')))
    sales_tax = Decimal(str(order_data.get('bigcommerce_order_tax', '0.00')))
    grand_total = Decimal(str(order_data.get('total_sale_price', '0.00')))
    
    summary_spacer_col_width = desc_col_width + qty_col_width 
    summary_label_col_width = each_col_width 
    summary_value_col_width = total_col_width 

    summary_data = [
        ['', Paragraph('Subtotal:', styles['Normal_Eloquia_Bold_Right']), Paragraph(format_currency(subtotal), styles['Normal_Eloquia_Right'])],
        ['', Paragraph('Shipping:', styles['Normal_Eloquia_Bold_Right']), Paragraph(format_currency(shipping_cost), styles['Normal_Eloquia_Right'])],
        ['', Paragraph('Sales Tax:', styles['Normal_Eloquia_Bold_Right']), Paragraph(format_currency(sales_tax), styles['Normal_Eloquia_Right'])],
        ['', Paragraph('TOTAL:', styles['Total_Label_Eloquia_Bold_Right']), Paragraph(f"<b>{format_currency(grand_total)}</b>", styles['Total_Value_Eloquia_Bold_Right'])],
    ]
    
    summary_table = Table(summary_data, 
                          colWidths=[summary_spacer_col_width, summary_label_col_width, summary_value_col_width])
    summary_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0), 
        ('RIGHTPADDING', (0,0), (-1,-1), 0), 
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('LINEABOVE', (1,3), (2,3), 0.5, colors.black), 
        ('TOPPADDING', (1,3), (2,3), 5), 
        ('BOTTOMPADDING', (1,3), (2,3), 5)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.2 * inch))

    # --- Build with fixed footer ---
    # Ensure _draw_invoice_footer is used here (was _draw_paid_invoice_footer)
    draw_footer_partial = partial(_draw_invoice_footer, styles=styles) 
    doc.build(story, onFirstPage=draw_footer_partial, onLaterPages=draw_footer_partial)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
# --- END OF generate_receipt_pdf FUNCTION ---



if __name__ == '__main__':
    print("Running document_generator.py in local test mode.")
    print("NOTE: Logo will be text unless GCS is configured and test_logo_gcs_uri is set.")

    test_logo_gcs_uri = os.getenv("COMPANY_LOGO_GCS_URI")
    if not test_logo_gcs_uri: 
        print("WARN (local test): COMPANY_LOGO_GCS_URI environment variable not set. Logo will be company name text or fallbacks.")

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

    print("\nTesting Payment Method Formatting:")
    test_payments = [
        "Net 30 Terms [with credit approval]",
        "Credit Card",
        "PayPal [Transaction ID: XYZ123]",
        "Net 15 [Early Pay Discount]",
        "Wire Transfer"
    ]
    for tp in test_payments:
        print(f"Original: '{tp}' -> Formatted: '{_format_payment_method_for_packing_slip(tp)}'")

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

    print("\nGenerating Sample Packing Slip (Local Test - Mapped Eloquia - Original PM)...")
    packing_slip_pdf_bytes_orig_pm = generate_packing_slip_pdf(
        order_data=sample_order_data_ps, 
        items_in_this_shipment=sample_items_in_shipment,
        items_shipping_separately=sample_items_shipping_separately,
        logo_gcs_uri=test_logo_gcs_uri,
        is_g1_onsite_fulfillment=False,
        is_blind_slip=False
    )
    ps_filename_orig_pm = "LOCAL_TEST_packing_slip_mapped_eloquia_orig_pm.pdf"
    with open(ps_filename_orig_pm, "wb") as f: f.write(packing_slip_pdf_bytes_orig_pm)
    print(f"Sample Packing Slip PDF generated: {ps_filename_orig_pm}")

    sample_order_data_ps_copy = sample_order_data_ps.copy() # Create a copy to modify payment_method
    sample_order_data_ps_copy['payment_method'] = "Net 30 Terms [with credit approval]" 
    print("\nGenerating Sample Packing Slip (Local Test - With new Payment Method Formatting)...")
    packing_slip_pdf_bytes_new_pm = generate_packing_slip_pdf(
        order_data=sample_order_data_ps_copy,
        items_in_this_shipment=sample_items_in_shipment,
        items_shipping_separately=sample_items_shipping_separately,
        logo_gcs_uri=test_logo_gcs_uri,
        is_g1_onsite_fulfillment=False,
        is_blind_slip=False
    )
    ps_filename_new_pm = "LOCAL_TEST_packing_slip_new_payment_format.pdf"
    with open(ps_filename_new_pm, "wb") as f: f.write(packing_slip_pdf_bytes_new_pm)
    print(f"Sample Packing Slip PDF generated with new payment format: {ps_filename_new_pm}")

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

    # --- Test for PAID INVOICE (Receipt) ---
    print("\nGenerating Sample PAID INVOICE PDF (Local Test)...")
    sample_order_data_receipt = {
        'bigcommerce_order_id': '106157639', # [cite: 2]
        'processed_date_display': '06/02/2025', # [cite: 2]
        'customer_billing_company': 'BlueSouth', # [cite: 3]
        'customer_billing_first_name': 'Federico',
        'customer_billing_last_name': 'Perez',
        'customer_billing_street_1': '710 W Hallandale Beach Blvd', # [cite: 3]
        'customer_billing_street_2': 'Suite 103', # [cite: 3]
        'customer_billing_city': 'Hallandale Beach', # [cite: 3]
        'customer_billing_state': 'FL', # [cite: 3]
        'customer_billing_zip': '33009', # [cite: 3]
        'customer_billing_country_iso2': 'US',
        'customer_billing_country': 'United States',
        'customer_company': 'BlueSouth', 
        'customer_name': 'Federico Perez Sabater', # [cite: 3]
        'customer_shipping_address_line1': '87 lefferts lane', # [cite: 3]
        'customer_shipping_address_line2': '',
        'customer_shipping_city': 'clark', # [cite: 3]
        'customer_shipping_state': 'NJ', # [cite: 3]
        'customer_shipping_zip': '07066', # [cite: 3]
        'customer_shipping_country_iso2': 'US',
        'customer_shipping_country': 'United States',
        'bc_shipping_cost_ex_tax': '0.00', 
        'bigcommerce_order_tax': '10.53', # [cite: 4]
        'total_sale_price': '169.53', # [cite: 4]
        'customer_po_number': '', # [cite: 5]
        'customer_shipping_method': 'UPS', # [cite: 5]
        'payment_method': 'Credit Card (Processed Online)', 
    }
    sample_line_items_receipt = [
        {
            'name': 'HPE Ethernet 10Gb 2-port 562SFP+ Adapter', # [cite: 4]
            'original_sku': '727055-B21', # [cite: 4]
            'hpe_option_pn': '727055-B21', # Included for more detailed description
            'spare_part_pn': '790316-001', # Included for more detailed description
            'quantity': 1, # [cite: 4]
            'sale_price': '159.00' # [cite: 4]
        }
    ]
    try:
        receipt_pdf_bytes = generate_receipt_pdf(
            order_data=sample_order_data_receipt,
            line_items_data=sample_line_items_receipt,
            logo_gcs_uri=test_logo_gcs_uri 
        )
        receipt_filename = "LOCAL_TEST_Paid_Invoice.pdf"
        with open(receipt_filename, "wb") as f:
            f.write(receipt_pdf_bytes)
        print(f"Sample PAID INVOICE PDF generated: {receipt_filename}")
    except Exception as e_receipt:
        print(f"ERROR generating Paid Invoice PDF: {e_receipt}")
        traceback.print_exc()

    print("\n--- Document generator local tests complete. ---")