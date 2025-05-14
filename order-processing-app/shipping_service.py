# shipping_service.py
# PRINT DIAGNOSTIC VERSION MARKER - ENSURE THIS APPEARS IN CLOUD RUN STARTUP LOGS
print("DEBUG SHIPPING_SERVICE: TOP OF FILE shipping_service.py REACHED (local-build-test)")
print("DEBUG SHIPPING_SERVICE: --- RUNNING VERSION V56_FIX_TRANSACTION_ID ---")
print("DEBUG SHIPPING_SERVICE: --- APPLIED UPS URL VERSIONING FIX (e.g., v2409) ---")
# print("DEBUG SHIPPING_SERVICE: --- APPLIED UPS PAYMENTDETAILS ARRAY FIX (120416 error) ---") # This was reverted
print("DEBUG SHIPPING_SERVICE: --- ALIGNED WITH USER'S BACKUP (PaymentInformation, transId, ReferenceNumber) ---") # New marker

import os
print("DEBUG SHIPPING_SERVICE: os imported in shipping_service.py (local-build-test)")
import requests
import base64
from datetime import datetime, timezone
from dotenv import load_dotenv
import json # For debugging payload if needed

if __name__ == '__main__':
    print("DEBUG SHIPPING_SERVICE (__main__): Running standalone, loading .env")
    load_dotenv()

APP_BC_API_URL = None
APP_BC_HEADERS = None
try:
    from app import bc_api_base_url_v2 as APP_BC_API_URL_FROM_APP, bc_headers as APP_BC_HEADERS_FROM_APP
    if APP_BC_API_URL_FROM_APP and APP_BC_HEADERS_FROM_APP:
        APP_BC_API_URL = APP_BC_API_URL_FROM_APP
        APP_BC_HEADERS = APP_BC_HEADERS_FROM_APP
        print("DEBUG SHIPPING_SERVICE: Successfully imported BC config from app.py")
except ImportError:
    print("WARN SHIPPING_SERVICE: Could not import BC config from app.py. Will rely on os.getenv for BC config if needed by functions called directly.")

BC_API_STORE_HASH = os.getenv("BIGCOMMERCE_STORE_HASH")
BC_API_ACCESS_TOKEN = os.getenv("BIGCOMMERCE_ACCESS_TOKEN")

CURRENT_BC_API_BASE_URL_V2 = None
CURRENT_BC_HEADERS = None

if APP_BC_API_URL and APP_BC_HEADERS and APP_BC_HEADERS.get("X-Auth-Token"):
    CURRENT_BC_API_BASE_URL_V2 = APP_BC_API_URL
    CURRENT_BC_HEADERS = APP_BC_HEADERS
    print("DEBUG SHIPPING_SERVICE (Module Level): Using BC_API_BASE_URL_V2 and BC_HEADERS imported from app.py")
