# email_service.py - Updated with Postmark Integration & IIF Warning

import os
import base64
import traceback
import re
import json # For parsing Postmark error responses if needed
from xml.sax.saxutils import escape
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
COMPANY_WEBSITE = os.getenv("COMPANY_WEBSITE", "www.globalonetechnology.com") 

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


def send_po_email(supplier_email, po_number, attachments, is_blind_drop_ship=False): # Added is_blind_drop_ship
    """
    Sends the PO email with provided documents as attachments using Postmark.
    Each item in 'attachments' should be a dict:
    {'filename': 'somefile.ext', 'content': byte_data, 'content_type': 'mime/type'}
    The is_blind_drop_ship parameter is accepted but not currently used to alter email content.
    """
    print(f"DEBUG EMAIL_SERVICE (PO): Attempting to send PO email for PO {po_number} to {supplier_email}. Blind Ship: {is_blind_drop_ship}")

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
                if att_data and att_data.get('Name') and att_data.get('Content') and att_data.get('ContentType'):
                    email_attachments_for_postmark.append({
                        "Name": att_data['Name'],
                        "Content": att_data['Content'],
                        "ContentType": att_data['ContentType']
                    })
                else:
                    print(f"WARN EMAIL_SERVICE (PO): Invalid or incomplete attachment data structure skipped for PO {po_number}. Data: {att_data}")

        subject = f"New Purchase Order #{po_number} from {COMPANY_NAME_FOR_EMAIL}"
        html_body = f"""
         Hello,
         <br><br>
         Attached are the purchase order, packing slip, and shipping paperwork for our PO# referenced above. Kindly process at your earliest convenience.
         <br><br>
         Thanks!
         <br>
         <strong>Mark T. Winkler</strong>
         <br>
         <em>HP Enterprise Purchasing and Fulfillment</em>
         <br>
         <strong>Global One Technology</strong>
         <br>
         <a href="mailto:sales@globalonetechnology.com" target="_blank" style="color: rgb(31, 162, 221);">sales@globalonetechnology.com</a>
        """

        print(f"DEBUG EMAIL_SERVICE (PO): Sending Postmark email to {supplier_email} for PO {po_number} with {len(email_attachments_for_postmark)} attachments.")

        email_params = {
            "From": f"Mark Winkler | Global One Technology <{EMAIL_SENDER_ADDRESS}>",
            "To": supplier_email,
            "Subject": subject,
            "HtmlBody": html_body,
            "Attachments": email_attachments_for_postmark,
            "TrackOpens": True,
            "MessageStream": "outbound"
        }

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

def send_iif_batch_email(iif_content_string, batch_date_str,
                         warning_message_html=None,
                         custom_subject=None,
                         filename_prefix="IIF_Batch_"):
    """
    Sends the daily IIF batch email using Postmark.
    """
    print(f"DEBUG IIF_EMAIL: Attempting to send IIF batch email for context: {batch_date_str}, prefix: {filename_prefix}")
    if EMAIL_SERVICE_PROVIDER != "postmark":
        print(f"DEBUG IIF_EMAIL: Email service provider is '{EMAIL_SERVICE_PROVIDER}', not Postmark. Skipping.")
        return False
    if not PostmarkClient:
        print("ERROR IIF_EMAIL: PostmarkClient library is not available. IIF Email not sent.")
        return False
    if not EMAIL_API_KEY or not EMAIL_SENDER_ADDRESS or not QUICKBOOKS_EMAIL_RECIPIENT:
        print("ERROR IIF_EMAIL: Postmark API key, sender, or QB recipient not configured. Skipping.")
        return False

    try:
        client = PostmarkClient(server_token=EMAIL_API_KEY)

        date_part_for_filename = batch_date_str.replace('-', '')
        if "OnDemand" in batch_date_str:
            try:
                date_match = re.search(r'(\d{8})', batch_date_str)
                if date_match:
                    date_part_for_filename = date_match.group(1)
                else:
                    date_part_for_filename = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
            except Exception:
                date_part_for_filename = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')

        iif_filename = f"{filename_prefix}{date_part_for_filename}.iif"
        print(f"DEBUG IIF_EMAIL: Attachment filename will be: {iif_filename}")

        attachments = [{
            "Name": iif_filename,
            "Content": base64.b64encode(iif_content_string.encode('utf-8')).decode('utf-8'),
            "ContentType": "application/iif"
        }]

        html_body_parts = []
        text_body_parts = []

        if warning_message_html:
            html_body_parts.append(warning_message_html)
            text_warning = "WARNING: QuickBooks Item Mapping Failures occurred. See HTML email for details or check server logs."
            text_body_parts.append(text_warning)
            text_body_parts.append("-" * 20)

        standard_html_body = f"<p>Attached is the batch IIF file for context: {batch_date_str}.</p>"
        standard_text_body = f"Attached is the batch IIF file for context: {batch_date_str}."
        html_body_parts.append(standard_html_body)
        text_body_parts.append(standard_text_body)
        html_body_parts.append("<p>Import this file into QuickBooks Desktop via File > Utilities > Import > IIF Files.</p>")
        text_body_parts.append("Import this file into QuickBooks Desktop via File > Utilities > Import > IIF Files.")


        final_html_body = "\n".join(html_body_parts)
        final_text_body = "\n".join(text_body_parts)

        subject_date_context = batch_date_str
        if "OnDemand" in custom_subject if custom_subject else False:
             subject_date_context = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')


        subject_to_send = custom_subject if custom_subject else f"{DAILY_IIF_EMAIL_SUBJECT_PREFIX} {subject_date_context}"


        print(f"DEBUG IIF_EMAIL: Attempting to send IIF batch email for context {batch_date_str}")
        response = client.emails.send(
            From=EMAIL_SENDER_ADDRESS,
            To=QUICKBOOKS_EMAIL_RECIPIENT,
            Subject=subject_to_send,
            HtmlBody=final_html_body,
            TextBody=final_text_body,
            Attachments=attachments,
            MessageStream="outbound"
        )
        response_data = response
        if isinstance(response, dict) and response.get("ErrorCode") == 0:
            print(f"INFO IIF_EMAIL: IIF Batch email for {batch_date_str} sent. MessageID: {response.get('MessageID')}")
            return True
        elif hasattr(response, 'status_code') and response.status_code == 200:
            print(f"INFO IIF_EMAIL: IIF Batch email for {batch_date_str} sent (status 200).")
            return True
        else:
            print(f"ERROR IIF_EMAIL: Failed to send IIF Batch email. Response: {response_data}")
            return False

    except Exception as e:
        print(f"CRITICAL IIF_EMAIL: Failed to send IIF Batch email for {batch_date_str}: {e}")
        traceback.print_exc()
        return False


