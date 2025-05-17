# shipping_service.py
# PRINT DIAGNOSTIC VERSION MARKER
print("DEBUG SHIPPING_SERVICE: TOP OF FILE shipping_service.py REACHED")
print("DEBUG SHIPPING_SERVICE: --- VERSION WITH SPLIT BC SHIPMENT/STATUS UPDATE FUNCTIONS ---")

import os
import requests
import base64
from datetime import datetime, timezone
from dotenv import load_dotenv
import json

if __name__ == '__main__':
    print("DEBUG SHIPPING_SERVICE (__main__): Running standalone, loading .env")
    load_dotenv()

# --- BigCommerce Configuration (copied from your provided file) ---
APP_BC_API_URL = None
APP_BC_HEADERS = None
try:
    from app import bc_api_base_url_v2 as APP_BC_API_URL_FROM_APP, bc_headers as APP_BC_HEADERS_FROM_APP
    if APP_BC_API_URL_FROM_APP and APP_BC_HEADERS_FROM_APP:
        APP_BC_API_URL = APP_BC_API_URL_FROM_APP
        APP_BC_HEADERS = APP_BC_HEADERS_FROM_APP
        print("DEBUG SHIPPING_SERVICE: Successfully imported BC config from app.py")
except ImportError:
    print("WARN SHIPPING_SERVICE: Could not import BC config from app.py. Will rely on os.getenv for BC config.")

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
# --- End BigCommerce Configuration ---

# --- UPS Configuration (copied from your provided file) ---
UPS_CLIENT_ID = os.getenv("UPS_CLIENT_ID")
UPS_CLIENT_SECRET = os.getenv("UPS_CLIENT_SECRET")
UPS_ACCOUNT_NUMBER = os.getenv("UPS_BILLING_ACCOUNT_NUMBER")
UPS_API_ENVIRONMENT = os.getenv("UPS_API_ENVIRONMENT", "test").lower()
UPS_API_VERSION = os.getenv("UPS_API_VERSION", "v2409")

UPS_OAUTH_URL_PRODUCTION = "https://onlinetools.ups.com/security/v1/oauth/token"
UPS_OAUTH_URL_TEST = "https://wwwcie.ups.com/security/v1/oauth/token"
UPS_SHIPPING_API_URL_BASE_PRODUCTION = "https://onlinetools.ups.com/api/shipments"
UPS_SHIPPING_API_URL_BASE_TEST = "https://wwwcie.ups.com/api/shipments"
UPS_OAUTH_ENDPOINT = UPS_OAUTH_URL_TEST if UPS_API_ENVIRONMENT == "test" else UPS_OAUTH_URL_PRODUCTION
if UPS_API_ENVIRONMENT == "test":
    UPS_SHIPPING_API_ENDPOINT = f"{UPS_SHIPPING_API_URL_BASE_TEST}/{UPS_API_VERSION}/ship"
else:
    UPS_SHIPPING_API_ENDPOINT = f"{UPS_SHIPPING_API_URL_BASE_PRODUCTION}/{UPS_API_VERSION}/ship"
print(f"INFO SHIPPING_SERVICE (UPS): API Version: {UPS_API_VERSION}, Env: {UPS_API_ENVIRONMENT}, Endpoint: {UPS_SHIPPING_API_ENDPOINT}")
# --- End UPS Configuration ---

# --- Pillow/ReportLab for Image Conversion (copied from your provided file) ---
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
# --- End Image Conversion ---