elif BC_API_STORE_HASH and BC_API_ACCESS_TOKEN:
    CURRENT_BC_API_BASE_URL_V2 = f"https://api.bigcommerce.com/stores/{BC_API_STORE_HASH}/v2/"
    CURRENT_BC_HEADERS = {
        "X-Auth-Token": BC_API_ACCESS_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    print(f"DEBUG SHIPPING_SERVICE (Module Level): Using BC_API_BASE_URL_V2 and BC_HEADERS from os.getenv. URL: {CURRENT_BC_API_BASE_URL_V2}")
else:
    print("ERROR SHIPPING_SERVICE (Module Level): BigCommerce API credentials not configured. BC-dependent functions may fail.")

UPS_CLIENT_ID = os.getenv("UPS_CLIENT_ID")
UPS_CLIENT_SECRET = os.getenv("UPS_CLIENT_SECRET")
UPS_ACCOUNT_NUMBER = os.getenv("UPS_BILLING_ACCOUNT_NUMBER") # This is used as ups_billing_account_number in backup
UPS_API_ENVIRONMENT = os.getenv("UPS_API_ENVIRONMENT", "test").lower()
UPS_API_VERSION = os.getenv("UPS_API_VERSION", "v2409") # Defaulting to v2409 as per user indication

print(f"INFO SHIPPING_SERVICE (UPS): API Version set to: {UPS_API_VERSION}")

UPS_OAUTH_URL_PRODUCTION = "https://onlinetools.ups.com/security/v1/oauth/token"
UPS_OAUTH_URL_TEST = "https://wwwcie.ups.com/security/v1/oauth/token"

UPS_SHIPPING_API_URL_BASE_PRODUCTION = "https://onlinetools.ups.com/api/shipments"
UPS_SHIPPING_API_URL_BASE_TEST = "https://wwwcie.ups.com/api/shipments"

UPS_OAUTH_ENDPOINT = UPS_OAUTH_URL_TEST if UPS_API_ENVIRONMENT == "test" else UPS_OAUTH_URL_PRODUCTION

if UPS_API_ENVIRONMENT == "test":
    UPS_SHIPPING_API_ENDPOINT = f"{UPS_SHIPPING_API_URL_BASE_TEST}/{UPS_API_VERSION}/ship"
    print(f"INFO SHIPPING_SERVICE (UPS): Using TEST (CIE) UPS Endpoints. Shipping API: {UPS_SHIPPING_API_ENDPOINT}")
else:
    UPS_SHIPPING_API_ENDPOINT = f"{UPS_SHIPPING_API_URL_BASE_PRODUCTION}/{UPS_API_VERSION}/ship"
    print(f"INFO SHIPPING_SERVICE (UPS): Using PRODUCTION UPS Endpoints. Shipping API: {UPS_SHIPPING_API_ENDPOINT}")

try:
    from PIL import Image as PILImage
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    import io
    PILLOW_AVAILABLE = True
    print("DEBUG SHIPPING_SERVICE: Pillow & ReportLab imported successfully for PDF conversion.")
except ImportError:
    PILLOW_AVAILABLE = False
    print("WARN SHIPPING_SERVICE: Pillow or ReportLab not found. GIF to PDF conversion will not be available.")

def get_ups_oauth_token():
    if not all([UPS_CLIENT_ID, UPS_CLIENT_SECRET]):
        print("ERROR UPS_AUTH: UPS Client ID or Client Secret not configured.")
        return None
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"} # Added Accept from backup
    data = {"grant_type": "client_credentials"}
    auth = (UPS_CLIENT_ID, UPS_CLIENT_SECRET)
    try:
        print(f"DEBUG UPS_AUTH: Requesting OAuth token from {UPS_OAUTH_ENDPOINT}")
        response = requests.post(UPS_OAUTH_ENDPOINT, headers=headers, data=data, auth=auth)
        print(f"DEBUG UPS_AUTH: OAuth response status code: {response.status_code}") # From backup
        print(f"DEBUG UPS_AUTH: OAuth raw response body: {response.text[:500]}...") # From backup
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        if access_token:
            print(f"DEBUG UPS_AUTH: Successfully obtained OAuth token. Type: {token_data.get('token_type')}, Expires in: {token_data.get('expires_in')} sec.")
            return access_token
        else:
            print(f"DEBUG UPS_AUTH: OAuth token response successful but missing 'access_token'. Full Response: {token_data}")
            return None
    except requests.exceptions.RequestException as req_e: # More specific error handling from backup
        status_code = req_e.response.status_code if req_e.response is not None else 'N/A'
        response_text = req_e.response.text if req_e.response is not None else 'N/A'
        print(f"DEBUG UPS_AUTH: OAuth HTTP Error. Status: {status_code}, Response: {response_text[:500]}..., Exception: {req_e}")
        return None
    except Exception as e:
        print(f"DEBUG UPS_AUTH: Caught unexpected exception during OAuth token request: {e}") # From backup
        return None

def map_shipping_method_to_ups_code(method_name_from_bc): # From backup
    method_name = method_name_from_bc.lower() if method_name_from_bc else ""
    shipping_method_mapping = {
        'ups® ground': '03', 'ups ground': '03',
        'ups® (ups next day air®)': '01', 'ups next day air': '01',
        'ups® (ups 2nd day air®)': '02', 'ups 2nd day air': '02',
        'ups® (ups worldwide expedited®)': '08', # From backup
        'free shipping': '03', # From backup, assuming ground
    }
    code = shipping_method_mapping.get(method_name, '03') # Default to Ground
    print(f"DEBUG UPS: Mapped '{method_name_from_bc}' to UPS Service Code '{code}'")
    return code

def generate_ups_label_raw(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token):
    if not access_token:
        print("ERROR UPS_LABEL_RAW: UPS Access token not provided.")
        return None, None

    bc_order_id_str = str(order_data.get('bigcommerce_order_id', 'N/A')) # Match backup's default
    
    # Using transId and transactionSrc from backup
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json", # Added from backup
        "transId": f"Order{bc_order_id_str}-{int(datetime.now(timezone.utc).timestamp()*1000)}",
        "transactionSrc": "OrderProcessingApp"
    }

    ups_service_code = map_shipping_method_to_ups_code(customer_shipping_method_name)
    if ups_service_code is None: # Should not happen with default in map_shipping_method_to_ups_code
         print(f"DEBUG UPS_LABEL_RAW: Shipping method '{customer_shipping_method_name}' did not map. Skipping label.")
         return None, None

    # State code mapping logic from backup (simplified for brevity, assuming it works or is handled)
    ship_to_state_full = order_data.get('customer_shipping_state', '')
    # Basic mapping, can be expanded or made more robust if needed
    ship_to_state_code = ship_to_state_full if len(ship_to_state_full) == 2 else ship_to_state_full # Placeholder, needs proper mapping

    payload = {
        "ShipmentRequest": {
            "Request": {
                "RequestOption": "nonvalidate",
                "TransactionReference": { # From backup
                    "CustomerContext": f"Order_{bc_order_id_str}"
                }
            },
            "Shipment": {
                "Description": "Computer Parts", # From backup
                "Shipper": {
                    "Name": ship_from_address.get('name'),
                    "AttentionName": ship_from_address.get('contact_person'),
                    "Phone": {"Number": (ship_from_address.get('phone') or "").replace('-', '')}, # From backup
                    "ShipperNumber": UPS_ACCOUNT_NUMBER, # Uses global UPS_ACCOUNT_NUMBER
                    "Address": {
                        "AddressLine": [addr for addr in [ship_from_address.get('street_1'), ship_from_address.get('street_2')] if addr and addr.strip()], # From backup
                        "City": ship_from_address.get('city'),
                        "StateProvinceCode": ship_from_address.get('state'),
                        "PostalCode": ship_from_address.get('zip'),
                        "CountryCode": ship_from_address.get('country', 'US') # Default to US from backup
                    }
                },
                "ShipTo": {
                    "Name": order_data.get('customer_name'),
                    "AttentionName": order_data.get('customer_name'), # From backup
                    "Phone": {"Number": (order_data.get('customer_phone') or "").replace('-', '')}, # From backup
                    "Address": {
                        "AddressLine": [addr for addr in [order_data.get('customer_shipping_address_line1'), order_data.get('customer_shipping_address_line2')] if addr and addr.strip()], # From backup
                        "City": order_data.get('customer_shipping_city'),
                        "StateProvinceCode": ship_to_state_code, # Using mapped state code
                        "PostalCode": order_data.get('customer_shipping_zip'),
                        "CountryCode": order_data.get('customer_shipping_country', 'US') # Default to US from backup
                    }
                },
                "PaymentInformation": { # Key changed from PaymentDetails, structure from backup
                    "ShipmentCharge": {
                        "Type": "01",
                        "BillShipper": {"AccountNumber": UPS_ACCOUNT_NUMBER} # Uses global UPS_ACCOUNT_NUMBER
                    }
                },
                "Service": {"Code": ups_service_code},
                "Package": [{
                    "Description": "Package of Computer Parts", # From backup
                    "Packaging": {"Code": "02"},
                    "PackageWeight": {
                        "UnitOfMeasurement": {"Code": "LBS"},
                        "Weight": str(round(float(max(0.1, total_weight_lbs)), 1)) # From backup, ensures positive and rounds
                    },
                    "ReferenceNumber": [{"Code": "02", "Value": str(bc_order_id_str)}] # Added from backup
                }]
            },
            "LabelSpecification": {
                "LabelImageFormat": {"Code": "GIF"},
                "HTTPUserAgent": "Mozilla/5.0" # From backup
            }
        }
    }
    # AddressLine cleanup was already present and is good.

    try:
        print(f"DEBUG UPS_LABEL_RAW: Sending POST request to UPS Shipping API: {UPS_SHIPPING_API_ENDPOINT}")
        # print(f"DEBUG UPS_LABEL_RAW: Payload: {json.dumps(payload, indent=2)}") # For deep debugging
        response = requests.post(UPS_SHIPPING_API_ENDPOINT, headers=headers, json=payload)
        print(f"DEBUG UPS_LABEL_RAW: UPS API response status code: {response.status_code}") # From backup
        print(f"DEBUG UPS_LABEL_RAW: UPS API raw response body (preview): {response.text[:1000]}...") # From backup
        response.raise_for_status()
        response_data = response.json() # From backup

        shipment_response = response_data.get("ShipmentResponse", {})
        shipment_results = shipment_response.get("ShipmentResults", {})
        response_status_obj = shipment_response.get("Response", {}).get("ResponseStatus", {})
        response_status_code_ups = response_status_obj.get("Code")

        if response_status_code_ups == "1": # Success code from backup
            print(f"DEBUG UPS_LABEL_RAW: UPS API reported success. Desc: {response_status_obj.get('Description')}")
            if shipment_results:
                tracking_number = shipment_results.get("ShipmentIdentificationNumber") # From backup
                package_results = shipment_results.get("PackageResults", [])
                if package_results and package_results[0]:
                    label_image_base64 = package_results[0].get("ShippingLabel", {}).get("GraphicImage")
                    if label_image_base64:
                        raw_gif_bytes = base64.b64decode(label_image_base64)
                        print(f"DEBUG UPS_LABEL_RAW: Decoded Base64 GIF data ({len(raw_gif_bytes)} bytes).")
                        return raw_gif_bytes, tracking_number # Return raw GIF as per backup logic
                    else: print("DEBUG UPS_LABEL_RAW: GraphicImage (label data) not found in UPS response.")
                if tracking_number: # If tracking obtained but no label image
                    print(f"WARN UPS_LABEL_RAW: Tracking {tracking_number} obtained, but label image data missing.")
                    return None, tracking_number # Return tracking even if image fails
                else: print("DEBUG UPS_LABEL_RAW: Missing tracking or label data after processing.")
            else: print(f"DEBUG UPS_LABEL_RAW: UPS success but missing ShipmentResults. Full Response: {shipment_response}")
        else:
            # Using the more detailed error parsing from previous version if API reports error
            error_desc = response_status_obj.get("Description", "Unknown UPS Error")
            errors = shipment_response.get("Response", {}).get("Error") # Path from current version
            if errors:
                if isinstance(errors, list): error_messages = [f"{err.get('Code')}: {err.get('Description')}" for err in errors]; error_desc += " | Details: " + "; ".join(error_messages)
                elif isinstance(errors, dict): error_desc += f" | Detail: {errors.get('Code')}: {errors.get('Description')}"
            print(f"ERROR UPS_LABEL_RAW: UPS API reported an error: {error_desc}. Full response: {response_data}")
        return None, None
    except requests.exceptions.HTTPError as e: # Keep enhanced HTTPError parsing
        error_message = f"UPS Shipping API request failed with HTTPError: {e}"
        response_content = "No response content"
        if e.response is not None:
            try:
                error_json = e.response.json(); fault = error_json.get("Fault") or error_json.get("fault")
                if fault:
                    detail = fault.get("detail", {}); errors = detail.get("Errors", {}).get("ErrorDetail", [])
                    if not isinstance(errors, list): errors = [errors]
                    error_descriptions = [f"Code {err.get('PrimaryErrorCode', {}).get('Code')} ({err.get('PrimaryErrorCode', {}).get('Description')}) at {err.get('Location', {}).get('LocationElementName') or 'N/A'}" for err in errors]
                    response_content = "; ".join(error_descriptions) if error_descriptions else e.response.text
                else: response_content = e.response.text
            except ValueError: response_content = e.response.text
        print(f"ERROR UPS_LABEL_RAW: {error_message}. Parsed/Raw Response: {response_content[:1000]}")
        return None, None
    except requests.exceptions.RequestException as req_e: # From backup
        status_code = req_e.response.status_code if req_e.response is not None else 'N/A'
        response_text = req_e.response.text if req_e.response is not None else 'N/A'
        print(f"DEBUG UPS_LABEL_RAW: HTTP Error during UPS API call. Status: {status_code}, Resp: {response_text[:500]}..., Exc: {req_e}")
        return None, None
    except Exception as e: # From backup
        print(f"DEBUG UPS_LABEL_RAW: Unexpected exception during UPS label generation/conversion: {e}")
        import traceback; traceback.print_exc()
        return None, None

