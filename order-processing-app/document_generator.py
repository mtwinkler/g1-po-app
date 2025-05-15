# document_generator.py
from datetime import datetime, timezone
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepInFrame, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from io import BytesIO # To generate PDF in memory and handle image data
import os
import traceback # For detailed error logging
import re # For regex in shipping method formatting

# --- Pillow Import ---
try:
    from PIL import Image as PILImage
    print("DEBUG DOC_GEN: Pillow library imported successfully.")
except ImportError:
    print("ERROR DOC_GEN: Pillow library (PIL) not found. Image processing will fail. Please install it (`pip install Pillow`).")
    PILImage = None
# --- End Pillow Import ---

# --- GCS Import and Client Initialization ---
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
# --- End GCS Initialization ---


# --- Global Company Details (Update as needed) ---
COMPANY_NAME = "GLOBAL ONE TECHNOLOGY"
COMPANY_ADDRESS_PO_HEADER = "4916 S 184th Plaza - Omaha, NE 68135"
COMPANY_ADDRESS_PACKING_SLIP_FOOTER_LINE1 = "4916 S 184th Plaza - Omaha, NE 68135" # Made consistent or can be empty
COMPANY_PHONE = "(877) 418-3246"
COMPANY_FAX = "(866) 921-1032"
COMPANY_EMAIL = "sales@globalonetechnology.com"
COMPANY_WEBSITE = "www.globalonetechnology.com"

# --- Helper function to format currency ---
def format_currency(value):
    try:
        # Ensure value is floatable before formatting
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        try: # Try converting from potential Decimal
            return f"${float(str(value)):,.2f}"
        except:
             return "$0.00"


# --- Helper function to format shipping method for display ---
def _format_shipping_method_for_display(method_string):
    if not method_string or not isinstance(method_string, str):
        return "N/A"
    match = re.search(r'\(([^)]+)\)[^(]*$', method_string)
    if match:
        return match.group(1).strip()
    return method_string.strip()

