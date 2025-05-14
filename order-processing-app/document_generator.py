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
COMPANY_NAME = "GLOBAL ONE TECHNOLOGY" # Updated
COMPANY_ADDRESS_PO_HEADER = "4916 S 184th Plaza - Omaha, NE 68135"
COMPANY_ADDRESS_PACKING_SLIP_FOOTER_LINE1 = ""
COMPANY_PHONE = "(877) 418-3246"
COMPANY_FAX = "(866) 921-1032"
COMPANY_EMAIL = "sales@globalonetechnology.com"
COMPANY_WEBSITE = "www.globalonetechnology.com"

# --- Helper function to format currency ---
def format_currency(value):
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return "$0.00"

# --- Helper function to format shipping method for display ---
def _format_shipping_method_for_display(method_string):
    if not method_string or not isinstance(method_string, str):
        return "N/A"
    # Regex to find content within the last parentheses
    match = re.search(r'\(([^)]+)\)[^(]*$', method_string)
    if match:
        return match.group(1).strip()
    return method_string.strip()

# --- Custom Styles ---
def get_custom_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Normal_Helvetica', parent=styles['Normal'], fontName='Helvetica'))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Small', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Bold', parent=styles['Normal'], fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Bold_Center', parent=styles['Normal_Helvetica_Bold'], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Right', parent=styles['Normal_Helvetica'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Center', parent=styles['Normal_Helvetica'], alignment=TA_CENTER))

    styles.add(ParagraphStyle(name='H1_Helvetica', parent=styles['h1'], fontName='Helvetica-Bold', fontSize=16, leading=18))
    styles.add(ParagraphStyle(name='H1_Helvetica_Right', parent=styles['H1_Helvetica'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='H2_Helvetica', parent=styles['h2'], fontName='Helvetica-Bold', fontSize=14, leading=16))
    styles.add(ParagraphStyle(name='H3_Helvetica', parent=styles['h3'], fontName='Helvetica-Bold', fontSize=10, leading=12))
    styles.add(ParagraphStyle(name='Normal_Helvetica_Semibold', parent=styles['Normal_Helvetica'], fontName='Helvetica-Bold', fontSize=9, leading=11))

    styles.add(ParagraphStyle(name='ItemDesc', parent=styles['Normal_Helvetica'], fontSize=9, leading=11))
    styles.add(ParagraphStyle(name='ItemDescSmall', parent=styles['Normal_Helvetica'], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name='FulfillmentNoteStyle', parent=styles['Normal_Helvetica'], fontSize=9, leading=11, textColor=colors.HexColor("#666666"))) # Medium grey

    styles.add(ParagraphStyle(name='FooterStyle', parent=styles['Normal_Helvetica_Small'], alignment=TA_CENTER))
    # ***** MODIFICATION: Style for environment note in footer (light grey) *****
    styles.add(ParagraphStyle(name='EnvironmentNoteStyle', parent=styles['Normal_Helvetica_Small'], alignment=TA_CENTER, textColor=colors.HexColor("#888888")))


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
                return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Helvetica'])
        else: # Pillow not available
            logo_stream.seek(0)
            actual_logo_height = None

        if actual_logo_height is not None:
            logo = Image(logo_stream, width=actual_logo_width, height=actual_logo_height)
        else:
            logo = Image(logo_stream, width=actual_logo_width, kind='bound')
        if not logo.imageWidth or not logo.imageHeight or logo.imageWidth == 0 or logo.imageHeight == 0:
            raise ValueError(f"ReportLab Image dimensions invalid for '{logo_gcs_uri}'.")
        return logo
    except Exception as e:
        print(f"ERROR _get_logo_element_from_gcs: Failed to load logo: {e}"); traceback.print_exc()
        if logo_stream and not logo_stream.closed: logo_stream.close()
        return Paragraph(f"<b>{COMPANY_NAME}</b>", styles['H2_Helvetica'])

# --- Function to Generate Purchase Order PDF ---
def generate_purchase_order_pdf(order_data, supplier_data, po_number, po_date, po_items, payment_terms, payment_instructions, logo_gcs_uri=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=0.75*inch, rightMargin=0.75*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = get_custom_styles()
    story = []

    logo_element = _get_logo_element_from_gcs(styles, logo_gcs_uri, desired_logo_width=2*inch)

    formatted_po_date = f"{po_date.month}/{po_date.day}/{po_date.year}"
    header_data = [
        [
            logo_element,
            Paragraph("<b>PURCHASE ORDER</b>", styles['H1_Helvetica_Right'])
        ],
        [
            Paragraph(COMPANY_ADDRESS_PO_HEADER, styles['Normal_Helvetica']),
            Paragraph(f"Date: {formatted_po_date}<br/>P.O. No.: {po_number}", styles['Normal_Helvetica_Right'])
        ]
    ]
    header_table = Table(header_data, colWidths=[4*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (0,0), 6),
        ('BOTTOMPADDING', (0,1), (0,1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('SPAN', (0,0), (0,0)),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.25 * inch))

    vendor_ship_to_content = [
        [Paragraph("<b>Vendor</b>", styles['H3_Helvetica']), Paragraph("<b>Ship To</b>", styles['H3_Helvetica'])],
        [
            Paragraph(
                f"{supplier_data.get('name', 'N/A')}<br/>"
                f"{supplier_data.get('address_line1', '')}<br/>"
                f"{supplier_data.get('address_line2', '') or ''}<br/>"
                f"{supplier_data.get('city', '')}, {supplier_data.get('state', '')} {supplier_data.get('zip', '')}<br/>"
                f"{supplier_data.get('country', '')}",
                styles['Normal_Helvetica']
            ),
            Paragraph(
                "PLEASE BLIND DROP SHIP<br/>USING ATTACHED LABEL<br/>AND PACKING SLIP",
                styles['Normal_Helvetica']
            )
        ]
    ]
    vendor_ship_to_table = Table(vendor_ship_to_content, colWidths=[3.5*inch, 3.5*inch])
    vendor_ship_to_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(vendor_ship_to_table)
    story.append(Spacer(1, 0.25 * inch))

    items_header = [
        Paragraph('<b>Item</b>', styles['Normal_Helvetica_Bold']),
        Paragraph('<b>Qty</b>', styles['Normal_Helvetica_Bold']),
        Paragraph('<b>Rate</b>', styles['Normal_Helvetica_Bold']),
        Paragraph('<b>Amount</b>', styles['Normal_Helvetica_Bold'])
    ]
    items_table_data = [items_header]
    total_po_amount = 0

    for item in po_items:
        item_amount = float(item.get('quantity', 0)) * float(item.get('unit_cost', 0.00))
        total_po_amount += item_amount
        # ***** MODIFICATION: Condition no longer appended to description_text *****
        description_text = f"{item.get('description', 'N/A')}"
        # The 'condition' is still available in item.get('condition') if needed elsewhere,
        # but not appended to description_text for the PDF.

        items_table_data.append([
            Paragraph(description_text, styles['ItemDesc']),
            Paragraph(str(item.get('quantity', 0)), styles['Normal_Helvetica_Right']),
            Paragraph(format_currency(item.get('unit_cost', 0.00)), styles['Normal_Helvetica_Right']),
            Paragraph(format_currency(item_amount), styles['Normal_Helvetica_Right'])
        ])

    items_table = Table(items_table_data, colWidths=[4.0*inch, 0.5*inch, 1*inch, 1.5*inch])
    items_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('ALIGN', (0,0), (0,0), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('TOPPADDING', (0,0), (-1,0), 6),
        ('BOTTOMPADDING', (0,1), (-1,-1), 4),
        ('TOPPADDING', (0,1), (-1,-1), 4),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 0.1 * inch))

    notes_and_total_data = []

    if payment_instructions:
        # ***** MODIFICATION: PO notes (payment instructions) now use ItemDesc style *****
        notes_and_total_data.append([
            Paragraph(payment_instructions.replace('\n', '<br/>'), styles['ItemDesc']), '', '', ''
        ])

    if order_data.get('bigcommerce_order_id'):
        # ***** MODIFICATION: Fulfillment note text and style changed *****
        notes_and_total_data.append([
            Paragraph(f"Fulfillment of G1 Order #{order_data.get('bigcommerce_order_id', 'N/A')}", styles['FulfillmentNoteStyle']), '', '', ''
        ])

    if notes_and_total_data: # Add a spacer row if any notes were added
         notes_and_total_data.append(['', '', '', ''])

    notes_and_total_data.append([
        '', '', Paragraph("<b>Total</b>", styles['Normal_Helvetica_Bold']), Paragraph(f"<b>USD {format_currency(total_po_amount)}</b>", styles['Normal_Helvetica_Right'])
    ])

    if notes_and_total_data:
        notes_total_table = Table(notes_and_total_data, colWidths=[4.0*inch, 0.5*inch, 1*inch, 1.5*inch])
        style_cmds = [
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (0,-1), 0),
        ]
        current_row_for_span = 0
        if payment_instructions:
            style_cmds.append(('SPAN', (0,current_row_for_span), (3,current_row_for_span)))
            current_row_for_span +=1
        if order_data.get('bigcommerce_order_id'):
            style_cmds.append(('SPAN', (0,current_row_for_span), (3,current_row_for_span)))
            # No increment here if it's the last note before the spacer

        total_row_idx = len(notes_and_total_data) - 1
        style_cmds.extend([
            ('ALIGN', (2, total_row_idx), (3, total_row_idx), 'RIGHT'),
            ('FONTNAME', (2, total_row_idx), (2, total_row_idx), 'Helvetica-Bold'),
            ('FONTNAME', (3, total_row_idx), (3, total_row_idx), 'Helvetica-Bold'),
            ('TOPPADDING', (2, total_row_idx), (3, total_row_idx), 10),
        ])
        notes_total_table.setStyle(TableStyle(style_cmds))
        story.append(notes_total_table)

    story.append(Spacer(1, 0.3 * inch))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

# --- Packing Slip Footer Function ---
def _draw_packing_slip_footer(canvas, doc):
    canvas.saveState()
    styles = get_custom_styles()

    # Calculate available width for footer elements
    available_width = doc.width
    left_margin = doc.leftMargin
    
    # Start drawing from bottom of usable page area, adjusted for content height
    current_y = 0.3 * inch # Start a bit from the bottom edge

    # Environment Statement (at the very bottom, centered)
    env_text = """In an effort to minimize our footprint on the environment,<br/>Global One Technology uses clean, recycled packaging materials."""
    p_env = Paragraph(env_text, styles['EnvironmentNoteStyle'])
    p_env.wrapOn(canvas, available_width, doc.bottomMargin) # Wrap within page width
    p_env.drawOn(canvas, left_margin, current_y)
    current_y += p_env.height + 0.1 * inch # Space above next section

    # Company Details (centered)
    # ***** MODIFICATION: Removed "Group, Inc" and using FooterStyle for centering *****
    company_footer_text = f"""
    <font name="Helvetica-Bold" size="9">{COMPANY_NAME}</font><br/>
    <font name="Helvetica" size="8">
    Voice: {COMPANY_PHONE} Fax: {COMPANY_FAX}<br/>
    {COMPANY_ADDRESS_PACKING_SLIP_FOOTER_LINE1}<br/>
    Email: {COMPANY_EMAIL} Website: {COMPANY_WEBSITE}
    </font>
    """
    p_company = Paragraph(company_footer_text, styles['FooterStyle'])
    p_company.wrapOn(canvas, available_width, doc.bottomMargin)
    p_company.drawOn(canvas, left_margin, current_y)
    current_y += p_company.height + 0.15 * inch

    # FAQ Text (remains left-aligned as per previous design, drawn above company details)
    faq_text = """
    <font name="Helvetica" size="9"><b>FAQ's:</b></font><br/>
    <font name="Helvetica" size="8">
    1. We ordered the wrong part or have a defective item. How would we arrange a return?<br/>
    Please visit http://www.globalonetechnology.com/returns for information on how to return an item.<br/><br/>
    2. How can I get a copy of our invoice for bookkeeping/accounting?<br/>
    Please email sales@globalonetechnology.com to request a copy of your invoice.
    </font>
    """
    p_faq = Paragraph(faq_text, styles['Normal_Helvetica_Small']) # Keep left-aligned
    p_faq.wrapOn(canvas, available_width, doc.bottomMargin)
    p_faq.drawOn(canvas, left_margin, current_y)

    canvas.restoreState()


# --- Function to Generate Packing Slip PDF ---
def generate_packing_slip_pdf(order_data, packing_slip_items, logo_gcs_uri=None):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            leftMargin=0.75*inch, rightMargin=0.75*inch,
                            topMargin=0.5*inch, bottomMargin=1.9*inch) # Increased bottom margin for footer
    styles = get_custom_styles()
    story = []

    logo_element = _get_logo_element_from_gcs(styles, logo_gcs_uri, desired_logo_width=2*inch)

    current_date = datetime.now(timezone.utc)
    formatted_current_date = f"{current_date.month}/{current_date.day}/{current_date.year}"

    header_data = [
        [
            logo_element,
            Paragraph("<b>PACKING SLIP</b>", styles['H1_Helvetica_Right'])
        ],
        [
            Paragraph(COMPANY_ADDRESS_PO_HEADER, styles['Normal_Helvetica_Small']),
            Paragraph(f"Date: {formatted_current_date}<br/>Order #: {order_data.get('bigcommerce_order_id', 'N/A')}", styles['Normal_Helvetica_Right'])
        ]
    ]
    header_table = Table(header_data, colWidths=[4*inch, 3*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (0,0), 6),
        ('SPAN', (0,0), (0,0)),
        # Grey background removed
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceBefore=0.05*inch, spaceAfter=0.1*inch))

    ship_to_address_text = ( # Renamed to avoid conflict with table cell
        f"{order_data.get('customer_name', 'N/A')}<br/>"
        f"{order_data.get('customer_shipping_address_line1', '')}<br/>"
        f"{order_data.get('customer_shipping_address_line2', '') or ''}<br/>"
        f"{order_data.get('customer_shipping_city', '')}, {order_data.get('customer_shipping_state', '')} {order_data.get('customer_shipping_zip', '')}<br/>"
        f"{order_data.get('customer_shipping_country', '')}"
    )
    ship_to_para = Paragraph(ship_to_address_text, styles['Normal_Helvetica'])


    # ***** MODIFICATION: Shipping method formatting and layout *****
    formatted_shipping_method = _format_shipping_method_for_display(order_data.get('customer_shipping_method', 'N/A'))
    payment_method_text = order_data.get('payment_method', 'N/A')

    # Create a list of Paragraphs for the right column (shipping and payment)
    right_column_content = [
        Paragraph(f"<b>Shipping Method:</b> {formatted_shipping_method}", styles['Normal_Helvetica_Right']),
        Spacer(1, 0.05 * inch), # Small spacer
        Paragraph(f"<b>Payment Method:</b> {payment_method_text}", styles['Normal_Helvetica_Right'])
    ]

    shipping_details_data = [
        [Paragraph("<b>Ship To:</b>", styles['H3_Helvetica']), None], # Placeholder for right column
        [ship_to_para, None] # Placeholder for right column
    ]

    shipping_details_table = Table(shipping_details_data, colWidths=[3.5*inch, 3.5*inch])
    shipping_details_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        # ('ALIGN', (1,1), (1,1), 'RIGHT'), # Alignment handled by Paragraphs now
        ('SPAN', (1,0), (1,1)), # Span the placeholder cells for the right column content
    ]))
    story.append(shipping_details_table)

    # Manually add the right column content into the spanned cell
    # This gives more control over vertical alignment if needed, but KeepInFrame is often simpler
    # For now, let's try placing it directly using coordinates relative to the table or page
    # A simpler approach for now is to put it in the table cell if possible.
    # We'll use a nested table or a list of flowables for the right cell.
    
    # Replace the placeholder in the table with the actual content
    shipping_details_table._cellvalues[0][1] = "" # Top right cell empty (above ship to)
    shipping_details_table._cellvalues[1][1] = right_column_content # Content for bottom right


    story.append(Spacer(1, 0.25 * inch))

    # ***** MODIFICATION: "Qty" centered, "Description" changed to "Item" *****
    items_header = [
        Paragraph('<b>Qty</b>', styles['Normal_Helvetica_Bold_Center']),
        Paragraph('<b>Item</b>', styles['Normal_Helvetica_Bold'])
    ]
    items_table_data = [items_header]

    for item in packing_slip_items:
        items_table_data.append([
            Paragraph(str(item.get('quantity', 0)), styles['Normal_Helvetica_Center']),
            Paragraph(item.get('name', item.get('description', 'N/A')), styles['ItemDesc'])
        ])

    items_table = Table(items_table_data, colWidths=[0.75*inch, 6.25*inch])
    items_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (0,0), 'CENTER'), # Center Qty header
        ('ALIGN', (1,0), (1,0), 'LEFT'),   # Item header left
        ('ALIGN', (0,1), (0,-1), 'CENTER'), # Center Qty data
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('TOPPADDING', (0,0), (-1,0), 6),
        ('BOTTOMPADDING', (0,1), (-1,-1), 4),
        ('TOPPADDING', (0,1), (-1,-1), 4),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f0f0f0")),
    ]))
    story.append(items_table)

    doc.build(story, onFirstPage=_draw_packing_slip_footer, onLaterPages=_draw_packing_slip_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

# --- Example usage (for testing the functions independently) ---
if __name__ == '__main__':
    print("Running document_generator.py in local test mode.")
    print("NOTE: Logo will be text unless you manually set a test_logo_gcs_uri below.")

    sample_order_data_po = { 'bigcommerce_order_id': '106157456' }
    sample_supplier_data = { 'name': 'Test Supplier Inc.', 'address_line1': '123 Test St', 'city': 'Testville', 'state': 'TS', 'zip': '12345', 'country': 'USA', 'payment_terms': 'Net 30' }
    sample_po_items = [{'sku': 'TEST-SKU-1', 'description': 'Test Item One (Condition Suffix)', 'quantity': 2, 'unit_cost': 10.50, 'condition': 'New'}, {'sku': 'TEST-SKU-2', 'description': 'Test Item Two', 'quantity': 1, 'unit_cost': 25.00, 'condition': 'Used'}]
    po_specific_notes = "Test payment instructions.\nSecond line."
    sample_order_data_ps = {
        'bigcommerce_order_id': '106157456',
        'customer_name': 'Test Customer',
        'customer_shipping_address_line1': '456 Ship Ave',
        'customer_shipping_city': 'Shipton',
        'customer_shipping_state': 'SH',
        'customer_shipping_zip': '67890',
        'customer_shipping_country': 'USA',
        'po_number': 'CUST-PO-789', # This is customer's PO, not ours
        'customer_shipping_method': 'UPS Expedited (UPS Expedited Service)',
        'payment_method': 'Credit Card via PayPal'
    }
    sample_packing_slip_items = [
        {'quantity': 2, 'name': 'Test Item One - Clean Name', 'sku': 'TEST-SKU-1'}, # Ensure this has the desired clean name
        {'quantity': 1, 'name': 'Test Item Two - Clean Name', 'sku': 'TEST-SKU-2'}
    ]
    test_logo_gcs_uri = None # "gs://your-bucket/path/to/logo.png" for testing GCS logo

    print("\nGenerating Sample Purchase Order (Local Test)...")
    po_pdf_bytes = generate_purchase_order_pdf(
        order_data=sample_order_data_po,
        supplier_data=sample_supplier_data,
        po_number='TEST-PO-123',
        po_date=datetime.now(timezone.utc),
        po_items=sample_po_items,
        payment_terms=sample_supplier_data['payment_terms'],
        payment_instructions=po_specific_notes,
        logo_gcs_uri=test_logo_gcs_uri
    )
    po_filename = "LOCAL_TEST_purchase_order.pdf"
    with open(po_filename, "wb") as f: f.write(po_pdf_bytes)
    print(f"Sample Purchase Order PDF generated: {po_filename}")

    print("\nGenerating Sample Packing Slip (Local Test)...")
    packing_slip_pdf_bytes = generate_packing_slip_pdf(
        order_data=sample_order_data_ps,
        packing_slip_items=sample_packing_slip_items,
        logo_gcs_uri=test_logo_gcs_uri
    )
    ps_filename = "LOCAL_TEST_packing_slip.pdf"
    with open(ps_filename, "wb") as f: f.write(packing_slip_pdf_bytes)
    print(f"Sample Packing Slip PDF generated: {ps_filename}")