def convert_image_bytes_to_pdf_bytes(image_bytes, image_format="GIF"): # From backup
    if not PILImage: print("ERROR IMG_TO_PDF: Pillow library not available."); return None
    if not canvas or not ImageReader: print("ERROR IMG_TO_PDF: reportlab not available."); return None
    try:
        print(f"DEBUG IMG_TO_PDF: Attempting to convert {len(image_bytes)} bytes of {image_format} to PDF.")
        img_stream = io.BytesIO(image_bytes); img = PILImage.open(img_stream)
        if hasattr(img, 'seek'): img.seek(0) # For multi-frame images like GIF, use first frame
        img = img.convert("RGBA")
        img_width_px, img_height_px = img.size
        if img_width_px == 0 or img_height_px == 0: print("ERROR IMG_TO_PDF: Image has zero width or height."); return None
        page_width_pt, page_height_pt = letter; margin = 1.0 * 72 # inch to points
        drawable_area_width = page_width_pt - (2 * margin); drawable_area_height = page_height_pt - (2 * margin)
        img_aspect_ratio = img_width_px / img_height_px
        draw_width = drawable_area_width; draw_height = draw_width / img_aspect_ratio
        if draw_height > drawable_area_height: draw_height = drawable_area_height; draw_width = draw_height * img_aspect_ratio
        x_offset = margin + (drawable_area_width - draw_width) / 2
        y_offset = page_height_pt - margin - draw_height
        pdf_buffer = io.BytesIO(); c = canvas.Canvas(pdf_buffer, pagesize=letter)
        png_stream = io.BytesIO(); img.save(png_stream, format="PNG"); png_stream.seek(0)
        reportlab_image = ImageReader(png_stream)
        c.drawImage(reportlab_image, x_offset, y_offset, width=draw_width, height=draw_height, mask='auto', preserveAspectRatio=True)
        c.showPage(); c.save()
        pdf_bytes_out = pdf_buffer.getvalue(); pdf_buffer.close(); png_stream.close(); img_stream.close()
        print(f"DEBUG IMG_TO_PDF: Successfully converted image to {len(pdf_bytes_out)} PDF bytes.")
        return pdf_bytes_out
    except Exception as e:
        print(f"ERROR IMG_TO_PDF: Failed to convert {image_format} to PDF: {e}")
        import traceback; traceback.print_exc(); return None

