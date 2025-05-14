# email_service.py - Updated with Postmark Integration & IIF Warning

import os
import base64
import json # For parsing Postmark error responses if needed
from datetime import datetime, timezone # Not directly used in send_po_email but good practice
from dotenv import load_dotenv


# Attempt to import PostmarkClient
try:
    from postmarker.core import PostmarkClient
except ImportError:
    PostmarkClient = None
    print("WARN EMAIL_SERVICE: 'postmarker' library not found. Please install it (`pip install postmarker`). Email sending will be mocked.")

# Load environment variables
load_dotenv()

# --- Email Configuration (centralized) ---
EMAIL_SERVICE_PROVIDER = os.getenv("EMAIL_SERVICE_PROVIDER", "Postmark").lower() # Default to Postmark
EMAIL_API_KEY = os.getenv("EMAIL_API_KEY") # This should be your Postmark Server API Token
EMAIL_SENDER_ADDRESS = os.getenv("EMAIL_SENDER_ADDRESS")
EMAIL_BCC_ADDRESS = os.getenv("EMAIL_BCC_ADDRESS")
QUICKBOOKS_EMAIL_RECIPIENT = os.getenv("QUICKBOOKS_EMAIL_RECIPIENT", "sales@globalonetechnology.com")
DAILY_IIF_EMAIL_SUBJECT_PREFIX = os.getenv("DAILY_IIF_EMAIL_SUBJECT_PREFIX", "Daily Purchase Orders IIF Batch for")
# Your company name for email content - consider making this an env var too
COMPANY_NAME_FOR_EMAIL = os.getenv("COMPANY_NAME_FOR_EMAIL", "Global One Technology")


def _get_postmark_headers(): # This might not be needed if using PostmarkClient library
    """Helper to get Postmark API headers if using direct requests.
       Not typically used with the postmarker library."""
    if not EMAIL_API_KEY:
        print("DEBUG EMAIL: Email API key (EMAIL_API_KEY) not configured.")
        return None
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": EMAIL_API_KEY
    }

def _format_item_sku_for_quickbooks(description, sku):
    # ... (your existing _format_item_sku_for_quickbooks function) ...
    desc_lower = description.lower() if description else ""
    brand = "UnknownBrand"
    if "hpe" in desc_lower: brand = "HPE"
    elif "hp" in desc_lower: brand = "HP"
    category = "Part"
    if "memory" in desc_lower or "ram" in desc_lower or "dimm" in desc_lower: category = "Memory"
    elif "drive" in desc_lower or "hdd" in desc_lower or "ssd" in desc_lower: category = "Storage"
    elif "processor" in desc_lower or "cpu" in desc_lower: category = "CPU"
    elif "adapter" in desc_lower or "card" in desc_lower: category = "Adapter"
    elif "power supply" in desc_lower or "psu" in desc_lower: category = "PowerSupply"
    elif "cable" in desc_lower: category = "Cable"
    elif "kit" in desc_lower:
        if "memory" in desc_lower : category = "MemoryKit"
        else: category = "Kit"
    if category == "Part" and brand != "UnknownBrand":
        if "server" in desc_lower: category = "ServerPart"
        elif "storage" in desc_lower: category = "StoragePart"
    return f"{brand}:{category}:{sku}"