def get_ups_oauth_token():
    # ... (This function remains the same as your last working version) ...
    if not all([UPS_CLIENT_ID, UPS_CLIENT_SECRET]):
        print("ERROR UPS_AUTH: UPS Client ID or Client Secret not configured.")
        return None
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    data = {"grant_type": "client_credentials"}
    auth = (UPS_CLIENT_ID, UPS_CLIENT_SECRET)
    try:
        print(f"DEBUG UPS_AUTH: Requesting OAuth token from {UPS_OAUTH_ENDPOINT}")
        response = requests.post(UPS_OAUTH_ENDPOINT, headers=headers, data=data, auth=auth)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        if access_token:
            print(f"DEBUG UPS_AUTH: Successfully obtained OAuth token. Expires in: {token_data.get('expires_in')} sec.")
            return access_token
        else:
            print(f"DEBUG UPS_AUTH: OAuth token response successful but missing 'access_token'. Full Response: {token_data}")
            return None
    except requests.exceptions.RequestException as req_e:
        status_code = req_e.response.status_code if req_e.response is not None else 'N/A'
        response_text = req_e.response.text if req_e.response is not None else 'N/A'
        print(f"ERROR UPS_AUTH: OAuth HTTP Error. Status: {status_code}, Response: {response_text[:500]}..., Exception: {req_e}")
        return None
    except Exception as e:
        print(f"ERROR UPS_AUTH: Unexpected exception during OAuth token request: {e}")
        return None

def map_shipping_method_to_ups_code(method_name_from_bc):
    method_name = method_name_from_bc.lower() if method_name_from_bc else ""
    shipping_method_mapping = {
        'ups® ground': '03', 
        'ups ground': '03',
        'ups® (ups next day air®)': '01', 
        'ups next day air': '01',
        'ups® (ups 2nd day air®)': '02', 
        'ups 2nd day air': '02',
        'ups® (ups worldwide expedited®)': '08',
        'free shipping': '03', # Assuming ground for free shipping
        # --- NEW MAPPING ---
        'ups® (ups next day air early a.m.®)': '14', # From BigCommerce format
        'ups next day air early a.m.': '14',        # Your internal/select format
        'ups next day air early am': '14'           # Common variation
    }
    # Fallback to a broader search if exact match fails
    code = shipping_method_mapping.get(method_name)
    if code is None:
        if 'next day air early' in method_name or 'early a.m.' in method_name or 'early am' in method_name : # Check for early AM variations
             code = '14'
        elif 'next day air' in method_name or 'nda' in method_name: # Check after early am
            code = '01'
        elif '2nd day air' in method_name or 'second day' in method_name:
            code = '02'
        elif 'ground' in method_name:
            code = '03'
        elif 'worldwide expedited' in method_name:
            code = '08'
        else:
            code = '03' # Default to Ground if no keywords match

    print(f"DEBUG UPS: Mapped '{method_name_from_bc}' to UPS Service Code '{code}'")
    return code