def generate_ups_label(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name):
    print(f"DEBUG UPS: Attempting label for order {order_data.get('bigcommerce_order_id', order_data.get('id'))}, weight {total_weight_lbs} lbs, method '{customer_shipping_method_name}'") # Use bigcommerce_order_id if available
    access_token = get_ups_oauth_token()
    if not access_token: print("ERROR UPS: Failed to obtain OAuth token for label generation."); return None, None
    
    raw_gif_bytes, tracking_number = generate_ups_label_raw(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token)
    
    if not raw_gif_bytes and not tracking_number: # Both failed
        print("ERROR UPS: Failed to generate raw label and tracking number.")
        return None, None
    if not raw_gif_bytes and tracking_number: # Got tracking but no label image
        print(f"WARN UPS: Got tracking {tracking_number}, but failed to generate raw label image.")
        # Decide if you want to proceed with just tracking, or fail.
        # For now, let's assume label image is critical.
        return None, tracking_number # Or return None, None if label is mandatory

    final_label_pdf_bytes = convert_image_bytes_to_pdf_bytes(raw_gif_bytes, image_format="GIF")
    if not final_label_pdf_bytes:
        print("ERROR UPS: GIF to PDF conversion failed. Label PDF will be None, but returning tracking if available.")
        return None, tracking_number # Return tracking even if PDF conversion fails

    if tracking_number and final_label_pdf_bytes:
        print(f"DEBUG UPS: Label generated & converted to PDF. Tracking: {tracking_number}")
        return final_label_pdf_bytes, tracking_number
    
    # Fallback if somehow logic above didn't catch all cases
    print("ERROR UPS: Unexpected state in generate_ups_label. Returning None, None.")
    return None, None