def send_po_email(supplier_email, po_number, attachments):
    """
    Sends the PO email with provided documents as attachments using Postmark.
    Each item in 'attachments' should be a dict:
    {'filename': 'somefile.ext', 'content': byte_data, 'content_type': 'mime/type'}
    """
    print(f"DEBUG EMAIL_SERVICE (PO): Attempting to send PO email for PO {po_number} to {supplier_email}")

    if EMAIL_SERVICE_PROVIDER != "postmark":
        print(f"DEBUG EMAIL_SERVICE (PO): Email service provider is '{EMAIL_SERVICE_PROVIDER}', not 'postmark'. Skipping actual send.")
        return False # Or raise an error, or implement other providers

    if not PostmarkClient:
        print("ERROR EMAIL_SERVICE (PO): PostmarkClient library is not available. Email not sent.")
        return False

    if not EMAIL_API_KEY or not EMAIL_SENDER_ADDRESS:
        print("ERROR EMAIL_SERVICE (PO): Postmark Server Token (EMAIL_API_KEY) or Sender Address not configured.")
        return False

    if not supplier_email:
        print(f"ERROR EMAIL_SERVICE (PO): No supplier email provided for PO {po_number}.")
        return False

    try:
        client = PostmarkClient(server_token=EMAIL_API_KEY)

        email_attachments_for_postmark = []
        if attachments:
            for att_data in attachments:
                if att_data and att_data.get('filename') and att_data.get('content') and att_data.get('content_type'):
                    encoded_content = base64.b64encode(att_data['content']).decode('utf-8')
                    email_attachments_for_postmark.append({
                        "Name": att_data['filename'],
                        "Content": encoded_content,
                        "ContentType": att_data['content_type']
                    })
                else:
                    print(f"WARN EMAIL_SERVICE (PO): Invalid attachment data skipped for PO {po_number}: {att_data}")

        subject = f"New Purchase Order #{po_number} from {COMPANY_NAME_FOR_EMAIL}"
        html_body = f"""
        <p>Hello,</p>
        <p><br></p>
        <p>Attached are the purchase order, packing slip, and shipping paperwork for our PO# referenced above. Kindly process at your earliest convenience.</p>
        <p><br></p>
        <p>Thanks!</p>
        <p><br></p>
        <p><strong>Mark T. Winkler</strong></p>
        <p><em>HP Enterprise Purchasing and Fulfillment</em></p>
        <p><strong>Global One Technology</strong></p>
        <p>
            <img src="https://fonts.gstatic.com/s/e/notoemoji/16.0/2709_fe0f/72.png" alt="✉️" height="17" width="17">&nbsp;
            <a href="mailto:sales@globalonetechnology.com" target="_blank" style="color: rgb(31, 162, 221);">sales@globalonetechnology.com</a>
        </p>
        """

        print(f"DEBUG EMAIL_SERVICE (PO): Sending Postmark email to {supplier_email} for PO {po_number} with {len(email_attachments_for_postmark)} attachments.")

        # Construct the email parameters
        email_params = {
            "From": f"Mark Winkler | Global One Technology <{EMAIL_SENDER_ADDRESS}>",
            "To": supplier_email,
            "Subject": subject,
            "HtmlBody": html_body,
            "Attachments": email_attachments_for_postmark,
            "TrackOpens": True,
            "MessageStream": "outbound" # Or your specific transactional stream if configured
        }

        # Add BCC if configured
        if EMAIL_BCC_ADDRESS:
            email_params["Bcc"] = EMAIL_BCC_ADDRESS
            print(f"DEBUG EMAIL_SERVICE (PO): BCCing to {EMAIL_BCC_ADDRESS}")

        response = client.emails.send(**email_params)

        print(f"INFO EMAIL_SERVICE (PO): Email for PO {po_number} sent successfully via Postmark. MessageID: {response.get('MessageID') if isinstance(response, dict) else 'N/A'}")
        return True

    except Exception as e:
        print(f"CRITICAL EMAIL_SERVICE (PO): Failed to send PO email for PO {po_number} via Postmark: {e}")
        import traceback
        traceback.print_exc()
        return False