# --- Custom Styles (Comprehensive Version) ---
def get_custom_styles():
    styles = getSampleStyleSheet()
    
    # Base styles
    styles.add(ParagraphStyle(name='Normal_Helvetica', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=11)) # Default size adjusted slightly
    styles.add(ParagraphStyle(name='Normal_Helvetica_Small', parent=styles['Normal_Helvetica'], fontSize=8, leading=10))
    
    # Bold variations
    styles.add(ParagraphStyle(name='Normal_Helvetica_Bold', parent=styles['Normal_Helvetica'], fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Semibold', parent=styles['Normal_Helvetica'], fontName='Helvetica-Bold', fontSize=9, leading=11)) 

    # Alignment variations
    styles.add(ParagraphStyle(name='Normal_Helvetica_Right', parent=styles['Normal_Helvetica'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Center', parent=styles['Normal_Helvetica'], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Bold_Right', parent=styles['Normal_Helvetica_Bold'], alignment=TA_RIGHT)) # Ensured this is present
    styles.add(ParagraphStyle(name='Normal_Helvetica_Bold_Center', parent=styles['Normal_Helvetica_Bold'], alignment=TA_CENTER))

    # Heading styles
    styles.add(ParagraphStyle(name='H1_Helvetica', parent=styles['h1'], fontName='Helvetica-Bold', fontSize=16, leading=18))
    styles.add(ParagraphStyle(name='H1_Helvetica_Right', parent=styles['H1_Helvetica'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='H2_Helvetica', parent=styles['h2'], fontName='Helvetica-Bold', fontSize=14, leading=16))
    styles.add(ParagraphStyle(name='H3_Helvetica', parent=styles['h3'], fontName='Helvetica-Bold', fontSize=10, leading=12))

    # Item description styles
    styles.add(ParagraphStyle(name='ItemDesc', parent=styles['Normal_Helvetica'], fontSize=9, leading=11)) # Consistent with Normal_Helvetica
    styles.add(ParagraphStyle(name='ItemDescSmall', parent=styles['Normal_Helvetica_Small'])) # Based on smaller helvetica
    
    # Specific use styles
    styles.add(ParagraphStyle(name='FulfillmentNoteStyle', parent=styles['Normal_Helvetica'], fontSize=9, leading=11, textColor=colors.HexColor("#666666")))
    styles.add(ParagraphStyle(name='FooterStyle', parent=styles['Normal_Helvetica_Small'], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='EnvironmentNoteStyle', parent=styles['Normal_Helvetica_Small'], alignment=TA_CENTER, textColor=colors.HexColor("#888888")))
    
    # --- STYLES for items shipping separately (from previous update) ---
    styles.add(ParagraphStyle(name='ItemDesc_ShippingSeparately', parent=styles['ItemDesc'], textColor=colors.HexColor("#777777"))) 
    styles.add(ParagraphStyle(name='Normal_Helvetica_Center_ShippingSeparately', parent=styles['Normal_Helvetica_Center'], textColor=colors.HexColor("#777777")))

    return styles

# --- Function to create logo element from GCS URI ---
def _get_logo_element_from_gcs(styles, logo_gcs_uri=None, desired_logo_width=1.5*inch):
    if not logo_gcs_uri:
        print("WARN _get_logo_element_from_gcs: No logo_gcs_uri provided. Using company name text.")
        return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Helvetica'])
    if not storage_client:
        print("WARN _get_logo_element_from_gcs: GCS storage client not available. Using company name text.")
        return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Helvetica'])
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
        actual_logo_height = None # Will be calculated
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
                return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Helvetica']) 
        else: 
            logo_stream.seek(0)
            actual_logo_height = 0.75 * inch # Default height if Pillow not available
        
        logo = Image(logo_stream, width=actual_logo_width, height=actual_logo_height)
        if not logo.imageWidth or not logo.imageHeight or logo.imageWidth == 0 or logo.imageHeight == 0:
             # This might happen if the image format is not directly supported by ReportLab without Pillow's help for sizing
            print(f"WARN _get_logo_element_from_gcs: ReportLab Image dimensions seem invalid for '{logo_gcs_uri}'. Attempting fallback render.")
            # Fallback to letting ReportLab try to size it with kind='bound' might be an option, or error out
            # For now, let's just use the company name text as a more robust fallback.
            raise ValueError("ReportLab image dimensions invalid after Pillow processing or Pillow unavailable.")

        return logo
    except Exception as e:
        print(f"ERROR _get_logo_element_from_gcs: Failed to load logo: {e}"); traceback.print_exc()
        if logo_stream and not logo_stream.closed: logo_stream.close()
        return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Helvetica'])


# --- Function to Generate Purchase Order PDF (MODIFIED) ---
def generate_purchase_order_pdf(order_data, supplier_data, po_number, po_date, po_items, 
                                payment_terms, payment_instructions, logo_gcs_uri=None,
                                is_partial_fulfillment=False): # <-- NEW ARGUMENT
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=0.75*inch, rightMargin=0.75*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = get_custom_styles() # Ensure this function is complete with all needed styles
    story = []

    logo_element = _get_logo_element_from_gcs(styles, logo_gcs_uri, desired_logo_width=2*inch)

    formatted_po_date = f"{po_date.month}/{po_date.day}/{po_date.year}"
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
        [Paragraph(f"{supplier_data.get('name', 'N/A')}<br/>"
                   f"{supplier_data.get('address_line1', '')}<br/>"
                   f"{supplier_data.get('address_line2', '') or ''}<br/>"
                   f"{supplier_data.get('city', '')}, {supplier_data.get('state', '')} {supplier_data.get('zip', '')}<br/>"
                   f"{supplier_data.get('country', '')}", styles['Normal_Helvetica']),
         Paragraph("PLEASE BLIND DROP SHIP<br/>USING ATTACHED LABEL<br/>AND PACKING SLIP", styles['Normal_Helvetica'])]
    ]
    vendor_ship_to_table = Table(vendor_ship_to_content, colWidths=[3.5*inch, 3.5*inch])
    vendor_ship_to_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(vendor_ship_to_table); story.append(Spacer(1, 0.25 * inch))

    items_header = [
        Paragraph('<b>Item</b>', styles['Normal_Helvetica_Bold']), 
        Paragraph('<b>Qty</b>', styles['Normal_Helvetica_Bold_Center']),
        Paragraph('<b>Rate</b>', styles['Normal_Helvetica_Bold_Right']),
        Paragraph('<b>Amount</b>', styles['Normal_Helvetica_Bold_Right'])
    ]
    items_table_data = [items_header]
    total_po_amount = 0
    for item in po_items:
        item_amount = float(item.get('quantity', 0)) * float(item.get('unit_cost', 0.00))
        total_po_amount += item_amount
        description_text = f"{item.get('description', 'N/A')}"
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
        notes_and_total_data.append([Paragraph(payment_instructions.replace('\n', '<br/>'), styles['ItemDesc']), '', '', ''])
    
    # --- MODIFIED FULFILLMENT NOTE ---
    if order_data.get('bigcommerce_order_id'):
        fulfillment_text_prefix = "Partial fulfillment of G1 Order #" if is_partial_fulfillment else "Fulfillment of G1 Order #"
        notes_and_total_data.append([
            Paragraph(f"{fulfillment_text_prefix}{order_data.get('bigcommerce_order_id', 'N/A')}", styles['FulfillmentNoteStyle']), 
            '', '', ''
        ])
    # --- END MODIFIED FULFILLMENT NOTE ---
    
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

# --- Packing Slip Footer Function ---
def _draw_packing_slip_footer(canvas, doc):
    canvas.saveState()
    styles = get_custom_styles()
    available_width = doc.width; left_margin = doc.leftMargin
    current_y = 0.3 * inch 
    env_text = """In an effort to minimize our footprint on the environment,<br/>Global One Technology uses clean, recycled packaging materials."""
    p_env = Paragraph(env_text, styles['EnvironmentNoteStyle'])
    p_env.wrapOn(canvas, available_width, doc.bottomMargin); p_env.drawOn(canvas, left_margin, current_y)
    current_y += p_env.height + 0.1 * inch 
    
    company_footer_text = f"""<font name="Helvetica-Bold" size="9">{COMPANY_NAME}</font><br/><font name="Helvetica" size="8">
    Voice: {COMPANY_PHONE} Fax: {COMPANY_FAX}<br/>{COMPANY_ADDRESS_PACKING_SLIP_FOOTER_LINE1}<br/>
    Email: {COMPANY_EMAIL} Website: {COMPANY_WEBSITE}</font>"""
    p_company = Paragraph(company_footer_text, styles['FooterStyle'])
    p_company.wrapOn(canvas, available_width, doc.bottomMargin); p_company.drawOn(canvas, left_margin, current_y)
    current_y += p_company.height + 0.15 * inch

    faq_text = """<font name="Helvetica" size="9"><b>FAQ's:</b></font><br/><font name="Helvetica" size="8">
    1. We ordered the wrong part or have a defective item. How would we arrange a return?<br/>
    Please visit http://www.globalonetechnology.com/returns for information on how to return an item.<br/><br/>
    2. How can I get a copy of our invoice for bookkeeping/accounting?<br/>
    Please email sales@globalonetechnology.com to request a copy of your invoice.</font>"""
    p_faq = Paragraph(faq_text, styles['Normal_Helvetica_Small'])
    p_faq.wrapOn(canvas, available_width, doc.bottomMargin); p_faq.drawOn(canvas, left_margin, current_y)
    canvas.restoreState()


# --- MODIFIED Function to Generate Packing Slip PDF ---
def generate_packing_slip_pdf(order_data, items_in_this_shipment, items_shipping_separately, 
                              logo_gcs_uri=None, po_number_for_slip=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.5*inch, bottomMargin=1.9*inch) 
    styles = get_custom_styles()
    story = []

    logo_element = _get_logo_element_from_gcs(styles, logo_gcs_uri, desired_logo_width=2*inch)

    current_date = datetime.now(timezone.utc)
    formatted_current_date = f"{current_date.month}/{current_date.day}/{current_date.year}"
    
    order_ref_text = f"Date: {formatted_current_date}<br/>Order #: {order_data.get('bigcommerce_order_id', 'N/A')}"
    if po_number_for_slip:
        order_ref_text += f"<br/>Ref PO #: {po_number_for_slip}"

    header_data = [
        [logo_element, Paragraph("<b>PACKING SLIP</b>", styles['H1_Helvetica_Right'])],
        [Paragraph(COMPANY_ADDRESS_PO_HEADER, styles['Normal_Helvetica_Small']), # Consistent with PO header style
         Paragraph(order_ref_text, styles['Normal_Helvetica_Right'])]
    ]
    header_table = Table(header_data, colWidths=[4*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (0,0), 6),
        ('SPAN', (0,0), (0,0)),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceBefore=0.05*inch, spaceAfter=0.1*inch))

    ship_to_address_text = (
        f"{order_data.get('customer_name', 'N/A')}<br/>"
        f"{order_data.get('customer_shipping_address_line1', '')}<br/>"
        f"{order_data.get('customer_shipping_address_line2', '') or ''}<br/>"
        f"{order_data.get('customer_shipping_city', '')}, {order_data.get('customer_shipping_state', '')} {order_data.get('customer_shipping_zip', '')}<br/>"
        f"{order_data.get('customer_shipping_country', '')}"
    )
    ship_to_para = Paragraph(ship_to_address_text, styles['Normal_Helvetica'])
    formatted_shipping_method = _format_shipping_method_for_display(order_data.get('customer_shipping_method', 'N/A'))
    payment_method_text = order_data.get('payment_method', 'N/A')
    right_column_content = [
        Paragraph(f"<b>Shipping Method:</b> {formatted_shipping_method}", styles['Normal_Helvetica_Right']),
        Spacer(1, 0.05 * inch),
        Paragraph(f"<b>Payment Method:</b> {payment_method_text}", styles['Normal_Helvetica_Right'])
    ]
    shipping_details_data = [
        [Paragraph("<b>Ship To:</b>", styles['H3_Helvetica']), ""], 
        [ship_to_para, KeepInFrame(3.5*inch, 1*inch, right_column_content)] # Use KeepInFrame for better layout control
    ]
    shipping_details_table = Table(shipping_details_data, colWidths=[3.5*inch, 3.5*inch])
    shipping_details_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('SPAN', (1,0), (1,0)), 
    ]))
    story.append(shipping_details_table)
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("<b>IN THIS SHIPMENT:</b>", styles['H3_Helvetica']))
    story.append(Spacer(1, 0.05 * inch))
    
    items_header_shipped = [
        Paragraph('<b>Qty</b>', styles['Normal_Helvetica_Bold_Center']),
        Paragraph('<b>Item</b>', styles['Normal_Helvetica_Bold'])
    ]
    items_table_data_shipped = [items_header_shipped]
    if items_in_this_shipment:
        for item in items_in_this_shipment:
            items_table_data_shipped.append([
                Paragraph(str(item.get('quantity', 0)), styles['Normal_Helvetica_Center']),
                Paragraph(item.get('name', item.get('description', 'N/A')), styles['ItemDesc'])
            ])
    else: 
        items_table_data_shipped.append([
            Paragraph("<i>(No items in this specific shipment segment)</i>", styles['ItemDesc'], colSpan=2)
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
    if not items_in_this_shipment: # Add SPAN if placeholder text is used
        style_cmds_shipped.append(('SPAN', (0, len(items_table_data_shipped)-1), (1, len(items_table_data_shipped)-1)))
        style_cmds_shipped.append(('ALIGN', (0, len(items_table_data_shipped)-1), (0, len(items_table_data_shipped)-1), 'CENTER')) # Center placeholder
        
    items_table_shipped.setStyle(TableStyle(style_cmds_shipped))
    story.append(items_table_shipped)
    story.append(Spacer(1, 0.2 * inch))

    if items_shipping_separately:
        story.append(Paragraph("<b>SHIPPING SEPARATELY:</b>", styles['H3_Helvetica']))
        story.append(Spacer(1, 0.05 * inch))
        
        items_header_separate = [
            Paragraph('<b>Qty</b>', styles['Normal_Helvetica_Bold_Center']),
            Paragraph('<b>Item</b>', styles['Normal_Helvetica_Bold'])
        ]
        items_table_data_separate = [items_header_separate]
        for item in items_shipping_separately:
            items_table_data_separate.append([
                Paragraph(str(item.get('quantity', 0)), styles['Normal_Helvetica_Center_ShippingSeparately']), 
                Paragraph(item.get('name', item.get('description', 'N/A')), styles['ItemDesc_ShippingSeparately']) 
            ])
        
        items_table_separate = Table(items_table_data_separate, colWidths=[0.75*inch, 6.25*inch])
        items_table_separate.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.darkgrey), 
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (0,0), (0,0), 'CENTER'), ('ALIGN', (1,0), (1,0), 'LEFT'),
            ('ALIGN', (0,1), (0,-1), 'CENTER'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4), ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f0f0f0")), 
        ]))
        story.append(items_table_separate)

    doc.build(story, onFirstPage=_draw_packing_slip_footer, onLaterPages=_draw_packing_slip_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

# --- Example usage (for testing the functions independently) ---
if __name__ == '__main__':
    print("Running document_generator.py in local test mode.")
    print("NOTE: Logo will be text unless GCS is configured and test_logo_gcs_uri is set.")

    sample_order_data_po = { 'bigcommerce_order_id': '106157456' }
    sample_supplier_data = { 'name': 'Test Supplier Inc.', 'address_line1': '123 Test St', 'city': 'Testville', 'state': 'TS', 'zip': '12345', 'country': 'USA', 'payment_terms': 'Net 30' }
    sample_po_items = [{'sku': 'TEST-SKU-1', 'description': 'Test Item One (Condition Suffix)', 'quantity': 2, 'unit_cost': 10.50, 'condition': 'New'}, {'sku': 'TEST-SKU-2', 'description': 'Test Item Two', 'quantity': 1, 'unit_cost': 25.00, 'condition': 'Used'}]
    po_specific_notes = "Test payment instructions.\nSecond line."
    
    sample_order_data_ps = { 
        'bigcommerce_order_id': 'ORDER-MULTI-001',
        'customer_name': 'Multi-Ship Customer',
        'customer_shipping_address_line1': '789 Split Ship Rd',
        'customer_shipping_city': 'Partsburg',
        'customer_shipping_state': 'PS',
        'customer_shipping_zip': '54321',
        'customer_shipping_country': 'USA',
        'customer_shipping_method': 'Standard Ground (UPS Ground)', # Example with parentheses
        'payment_method': 'Net 30 Terms'
    }
    sample_items_in_shipment = [
        {'quantity': 1, 'name': 'Widget A - Main Part (Black Font Test)', 'sku': 'WIDGET-A'},
        {'quantity': 2, 'name': 'Bolt Set for Widget A (More Details Here)', 'sku': 'BOLT-SET'}
    ]
    sample_items_shipping_separately = [
        {'quantity': 1, 'name': 'Widget B - Accessory (Ships Later in Grey)', 'sku': 'WIDGET-B'},
        {'quantity': 5, 'name': 'Extra Screws - Backordered (Grey Font Test)', 'sku': 'SCREW-XTRA'}
    ]
    test_logo_gcs_uri = os.getenv("COMPANY_LOGO_GCS_URI") # Use env var for testing if set
    if not test_logo_gcs_uri: print("WARN: COMPANY_LOGO_GCS_URI not set in .env for local logo test.")
    
    test_po_ref_for_slip = "PO-MULTI-123A" 

    print("\nGenerating Sample Purchase Order (Local Test)...")
    po_pdf_bytes = generate_purchase_order_pdf(
        order_data=sample_order_data_po, supplier_data=sample_supplier_data,
        po_number='TEST-PO-123', po_date=datetime.now(timezone.utc),
        po_items=sample_po_items, payment_terms=sample_supplier_data['payment_terms'],
        payment_instructions=po_specific_notes, logo_gcs_uri=test_logo_gcs_uri
    )
    po_filename = "LOCAL_TEST_purchase_order.pdf"
    with open(po_filename, "wb") as f: f.write(po_pdf_bytes)
    print(f"Sample Purchase Order PDF generated: {po_filename}")

    print("\nGenerating Sample Packing Slip (Local Test with new structure)...")
    packing_slip_pdf_bytes = generate_packing_slip_pdf(
        order_data=sample_order_data_ps,
        items_in_this_shipment=sample_items_in_shipment,
        items_shipping_separately=sample_items_shipping_separately,
        logo_gcs_uri=test_logo_gcs_uri,
        po_number_for_slip=test_po_ref_for_slip
    )
    ps_filename = "LOCAL_TEST_packing_slip_multi.pdf" 
    with open(ps_filename, "wb") as f: f.write(packing_slip_pdf_bytes)
    print(f"Sample Packing Slip PDF generated: {ps_filename}")

    print("\nTesting Packing Slip with EMPTY 'shipping separately' list...")
    packing_slip_pdf_bytes_no_separate = generate_packing_slip_pdf(
        order_data=sample_order_data_ps,
        items_in_this_shipment=sample_items_in_shipment, 
        items_shipping_separately=[], 
        logo_gcs_uri=test_logo_gcs_uri,
        po_number_for_slip="PO-SINGLE-FULL"
    )
    ps_filename_no_separate = "LOCAL_TEST_packing_slip_no_separate.pdf"
    with open(ps_filename_no_separate, "wb") as f: f.write(packing_slip_pdf_bytes_no_separate)
    print(f"Sample Packing Slip PDF (no separate items) generated: {ps_filename_no_separate}")

    print("\nTesting Packing Slip with EMPTY 'items_in_this_shipment' list...")
    packing_slip_pdf_bytes_no_shipped = generate_packing_slip_pdf(
        order_data=sample_order_data_ps,
        items_in_this_shipment=[], 
        items_shipping_separately=sample_items_shipping_separately, 
        logo_gcs_uri=test_logo_gcs_uri,
        po_number_for_slip="PO-ONLY-SEPARATE"
    )
    ps_filename_no_shipped = "LOCAL_TEST_packing_slip_no_shipped.pdf"
    with open(ps_filename_no_shipped, "wb") as f: f.write(packing_slip_pdf_bytes_no_shipped)
    print(f"Sample Packing Slip PDF (no shipped items) generated: {ps_filename_no_shipped}")