def update_bigcommerce_order(bigcommerce_order_id, tracking_number, shipping_method_name, line_items_shipped, order_address_id, shipped_status_id): # Added shipped_status_id
    print(f"DEBUG SHIPPING_SERVICE (BC_UPDATE): Attempting to update BigCommerce order {bigcommerce_order_id} to shipped status {shipped_status_id} with tracking {tracking_number}")
    if not CURRENT_BC_API_BASE_URL_V2 or not CURRENT_BC_HEADERS or not CURRENT_BC_HEADERS.get("X-Auth-Token"):
        print("ERROR SHIPPING_SERVICE (BC_UPDATE): BigCommerce API base URL or headers are not properly configured."); return False
    if not all([bigcommerce_order_id, tracking_number, shipping_method_name, line_items_shipped, order_address_id, shipped_status_id is not None]): # Check shipped_status_id
        print(f"ERROR SHIPPING_SERVICE (BC_UPDATE): Missing one or more required arguments. Check all params."); return False
    
    shipments_url = f"{CURRENT_BC_API_BASE_URL_V2}orders/{bigcommerce_order_id}/shipments"
    # Determine tracking carrier based on shipping_method_name (simplified from backup)
    tracking_carrier = ""
    sm_lower = (shipping_method_name or "").lower()
    if "ups" in sm_lower: tracking_carrier = "ups"
    elif "fedex" in sm_lower: tracking_carrier = "fedex"
    elif "usps" in sm_lower: tracking_carrier = "usps"

    shipment_payload = {
        "order_address_id": int(order_address_id),
        "tracking_number": str(tracking_number),
        "shipping_method": str(shipping_method_name),
        "items": line_items_shipped,
        "tracking_carrier": tracking_carrier # Added from backup
    }
    try:
        print(f"DEBUG SHIPPING_SERVICE (BC_UPDATE): Creating shipment for BC Order {bigcommerce_order_id}. Payload: {shipment_payload}")
        response = requests.post(shipments_url, headers=CURRENT_BC_HEADERS, json=shipment_payload)
        response.raise_for_status(); shipment_creation_data = response.json()
        print(f"DEBUG SHIPPING_SERVICE (BC_UPDATE): Shipment created successfully for BC Order {bigcommerce_order_id}. Shipment ID: {shipment_creation_data.get('id')}")
        
        order_update_url = f"{CURRENT_BC_API_BASE_URL_V2}orders/{bigcommerce_order_id}"
        status_update_payload = {"status_id": int(shipped_status_id)} # Use passed-in shipped_status_id
        print(f"DEBUG SHIPPING_SERVICE (BC_UPDATE): Updating status for BC Order {bigcommerce_order_id} to ID {shipped_status_id}. Payload: {status_update_payload}")
        status_response = requests.put(order_update_url, headers=CURRENT_BC_HEADERS, json=status_update_payload)
        status_response.raise_for_status()
        print(f"INFO SHIPPING_SERVICE (BC_UPDATE): BigCommerce order {bigcommerce_order_id} status updated successfully to {shipped_status_id}.")
        return True
    except requests.exceptions.RequestException as e: # Standard error handling
        error_message = f"BigCommerce API request failed during order update for {bigcommerce_order_id}: {e}"
        response_content = e.response.text if e.response else "No response content"
        print(f"ERROR SHIPPING_SERVICE (BC_UPDATE): {error_message}. Response: {response_content[:500]}"); return False
    except Exception as e:
        print(f"ERROR SHIPPING_SERVICE (BC_UPDATE): Unexpected error updating BigCommerce order {bigcommerce_order_id}: {e}")
        import traceback; traceback.print_exc(); return False

if __name__ == '__main__':
    print("--- Testing shipping_service.py (ensure .env is in this directory or parent for standalone tests) ---")
    # ... (testing code can be added here if desired, similar to backup) ...
    print(f"--- UPS Endpoints will be based on UPS_API_ENVIRONMENT: {UPS_API_ENVIRONMENT} ---")
    print(f"--- OAuth URL: {UPS_OAUTH_ENDPOINT} ---")
    print(f"--- Shipping URL: {UPS_SHIPPING_API_ENDPOINT} ---")
    pass