def send_quickbooks_data_email(po_data):
    """Sends structured PO data for potential QuickBooks import."""
    print(f"DEBUG QB_EMAIL: Attempting to send QuickBooks data email for PO {po_data.get('po_number')}")

    if EMAIL_SERVICE_PROVIDER != "postmark":
        print(f"DEBUG QB_EMAIL: Email service provider is '{EMAIL_SERVICE_PROVIDER}', not Postmark. Skipping QB email.")
        return False
    if not PostmarkClient:
        print("ERROR QB_EMAIL: PostmarkClient library is not available. QB Email not sent.")
        return False
    if not EMAIL_API_KEY or not EMAIL_SENDER_ADDRESS or not QUICKBOOKS_EMAIL_RECIPIENT:
        print("DEBUG QB_EMAIL: Postmark API key, sender, or QB recipient address not configured. Skipping QB email.")
        return False

    client = PostmarkClient(server_token=EMAIL_API_KEY)

    body_lines = [
        f"Supplier: {po_data.get('supplier_name', 'N/A')}",
        f"PO_Number: {po_data.get('po_number', 'N/A')}",
        f"PO_Date: {po_data.get('po_date').strftime('%Y-%m-%d') if po_data.get('po_date') else 'N/A'}",
        f"Shipping_Method: {po_data.get('shipping_method', 'N/A')}",
        f"Payment_Instructions: {po_data.get('payment_instructions_for_po', 'N/A')}",
        f"Fulfillment_Order_ID: {po_data.get('fulfillment_order_id', 'N/A')}",
        f"Expected_Delivery_Date: {po_data.get('expected_delivery_date', 'N/A (Not Provided)')}",
        ""
    ]
    for i, item in enumerate(po_data.get('po_line_items', [])):
        formatted_sku = _format_item_sku_for_quickbooks(item.get('description'), item.get('sku'))
        body_lines.extend([
            "[ITEM_START]", f"Item_SKU: {formatted_sku}",
            f"Item_FullDescription: {item.get('description', 'N/A')}",
            f"Item_Quantity: {item.get('quantity', 0)}",
            f"Item_UnitPrice: {item.get('unit_cost', 0.00)}", "[ITEM_END]", ""
        ])
    email_text_body = "\n".join(body_lines)

    try:
        response = client.emails.send(
            From=EMAIL_SENDER_ADDRESS,
            To=QUICKBOOKS_EMAIL_RECIPIENT,
            Subject=f"PO Data for QuickBooks Import - PO #{po_data.get('po_number', 'N/A')}",
            TextBody=email_text_body,
            MessageStream="outbound" # Or your specific stream
        )
        print(f"INFO QB_EMAIL: QB Data email for PO {po_data.get('po_number')} sent. MessageID: {response.get('MessageID') if isinstance(response, dict) else 'N/A'}")
        return True
    except Exception as e:
        print(f"CRITICAL QB_EMAIL: Failed to send QB Data email for PO {po_data.get('po_number')}: {e}")
        return False