def generate_ups_label_raw(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token):
    if not access_token:
        print("ERROR UPS_LABEL_RAW: UPS Access token not provided.")
        return None, None

    bc_order_id_str = str(order_data.get('bigcommerce_order_id', 'N/A'))
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "transId": f"Order{bc_order_id_str}-{int(datetime.now(timezone.utc).timestamp()*1000)}",
        "transactionSrc": "OrderProcessingApp"
    }
    ups_service_code = map_shipping_method_to_ups_code(customer_shipping_method_name)

    # --- State Processing Logic ---
    ship_to_state_input = order_data.get('customer_shipping_state', '')
    ship_to_country_code_from_data = order_data.get('customer_shipping_country', 'US') # Default to US if not provided
    ship_to_country_code_upper = ship_to_country_code_from_data.upper() if ship_to_country_code_from_data else 'US'
    
    ship_to_state_processed = ''  # Initialize

    state_mapping = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
        "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
        "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
        "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
        "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
        "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT",
        "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
        "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND",
        "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
        "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
        "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
        "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "puerto rico": "PR",
    }
    
    # Invert the mapping to easily check if the input is already a valid 2-letter code
    valid_us_state_codes = {v: k for k, v in state_mapping.items()} # For US states

    if ship_to_country_code_upper == 'US':
        input_state_upper_stripped = ship_to_state_input.upper().strip()
        if len(input_state_upper_stripped) == 2 and input_state_upper_stripped in valid_us_state_codes:
            # Input is already a valid 2-letter US state code
            ship_to_state_processed = input_state_upper_stripped
            print(f"DEBUG UPS Payload (State): US State '{ship_to_state_input}' used as 2-letter code: {ship_to_state_processed}")
        else:
            # Try to map from full name for US state
            ship_to_state_processed = state_mapping.get(ship_to_state_input.lower().strip(), "")
            if not ship_to_state_processed:
                print(f"ERROR UPS Payload: US State '{ship_to_state_input}' could not be mapped to a 2-letter code.")
                return None, None # Critical error for US if no mapping
            else:
                print(f"DEBUG UPS Payload (State): Mapped US State '{ship_to_state_input}' to '{ship_to_state_processed}'")
    else:
        # For non-US countries, assume the input state/province is directly usable by UPS
        # Or, if it's empty for a non-US country where state is optional, UPS might accept it.
        ship_to_state_processed = ship_to_state_input.strip() 
        print(f"DEBUG UPS Payload (State): Non-US country '{ship_to_country_code_upper}'. Using state/province '{ship_to_state_processed}' as is.")
    # --- End State Processing Logic ---

    # ---- ShipTo Name and AttentionName Logic ----
    ship_to_company_name = order_data.get('customer_company', '').strip()
    # 'customer_name' in ad_hoc_order_data is set to 'attention_name' from payload, or 'name' if attention is missing
    ship_to_contact_person_name = order_data.get('customer_name', '').strip() 

    # UPS Logic: Prefer company name in ShipTo.Name if available.
    ups_ship_to_name = ship_to_company_name if ship_to_company_name else ship_to_contact_person_name
    # AttentionName should be the contact person. If no company, ShipTo.Name is already the person.
    ups_attention_name = ship_to_contact_person_name
    
    # If company name was used for ShipTo.Name, and contact name is the same,
    # UPS sometimes prefers AttentionName to be different or more specific if possible,
    # but having it the same is usually fine if it's just one person.
    # If ShipTo.Name is already the person (no company), AttentionName can be the same.
    # The current logic is generally acceptable.

    print(f"DEBUG UPS Payload Prep (ShipTo): Name: '{ups_ship_to_name}', AttentionName: '{ups_attention_name}'")
    # ---- End ShipTo Name and AttentionName Logic ----

    payload = {
        "ShipmentRequest": {
            "Request": {
                "RequestOption": "nonvalidate",
                "TransactionReference": {"CustomerContext": f"Order_{bc_order_id_str}"}
            },
            "Shipment": {
                "Description": "Computer Parts", # Consider making this dynamic if needed
                "Shipper": {
                    "Name": ship_from_address.get('name'),
                    "AttentionName": ship_from_address.get('contact_person'),
                    "Phone": {"Number": (ship_from_address.get('phone') or "").replace('-', '')},
                    "ShipperNumber": UPS_ACCOUNT_NUMBER,
                    "Address": {
                        "AddressLine": [addr for addr in [ship_from_address.get('street_1'), ship_from_address.get('street_2')] if addr and addr.strip()],
                        "City": ship_from_address.get('city'),
                        "StateProvinceCode": ship_from_address.get('state'),
                        "PostalCode": ship_from_address.get('zip'),
                        "CountryCode": ship_from_address.get('country', 'US')
                    }
                },
                "ShipTo": {
                    "Name": ups_ship_to_name,
                    "AttentionName": ups_attention_name,
                    "Phone": {"Number": (order_data.get('customer_phone') or "").replace('-', '')},
                    "Address": {
                        "AddressLine": [addr for addr in [order_data.get('customer_shipping_address_line1'), order_data.get('customer_shipping_address_line2')] if addr and addr.strip()],
                        "City": order_data.get('customer_shipping_city'),
                        "StateProvinceCode": ship_to_state_processed,  # USE THE PROCESSED STATE CODE
                        "PostalCode": order_data.get('customer_shipping_zip'),
                        "CountryCode": ship_to_country_code_upper # USE THE PROCESSED (UPPERCASED) COUNTRY CODE
                    }
                },
                "PaymentInformation": {
                    "ShipmentCharge": {
                        "Type": "01", # Bill Shipper
                        "BillShipper": {"AccountNumber": UPS_ACCOUNT_NUMBER}
                    }
                },
                "Service": {"Code": ups_service_code},
                "Package": [{
                    "Description": "Package of Computer Parts", # Consider making this dynamic if needed
                    "Packaging": {"Code": "02"}, # 02 = Customer Supplied Package
                    "PackageWeight": {
                        "UnitOfMeasurement": {"Code": "LBS"},
                        "Weight": str(round(float(max(0.1, total_weight_lbs)), 1)) # Ensure weight is at least 0.1
                    },
                    "ReferenceNumber": [{"Code": "02", "Value": str(bc_order_id_str)}] # PO Number Reference
                }]
            },
            "LabelSpecification": {
                "LabelImageFormat": {"Code": "GIF"}, # Or "PNG", "ZPL", "SPL"
                "HTTPUserAgent": "Mozilla/5.0"
                # "LabelStockSize": { "Height": "6", "Width": "4" } # Optional
            }
        }
    }

    try:
        # For detailed debugging of the payload sent to UPS:
        # print(f"DEBUG UPS_LABEL_RAW: Full Payload to UPS API: {json.dumps(payload, indent=2)}")
        response = requests.post(UPS_SHIPPING_API_ENDPOINT, headers=headers, json=payload)
        
        # Log response status and first 500 chars of text for quick diagnostics
        print(f"DEBUG UPS_LABEL_RAW: UPS API Response Status: {response.status_code}")
        # print(f"DEBUG UPS_LABEL_RAW: UPS API Response Text (first 500 chars): {response.text[:500]}")

        response.raise_for_status()  # Raises HTTPError for 4xx/5xx responses
        response_data = response.json()

        shipment_response = response_data.get("ShipmentResponse", {})
        shipment_results = shipment_response.get("ShipmentResults", {})
        
        # Check overall response status from UPS
        ups_api_response_status_obj = shipment_response.get("Response", {}).get("ResponseStatus", {})
        if ups_api_response_status_obj.get("Code") == "1":  # "1" typically means success for UPS APIs
            tracking_number = shipment_results.get("ShipmentIdentificationNumber")
            package_results_list = shipment_results.get("PackageResults", [])
            
            if package_results_list and isinstance(package_results_list, list) and package_results_list[0]:
                label_image_base64 = package_results_list[0].get("ShippingLabel", {}).get("GraphicImage")
                if label_image_base64:
                    print(f"INFO UPS_LABEL_RAW: Label generated successfully. Tracking: {tracking_number}")
                    return base64.b64decode(label_image_base64), tracking_number
            
            # If tracking number is present but no label image (should be rare with successful code "1")
            if tracking_number:
                print(f"WARN UPS_LABEL_RAW: Tracking {tracking_number} obtained, but label image data is missing from successful UPS response.")
                return None, tracking_number # Or decide if this is a hard failure (None, None)
            else:
                print(f"ERROR UPS_LABEL_RAW: UPS API success code '1' but no tracking number or label image. Full Results: {shipment_results}")
                return None, None
        else:
            # UPS API indicated an error
            error_description = ups_api_response_status_obj.get("Description", "Unknown UPS API Error")
            # UPS often puts more detailed errors in an "Error" array within "Response"
            detailed_errors = shipment_response.get("Response", {}).get("Error", [])
            error_details_str = "; ".join([f"Code {err.get('ErrorCode')}: {err.get('ErrorDescription')}" for err in detailed_errors]) if detailed_errors else "No detailed errors provided."
            
            print(f"ERROR UPS_LABEL_RAW: UPS API returned an error. Description: '{error_description}'. Details: '{error_details_str}'. Full Response: {json.dumps(response_data, indent=2)}")
            return None, None

    except requests.exceptions.HTTPError as http_err:
        error_message = f"HTTPError calling UPS API: {http_err}."
        response_text = http_err.response.text if http_err.response is not None else "No response body."
        print(f"ERROR UPS_LABEL_RAW: {error_message} Response: {response_text[:1000]}") # Log more of the response
        return None, None
    except requests.exceptions.RequestException as req_err: # More general requests error (timeout, connection error)
        print(f"ERROR UPS_LABEL_RAW: RequestException calling UPS API: {req_err}")
        return None, None
    except Exception as e:
        print(f"ERROR UPS_LABEL_RAW: Unexpected exception during UPS label generation: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def convert_image_bytes_to_pdf_bytes(image_bytes, image_format="GIF"):
    # ... (This function remains the same as your last working version) ...
    if not PILLOW_AVAILABLE: print("ERROR IMG_TO_PDF: Pillow/ReportLab not available."); return None
    try: # ... (conversion logic) ...
        img_stream = io.BytesIO(image_bytes); img = PILImage.open(img_stream)
        if hasattr(img, 'seek'): img.seek(0); img = img.convert("RGBA")
        img_width_px, img_height_px = img.size
        if img_width_px == 0 or img_height_px == 0: return None
        page_width_pt, page_height_pt = letter; margin = 1.0 * 72
        drawable_area_width = page_width_pt - (2 * margin); drawable_area_height = page_height_pt - (2 * margin)
        img_aspect_ratio = img_width_px / img_height_px
        draw_width = drawable_area_width; draw_height = draw_width / img_aspect_ratio
        if draw_height > drawable_area_height: draw_height = drawable_area_height; draw_width = draw_height * img_aspect_ratio
        x_offset = margin + (drawable_area_width - draw_width) / 2; y_offset = page_height_pt - margin - draw_height
        pdf_buffer = io.BytesIO(); c = canvas.Canvas(pdf_buffer, pagesize=letter)
        png_stream = io.BytesIO(); img.save(png_stream, format="PNG"); png_stream.seek(0)
        reportlab_image = ImageReader(png_stream)
        c.drawImage(reportlab_image, x_offset, y_offset, width=draw_width, height=draw_height, mask='auto', preserveAspectRatio=True)
        c.showPage(); c.save(); pdf_bytes_out = pdf_buffer.getvalue(); pdf_buffer.close(); png_stream.close(); img_stream.close()
        return pdf_bytes_out
    except Exception as e: print(f"ERROR IMG_TO_PDF: {e}"); import traceback; traceback.print_exc(); return None

def generate_ups_label(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name):
    # ... (This function remains the same: calls get_ups_oauth_token, generate_ups_label_raw, convert_image_bytes_to_pdf_bytes) ...
    print(f"DEBUG UPS: Attempting label for order {order_data.get('bigcommerce_order_id', 'N/A')}, weight {total_weight_lbs}, method '{customer_shipping_method_name}'")
    access_token = get_ups_oauth_token()
    if not access_token: print("ERROR UPS: Failed to get OAuth token."); return None, None
    raw_gif_bytes, tracking_number = generate_ups_label_raw(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token)
    if not raw_gif_bytes and not tracking_number: return None, None
    if not raw_gif_bytes and tracking_number: print(f"WARN UPS: Got tracking {tracking_number}, but no label image."); return None, tracking_number # Or None, None
    final_label_pdf_bytes = convert_image_bytes_to_pdf_bytes(raw_gif_bytes, image_format="GIF")
    if not final_label_pdf_bytes: print("ERROR UPS: GIF to PDF conversion failed."); return None, tracking_number # Return tracking even if PDF fails
    if tracking_number and final_label_pdf_bytes: return final_label_pdf_bytes, tracking_number
    return None, None # Fallback


# --- NEW: Function to ONLY create a shipment in BigCommerce ---
def create_bigcommerce_shipment(bigcommerce_order_id, tracking_number, shipping_method_name, line_items_in_shipment, order_address_id, comments=None, shipping_provider=None):
    """
    Creates a shipment record in BigCommerce for the given order.
    Does NOT change the overall order status.
    `line_items_in_shipment` should be a list of dicts: [{"order_product_id": X, "quantity": Y}, ...]
    `order_address_id` is the ID of the shipping address for the order.
    """
    print(f"DEBUG BC_CREATE_SHIPMENT: Creating shipment for BC Order {bigcommerce_order_id} with tracking {tracking_number}")
    if not CURRENT_BC_API_BASE_URL_V2 or not CURRENT_BC_HEADERS or not CURRENT_BC_HEADERS.get("X-Auth-Token"):
        print("ERROR BC_CREATE_SHIPMENT: BigCommerce API base URL or headers not configured."); return False
    if not all([bigcommerce_order_id, tracking_number, line_items_in_shipment]) or order_address_id is None: # order_address_id can be 0
        print(f"ERROR BC_CREATE_SHIPMENT: Missing required arguments. OrderID: {bigcommerce_order_id}, Tracking: {tracking_number}, Items: {bool(line_items_in_shipment)}, AddressID: {order_address_id}"); return False

    shipments_url = f"{CURRENT_BC_API_BASE_URL_V2}orders/{bigcommerce_order_id}/shipments"
    
    tracking_carrier = "" # Determine carrier based on method_name
    sm_lower = (shipping_method_name or "").lower()
    if "ups" in sm_lower: tracking_carrier = "ups"
    elif "fedex" in sm_lower: tracking_carrier = "fedex"
    elif "usps" in sm_lower: tracking_carrier = "usps"
    # Add more or default if needed

    shipment_payload = {
        "order_address_id": int(order_address_id),
        "tracking_number": str(tracking_number),
        "items": line_items_in_shipment 
    }
    # These fields are optional for BC shipment creation API
    if shipping_method_name: shipment_payload["shipping_method"] = str(shipping_method_name)
    if tracking_carrier: shipment_payload["tracking_carrier"] = tracking_carrier
    if comments: shipment_payload["comments"] = comments
    if shipping_provider: shipment_payload["shipping_provider"] = shipping_provider # e.g., "auspost", "canadapost" etc.

    try:
        print(f"DEBUG BC_CREATE_SHIPMENT: POST to {shipments_url} with payload: {json.dumps(shipment_payload)}")
        response = requests.post(shipments_url, headers=CURRENT_BC_HEADERS, json=shipment_payload)
        print(f"DEBUG BC_CREATE_SHIPMENT: Response Status: {response.status_code}, Response Text: {response.text[:500]}")
        response.raise_for_status() # Will raise HTTPError for bad responses (4xx or 5xx)
        shipment_creation_data = response.json()
        print(f"INFO BC_CREATE_SHIPMENT: Shipment created successfully for BC Order {bigcommerce_order_id}. Shipment ID: {shipment_creation_data.get('id')}")
        return True
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR BC_CREATE_SHIPMENT: HTTPError creating BC shipment for {bigcommerce_order_id}: {http_err}. Response: {http_err.response.text if http_err.response else 'No response'}")
        return False
    except Exception as e:
        print(f"ERROR BC_CREATE_SHIPMENT: Unexpected error creating BC shipment for {bigcommerce_order_id}: {e}")
        import traceback; traceback.print_exc(); return False

# --- NEW: Function to ONLY set the BigCommerce order status ---
def set_bigcommerce_order_status(bigcommerce_order_id, status_id):
    """
    Updates the status of a BigCommerce order.
    """
    print(f"DEBUG BC_SET_STATUS: Setting status for BC Order {bigcommerce_order_id} to ID {status_id}")
    if not CURRENT_BC_API_BASE_URL_V2 or not CURRENT_BC_HEADERS or not CURRENT_BC_HEADERS.get("X-Auth-Token"):
        print("ERROR BC_SET_STATUS: BigCommerce API base URL or headers not configured."); return False
    if not bigcommerce_order_id or status_id is None: # status_id can be 0, check for None
        print(f"ERROR BC_SET_STATUS: Missing bigcommerce_order_id or status_id."); return False

    order_update_url = f"{CURRENT_BC_API_BASE_URL_V2}orders/{bigcommerce_order_id}"
    status_update_payload = {"status_id": int(status_id)}
    
    try:
        print(f"DEBUG BC_SET_STATUS: PUT to {order_update_url} with payload: {json.dumps(status_update_payload)}")
        response = requests.put(order_update_url, headers=CURRENT_BC_HEADERS, json=status_update_payload)
        print(f"DEBUG BC_SET_STATUS: Response Status: {response.status_code}, Response Text: {response.text[:500]}")
        response.raise_for_status()
        print(f"INFO BC_SET_STATUS: BC Order {bigcommerce_order_id} status updated successfully to {status_id}.")
        return True
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR BC_SET_STATUS: HTTPError setting BC order status for {bigcommerce_order_id}: {http_err}. Response: {http_err.response.text if http_err.response else 'No response'}")
        return False
    except Exception as e:
        print(f"ERROR BC_SET_STATUS: Unexpected error setting BC order status for {bigcommerce_order_id}: {e}")
        import traceback; traceback.print_exc(); return False


# Comment out or remove the old combined update_bigcommerce_order function if it's no longer needed
# def update_bigcommerce_order(bigcommerce_order_id, tracking_number, shipping_method_name, line_items_shipped, order_address_id, shipped_status_id):
#     # This was the old function that did both shipment creation and status update.
#     # It's being replaced by create_bigcommerce_shipment and set_bigcommerce_order_status
#     print(f"DEBUG SHIPPING_SERVICE (BC_UPDATE_OLD): Called OLD update_bigcommerce_order for {bigcommerce_order_id}")
#     # For now, let's just return False to indicate it shouldn't be used or needs refactoring
#     # if called accidentally.
#     return False


if __name__ == '__main__':
    print("--- Testing shipping_service.py (ensure .env is in this directory or parent for standalone tests) ---")
    # Example:
    # test_order_id = "12345" # Replace with a real test order ID from your BC sandbox
    # test_tracking = "TESTTRACK12345"
    # test_method = "UPS Ground"
    # test_items = [{"order_product_id": 678, "quantity": 1}] # Get a real order_product_id
    # test_address_id = 0 # Get a real shipping address ID for that order
    # test_status_id_completed = 11 # Example: "Completed" status ID in BC

    # if CURRENT_BC_API_BASE_URL_V2 and CURRENT_BC_HEADERS:
    #     print(f"\n--- Testing create_bigcommerce_shipment for Order ID: {test_order_id} ---")
    #     shipment_created = create_bigcommerce_shipment(test_order_id, test_tracking, test_method, test_items, test_address_id)
    #     print(f"Shipment Creation Test Result: {shipment_created}")

    #     if shipment_created: # Only try to set status if shipment was made (or test separately)
    #         print(f"\n--- Testing set_bigcommerce_order_status for Order ID: {test_order_id} ---")
    #         status_set = set_bigcommerce_order_status(test_order_id, test_status_id_completed)
    #         print(f"Set Order Status Test Result: {status_set}")
    # else:
    #     print("\nSkipping BigCommerce live tests as API is not configured at module level.")

    print(f"--- UPS Endpoints based on UPS_API_ENVIRONMENT: {UPS_API_ENVIRONMENT} ---")
    print(f"--- OAuth URL: {UPS_OAUTH_ENDPOINT} ---")
    print(f"--- Shipping URL: {UPS_SHIPPING_API_ENDPOINT} ---")
    pass