def send_sales_notification_email(recipient_email, subject, html_body, text_body, attachments):
    """
    Sends a generic notification email using Postmark, intended for internal sales notifications.
    """
    print(f"DEBUG EMAIL_SERVICE (SALES_NOTIF): Attempting to send notification email to {recipient_email} with subject '{subject}'")

    if EMAIL_SERVICE_PROVIDER != "postmark":
        print(f"DEBUG EMAIL_SERVICE (SALES_NOTIF): Email service provider is '{EMAIL_SERVICE_PROVIDER}', not 'postmark'. Skipping actual send.")
        return False

    if not PostmarkClient:
        print("ERROR EMAIL_SERVICE (SALES_NOTIF): PostmarkClient library is not available. Email not sent.")
        return False

    if not EMAIL_API_KEY or not EMAIL_SENDER_ADDRESS:
        print("ERROR EMAIL_SERVICE (SALES_NOTIF): Postmark Server Token (EMAIL_API_KEY) or Sender Address not configured.")
        return False

    if not recipient_email:
        print(f"ERROR EMAIL_SERVICE (SALES_NOTIF): No recipient email provided.")
        return False

    try:
        client = PostmarkClient(server_token=EMAIL_API_KEY)
        print(f"DEBUG EMAIL_SERVICE (SALES_NOTIF): Sending Postmark email to {recipient_email} with {len(attachments)} attachments.")

        email_params = {
            "From": f"{COMPANY_NAME_FOR_EMAIL} <{EMAIL_SENDER_ADDRESS}>",
            "To": recipient_email,
            "Subject": subject,
            "HtmlBody": html_body,
            "TextBody": text_body,
            "Attachments": attachments,
            "TrackOpens": True,
            "MessageStream": "outbound"
        }

        response = client.emails.send(**email_params)

        print(f"INFO EMAIL_SERVICE (SALES_NOTIF): Notification email sent successfully via Postmark. MessageID: {response.get('MessageID') if isinstance(response, dict) else 'N/A'}")
        return True

    except Exception as e:
        print(f"CRITICAL EMAIL_SERVICE (SALES_NOTIF): Failed to send notification email via Postmark: {e}")
        import traceback
        traceback.print_exc()
        return False