# --- CORRECTED FUNCTION DEFINITION ---
def send_iif_batch_email(iif_content_string, batch_date_str, warning_message_html=None):
    """
    Sends the daily IIF batch email using Postmark.

    Args:
        iif_content_string (str): The IIF file content as a string.
        batch_date_str (str): The date string (YYYY-MM-DD) for the batch.
        warning_message_html (str, optional): HTML formatted warning message
                                               about mapping failures. Defaults to None.
    Returns:
        bool: True if email sending was successful (or simulated), False otherwise.
    """
    print(f"DEBUG IIF_EMAIL: Attempting to send IIF batch email for date {batch_date_str}")
    if EMAIL_SERVICE_PROVIDER != "postmark":
        print(f"DEBUG IIF_EMAIL: Email service provider is '{EMAIL_SERVICE_PROVIDER}', not Postmark. Skipping.")
        return False # Indicate failure if not Postmark
    if not PostmarkClient:
        print("ERROR IIF_EMAIL: PostmarkClient library is not available. IIF Email not sent.")
        return False
    if not EMAIL_API_KEY or not EMAIL_SENDER_ADDRESS or not QUICKBOOKS_EMAIL_RECIPIENT:
        print("ERROR IIF_EMAIL: Postmark API key, sender, or QB recipient not configured. Skipping.")
        return False

    client = PostmarkClient(server_token=EMAIL_API_KEY)
    iif_filename = f"QB_POs_Batch_{batch_date_str.replace('-', '')}.iif"

    # Prepare attachment
    attachments = [{
        "Name": iif_filename,
        "Content": base64.b64encode(iif_content_string.encode('utf-8')).decode('utf-8'),
        "ContentType": "application/iif" # Correct MIME type for IIF
    }]

    # Construct email body, including the warning if present
    html_body_parts = []
    text_body_parts = []

    if warning_message_html:
        html_body_parts.append(warning_message_html) # Add warning first
        # Create a simple text version of the warning
        # (This is basic, could be improved with regex or HTML parsing if needed)
        text_warning = "WARNING: QuickBooks Item Mapping Failures occurred. See attached IIF and review mappings."
        text_body_parts.append(text_warning)
        text_body_parts.append("-" * 20) # Separator

    # Add standard body text
    standard_html_body = f"<p>Attached is the batch IIF file for Purchase Orders processed on {batch_date_str}.</p>"
    standard_text_body = f"Attached is the batch IIF file for Purchase Orders processed on {batch_date_str}."
    html_body_parts.append(standard_html_body)
    text_body_parts.append(standard_text_body)

    final_html_body = "\n".join(html_body_parts)
    final_text_body = "\n".join(text_body_parts)

    subject = f"{DAILY_IIF_EMAIL_SUBJECT_PREFIX} {batch_date_str}"

    try:
        print(f"DEBUG IIF_EMAIL: Sending email to {QUICKBOOKS_EMAIL_RECIPIENT} with subject '{subject}'")
        response = client.emails.send(
            From=EMAIL_SENDER_ADDRESS,
            To=QUICKBOOKS_EMAIL_RECIPIENT,
            Subject=subject,
            HtmlBody=final_html_body,
            TextBody=final_text_body, # Include a text part for clients that don't render HTML
            Attachments=attachments,
            MessageStream="outbound" # Or your specific stream
        )
        print(f"INFO IIF_EMAIL: IIF Batch email for {batch_date_str} sent. MessageID: {response.get('MessageID') if isinstance(response, dict) else 'N/A'}")
        return True
    except Exception as e:
        print(f"CRITICAL IIF_EMAIL: Failed to send IIF Batch email for {batch_date_str}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("--- Testing Email Service ---")

    # Test send_po_email
    # ... (keep existing PO email test code, ensure you uncomment and use a real test email) ...

    # Test send_quickbooks_data_email
    # ... (keep existing QB data email test code) ...

    # Test send_iif_batch_email
    print("\n--- Testing IIF Batch Email ---")
    sample_iif_content = "!TRNS\tTRNSID\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tDOCNUM\tMEMO\n!SPL\tSPLID\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tDOCNUM\tMEMO\tQNTY\tPRICE\tINVITEM\n!ENDTRNS\nTRNS\t\tPURCHORD\t05/12/2025\tAccounts Payable\tTest Supplier\t10.00\tPO-TEST\tTest PO\nSPL\t\tPURCHORD\t05/12/2025\tCost of Goods Sold\t\t10.00\tPO-TEST\tTest Item\t1\t10.00\tTest:Item:SKU123\nENDTRNS\n"
    test_batch_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Test without warning
    print("Testing IIF email without warning...")
    iif_email_sent_no_warn = send_iif_batch_email(iif_content_string=sample_iif_content, batch_date_str=test_batch_date)
    print(f"IIF Batch Email Send Test Result (No Warning): {iif_email_sent_no_warn}")
    # Test with warning
    print("\nTesting IIF email WITH warning...")
    sample_warning = '<p style="color:red;"><strong>WARNING TEST!</strong><ul><li>PO: P1, SKU: S1</li></ul></p><hr>'
    iif_email_sent_warn = send_iif_batch_email(iif_content_string=sample_iif_content, batch_date_str=test_batch_date, warning_message_html=sample_warning)
    print(f"IIF Batch Email Send Test Result (With Warning): {iif_email_sent_warn}")


    print("\n--- Make sure to set EMAIL_API_KEY (Postmark Server Token) and EMAIL_SENDER_ADDRESS in your .env for actual sending ---")