def send_customer_receipt_email(recipient_email, order_number, customer_name, pdf_attachment_bytes, pdf_filename="Paid_Invoice.pdf"):
    """
    Sends a "Paid Invoice" / Receipt email to the customer with the PDF attachment.
    """
    print(f"DEBUG EMAIL_SERVICE (RECEIPT): Attempting to send receipt for Order #{order_number} to {recipient_email}")

    if EMAIL_SERVICE_PROVIDER != "postmark":
        print(f"DEBUG EMAIL_SERVICE (RECEIPT): Email service provider is '{EMAIL_SERVICE_PROVIDER}', not 'postmark'. Skipping actual send.")
        return False

    if not PostmarkClient:
        print("ERROR EMAIL_SERVICE (RECEIPT): PostmarkClient library is not available. Email not sent.")
        return False

    if not EMAIL_API_KEY or not EMAIL_SENDER_ADDRESS: #
        print("ERROR EMAIL_SERVICE (RECEIPT): Postmark Server Token (EMAIL_API_KEY) or Sender Address not configured.") #
        return False

    if not recipient_email:
        print(f"ERROR EMAIL_SERVICE (RECEIPT): No recipient email provided for Order #{order_number}.")
        return False

    if not pdf_attachment_bytes:
        print(f"ERROR EMAIL_SERVICE (RECEIPT): No PDF attachment bytes provided for Order #{order_number}.")
        return False

    try:
        client = PostmarkClient(server_token=EMAIL_API_KEY) #

        # Ensure COMPANY_NAME_FOR_EMAIL is loaded, fallback if necessary
        company_display_name = os.getenv("COMPANY_NAME_FOR_EMAIL", "Global One Technology") #

        subject = f"Your Paid Invoice from {company_display_name} - Order #{order_number}"
        
        # Construct a polite HTML body
        html_body = f"""
        <p>Dear {escape(customer_name if customer_name else 'Valued Customer')},</p>
        <p>Thank you for your recent order with {escape(company_display_name)} (Order #{escape(str(order_number))}).</p>
        <p>Please find your paid invoice attached to this email for your records.</p>
        <p>We appreciate your business!</p>
        <p>Sincerely,</p>
        <p>The Team at {escape(company_display_name)}<br/>
        {escape(COMPANY_WEBSITE) if 'COMPANY_WEBSITE' in globals() else ''}</p>
        """
        
        text_body = f"""
        Dear {escape(customer_name if customer_name else 'Valued Customer')},

        Thank you for your recent order with {escape(company_display_name)} (Order #{escape(str(order_number))}).
        Please find your paid invoice attached to this email for your records.
        We appreciate your business!

        Sincerely,
        The Team at {escape(company_display_name)}
        {escape(COMPANY_WEBSITE) if 'COMPANY_WEBSITE' in globals() else ''}
        """

        email_attachments_for_postmark = [{
            "Name": pdf_filename, # e.g., "Paid_Invoice_Order_12345.pdf"
            "Content": base64.b64encode(pdf_attachment_bytes).decode('utf-8'), #
            "ContentType": "application/pdf" #
        }]

        print(f"DEBUG EMAIL_SERVICE (RECEIPT): Sending Postmark email to {recipient_email} for Order #{order_number} with attachment: {pdf_filename}.")

        email_params = {
            "From": f"{company_display_name} <{EMAIL_SENDER_ADDRESS}>", #
            "To": recipient_email,
            "Subject": subject,
            "HtmlBody": html_body,
            "TextBody": text_body, # Good practice to include a text version
            "Attachments": email_attachments_for_postmark, #
            "TrackOpens": True, # Optional: track if the email is opened
            "MessageStream": "outbound" # Or your designated stream for transactional customer emails
        }
        
        # Add BCC if configured
        bcc_address = os.getenv("EMAIL_BCC_ADDRESS") #
        if bcc_address:
            email_params["Bcc"] = bcc_address
            print(f"DEBUG EMAIL_SERVICE (RECEIPT): BCCing to {bcc_address}")


        response = client.emails.send(**email_params)

        print(f"INFO EMAIL_SERVICE (RECEIPT): Receipt email for Order #{order_number} sent successfully via Postmark. MessageID: {response.get('MessageID') if isinstance(response, dict) else 'N/A'}")
        return True

    except Exception as e:
        print(f"CRITICAL EMAIL_SERVICE (RECEIPT): Failed to send receipt email for Order #{order_number} to {recipient_email} via Postmark: {e}")
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("--- Testing Email Service ---")
    sample_iif_content = "!TRNS\tTRNSID\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tDOCNUM\tMEMO\n!SPL\tSPLID\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tDOCNUM\tMEMO\tQNTY\tPRICE\tINVITEM\n!ENDTRNS\nTRNS\t\tPURCHORD\t05/12/2025\tAccounts Payable\tTest Supplier\t10.00\tPO-TEST\tTest PO\nSPL\t\tPURCHORD\t05/12/2025\tCost of Goods Sold\t\t10.00\tPO-TEST\tTest Item\t1\t10.00\tTest:Item:SKU123\nENDTRNS\n"
    test_batch_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print("Testing IIF email without warning...")
    iif_email_sent_no_warn = send_iif_batch_email(iif_content_string=sample_iif_content, batch_date_str=test_batch_date)
    print(f"IIF Batch Email Send Test Result (No Warning): {iif_email_sent_no_warn}")
    print("\nTesting IIF email WITH warning...")
    sample_warning = '<p style="color:red;"><strong>WARNING TEST!</strong><ul><li>PO: P1, SKU: S1</li></ul></p><hr>'
    iif_email_sent_warn = send_iif_batch_email(iif_content_string=sample_iif_content, batch_date_str=test_batch_date, warning_message_html=sample_warning)
    print(f"IIF Batch Email Send Test Result (With Warning): {iif_email_sent_warn}")
    print("\n--- Make sure to set EMAIL_API_KEY (Postmark Server Token) and EMAIL_SENDER_ADDRESS in your .env for actual sending ---")

