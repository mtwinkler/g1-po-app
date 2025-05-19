# shipping_service.py
# PRINT DIAGNOSTIC VERSION MARKER
print("DEBUG SHIPPING_SERVICE: TOP OF FILE shipping_service.py REACHED")
print("DEBUG SHIPPING_SERVICE: --- VERSION WITH LABEL TOP ALIGN & CONDITIONAL UPS PAYMENT ---")

import os
import requests
import base64
from datetime import datetime, timezone
from dotenv import load_dotenv 
import json
import traceback

# --- LOAD DOTENV AT THE VERY TOP FOR STANDALONE EXECUTION ---
if __name__ == '__main__':
    print("DEBUG SHIPPING_SERVICE (Top-Level Pre-Config): Running standalone, attempting to load .env.")
    if os.path.exists('.env'):
        load_dotenv(dotenv_path='.env')
        print("DEBUG SHIPPING_SERVICE (Top-Level Pre-Config): Loaded .env from current directory for standalone run.")
    elif os.path.exists('../.env'):
        load_dotenv(dotenv_path='../.env')
        print("DEBUG SHIPPING_SERVICE (Top-Level Pre-Config): Loaded .env from parent directory for standalone run.")
    else:
        print("WARN SHIPPING_SERVICE (Top-Level Pre-Config): .env file not found for standalone run. Relying on pre-set environment.")
else:
    print("DEBUG SHIPPING_SERVICE (Top-Level Pre-Config): Imported by another module. Assuming .env already loaded by caller.")
# --- END OF TOP-LEVEL DOTENV LOADING ---

# --- BigCommerce Configuration ---
APP_BC_API_URL = None
APP_BC_HEADERS = None
try:
    from app import bc_api_base_url_v2 as APP_BC_API_URL_FROM_APP, bc_headers as APP_BC_HEADERS_FROM_APP
    if APP_BC_API_URL_FROM_APP and APP_BC_HEADERS_FROM_APP:
        APP_BC_API_URL = APP_BC_API_URL_FROM_APP
        APP_BC_HEADERS = APP_BC_HEADERS_FROM_APP
        print("DEBUG SHIPPING_SERVICE (Module Level): Successfully imported BC config from app.py")
except ImportError:
    print("WARN SHIPPING_SERVICE (Module Level): Could not import BC config from app.py. Will rely on os.getenv for BC config when run standalone.")

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

# --- UPS Configuration ---
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
print(f"INFO SHIPPING_SERVICE (UPS): API Version: {UPS_API_VERSION}, Env: {UPS_API_ENVIRONMENT}, OAuth Endpoint: {UPS_OAUTH_ENDPOINT}, Ship Endpoint: {UPS_SHIPPING_API_ENDPOINT}")
# --- End UPS Configuration ---

# --- FedEx API Configuration ---
FEDEX_API_KEY = os.getenv("FEDEX_API_KEY_SANDBOX")
FEDEX_SECRET_KEY = os.getenv("FEDEX_SECRET_KEY_SANDBOX")
FEDEX_SHIPPER_ACCOUNT_NUMBER = os.getenv("FEDEX_ACCOUNT_NUMBER_SANDBOX")
FEDEX_GRANT_TYPE = os.getenv("FEDEX_GRANT_TYPE", "client_credentials")
FEDEX_CHILD_KEY = os.getenv("FEDEX_CHILD_KEY_SANDBOX")
FEDEX_CHILD_SECRET = os.getenv("FEDEX_CHILD_SECRET_SANDBOX")
FEDEX_API_ENVIRONMENT = os.getenv("FEDEX_API_ENVIRONMENT", "sandbox").lower()

if FEDEX_API_ENVIRONMENT == "production":
    FEDEX_API_KEY_PROD = os.getenv("FEDEX_API_KEY_PRODUCTION")
    FEDEX_SECRET_KEY_PROD = os.getenv("FEDEX_SECRET_KEY_PRODUCTION")
    FEDEX_SHIPPER_ACCOUNT_NUMBER_PROD = os.getenv("FEDEX_ACCOUNT_NUMBER_PRODUCTION") 
    FEDEX_GRANT_TYPE_PROD = os.getenv("FEDEX_GRANT_TYPE_PRODUCTION")
    FEDEX_CHILD_KEY_PROD = os.getenv("FEDEX_CHILD_KEY_PRODUCTION")
    FEDEX_CHILD_SECRET_PROD = os.getenv("FEDEX_CHILD_SECRET_PRODUCTION")

    if FEDEX_API_KEY_PROD: FEDEX_API_KEY = FEDEX_API_KEY_PROD
    if FEDEX_SECRET_KEY_PROD: FEDEX_SECRET_KEY = FEDEX_SECRET_KEY_PROD
    if FEDEX_SHIPPER_ACCOUNT_NUMBER_PROD: FEDEX_SHIPPER_ACCOUNT_NUMBER = FEDEX_SHIPPER_ACCOUNT_NUMBER_PROD
    if FEDEX_GRANT_TYPE_PROD: FEDEX_GRANT_TYPE = FEDEX_GRANT_TYPE_PROD
    if FEDEX_CHILD_KEY_PROD: FEDEX_CHILD_KEY = FEDEX_CHILD_KEY_PROD
    if FEDEX_CHILD_SECRET_PROD: FEDEX_CHILD_SECRET = FEDEX_CHILD_SECRET_PROD
    
    print(f"DEBUG FEDEX_PROD_CONFIG: Using PRODUCTION API Key: {FEDEX_API_KEY[:5] if FEDEX_API_KEY else 'Not Set'}...") 
    print(f"DEBUG FEDEX_PROD_CONFIG: Using PRODUCTION Secret Key: {'*' * (len(FEDEX_SECRET_KEY) - 4) + FEDEX_SECRET_KEY[-4:] if FEDEX_SECRET_KEY else 'Not Set'}")
    print(f"DEBUG FEDEX_PROD_CONFIG: Using PRODUCTION Account Number: {FEDEX_SHIPPER_ACCOUNT_NUMBER}")

    FEDEX_OAUTH_URL = os.getenv("FEDEX_OAUTH_URL_PRODUCTION", "https://apis.fedex.com/oauth/token")
    FEDEX_SHIP_API_URL = os.getenv("FEDEX_SHIP_API_URL_PRODUCTION", "https://apis.fedex.com/ship/v1/shipments")
else: # Sandbox
    FEDEX_OAUTH_URL = os.getenv("FEDEX_OAUTH_URL_SANDBOX", "https://apis-sandbox.fedex.com/oauth/token")
    FEDEX_SHIP_API_URL = os.getenv("FEDEX_SHIP_API_URL_SANDBOX", "https://apis-sandbox.fedex.com/ship/v1/shipments")
    print(f"DEBUG FEDEX_SANDBOX_CONFIG: Using SANDBOX API Key: {FEDEX_API_KEY[:5] if FEDEX_API_KEY else 'Not Set'}...")
    print(f"DEBUG FEDEX_SANDBOX_CONFIG: Using SANDBOX Account Number: {FEDEX_SHIPPER_ACCOUNT_NUMBER}")
    
if not all([FEDEX_API_KEY, FEDEX_SECRET_KEY, FEDEX_SHIPPER_ACCOUNT_NUMBER]):
    print("ERROR SHIPPING_SERVICE (FedEx Setup): FedEx API Key, Secret Key, or Shipper Account Number not found in environment variables.")
else:
    print(f"INFO SHIPPING_SERVICE (FedEx Setup): Configured for {FEDEX_API_ENVIRONMENT}. GrantType: {FEDEX_GRANT_TYPE}. OAuth URL: {FEDEX_OAUTH_URL}, Ship API URL: {FEDEX_SHIP_API_URL}")
    if FEDEX_GRANT_TYPE != "client_credentials" and (not FEDEX_CHILD_KEY or not FEDEX_CHILD_SECRET):
        print(f"WARN SHIPPING_SERVICE (FedEx Setup): Grant type is {FEDEX_GRANT_TYPE}, but Child Key or Child Secret is missing from environment variables.")
# --- End FedEx API Configuration ---

# --- Pillow/ReportLab for Image Conversion ---
try:
    from PIL import Image as PILImage
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch # Ensure inch is imported
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    import io
    PILLOW_AVAILABLE = True
    print("DEBUG SHIPPING_SERVICE (Module Level): Pillow & ReportLab imported successfully for PDF conversion.")
except ImportError:
    PILLOW_AVAILABLE = False
    print("WARN SHIPPING_SERVICE (Module Level): Pillow or ReportLab not found. GIF to PDF conversion will not be available.")
# --- End Image Conversion ---

def get_ups_oauth_token():
    """Obtains an OAuth token from the UPS API."""
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
            print(f"DEBUG UPS_AUTH: Successfully obtained UPS OAuth token. Expires in: {token_data.get('expires_in')} sec.")
            return access_token
        else:
            print(f"ERROR UPS_AUTH: UPS OAuth token response successful but missing 'access_token'. Full Response: {token_data}")
            return None
    except requests.exceptions.HTTPError as http_err:
        status_code = http_err.response.status_code if http_err.response is not None else 'N/A'
        response_text = http_err.response.text if http_err.response is not None else 'N/A'
        print(f"ERROR UPS_AUTH: OAuth HTTP Error. Status: {status_code}, Response: {response_text[:500]}..., Exception: {http_err}")
        return None
    except requests.exceptions.RequestException as req_e:
        print(f"ERROR UPS_AUTH: RequestException during OAuth token request: {req_e}")
        return None
    except Exception as e:
        print(f"ERROR UPS_AUTH: Unexpected exception during OAuth token request: {e}")
        traceback.print_exc()
        return None

def get_fedex_oauth_token():
    """Obtains an OAuth token from the FedEx API."""
    if not all([FEDEX_API_KEY, FEDEX_SECRET_KEY]):
        print("ERROR FEDEX_AUTH: FedEx API Key or Secret Key not configured.")
        return None
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": FEDEX_GRANT_TYPE, "client_id": FEDEX_API_KEY, "client_secret": FEDEX_SECRET_KEY}
    print(f"DEBUG FEDEX_AUTH: Using grant_type '{FEDEX_GRANT_TYPE}'.")
    try:
        print(f"DEBUG FEDEX_AUTH: Requesting OAuth token from {FEDEX_OAUTH_URL} with data: {data}")
        response = requests.post(FEDEX_OAUTH_URL, headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        returned_scope = token_data.get("scope")
        if access_token:
            expires_in = token_data.get("expires_in", "N/A")
            print(f"DEBUG FEDEX_AUTH: Successfully obtained FedEx OAuth token. Expires in: {expires_in} sec. Returned Scope: '{returned_scope}'")
            if returned_scope != "CXS-TP" and "CXS-TP" not in (returned_scope or "").split() and \
               returned_scope != "CXS" and "CXS" not in (returned_scope or "").split() : 
                 print(f"WARN FEDEX_AUTH: Token obtained, but scope is '{returned_scope}'. Expected 'CXS-TP' or 'CXS'. Ship API might still fail.")
            return access_token
        else:
            print(f"ERROR FEDEX_AUTH: FedEx OAuth token response successful but 'access_token' is missing. Full Response: {token_data}")
            return None
    except requests.exceptions.HTTPError as http_err:
        error_message = f"HTTPError during FedEx OAuth token request: {http_err}."
        response_text = http_err.response.text if http_err.response is not None else "No response body."
        print(f"ERROR FEDEX_AUTH: {error_message} Status: {http_err.response.status_code if http_err.response is not None else 'N/A'}, Response: {response_text[:500]}")
        return None
    except requests.exceptions.RequestException as req_e:
        print(f"ERROR FEDEX_AUTH: RequestException during FedEx OAuth token request: {req_e}")
        return None
    except Exception as e:
        print(f"ERROR FEDEX_AUTH: Unexpected exception during FedEx OAuth token request: {e}")
        traceback.print_exc()
        return None

def map_shipping_method_to_ups_code(method_name_from_bc):
    """Maps a BigCommerce shipping method name to a UPS service code."""
    method_name = (method_name_from_bc or "").lower().strip()
    shipping_method_mapping = {
        'ups® ground': '03', 'ups ground': '03', 'ground': '03', 
        'ups® next day air®': '01', 'ups next day air': '01', 'next day air': '01', 
        'ups® 2nd day air®': '02', 'ups 2nd day air': '02', 'second day air': '02', 
        'ups® next day air early a.m.®': '14', 'ups next day air early a.m.': '14', 
        'next day air early am': '14', 'ups next day air early am': '14',
        'ups® worldwide expedited®': '08', 'ups worldwide expedited': '08', 'worldwide expedited': '08', 
        'ups worldwide express': '07', 'worldwide express': '07', 
        'ups worldwide saver': '65', 'worldwide saver': '65', 
        'free shipping': '03', 
    }
    code = shipping_method_mapping.get(method_name)
    if code is None: 
        if 'next day air early' in method_name or 'early a.m.' in method_name or 'early am' in method_name: code = '14'
        elif 'next day air' in method_name or 'nda' in method_name: code = '01'
        elif '2nd day air' in method_name or 'second day' in method_name: code = '02'
        elif 'worldwide expedited' in method_name: code = '08'
        elif 'worldwide express' in method_name: code = '07'
        elif 'worldwide saver' in method_name: code = '65'
        elif 'ground' in method_name: code = '03'
        else:
            print(f"WARN UPS_MAP: Could not map UPS service '{method_name_from_bc}'. Defaulting to '03' (Ground).")
            code = '03' 
    print(f"DEBUG UPS_MAP: Mapped '{method_name_from_bc}' to UPS Service Code '{code}'")
    return code

def map_shipping_method_to_fedex_code(method_name_from_bc):
    """Maps a BigCommerce shipping method name to a FedEx service type ENUM."""
    print(f"DEBUG FEDEX_MAP: Received method name '{method_name_from_bc}' for FedEx mapping.")
    method_name_lower = (method_name_from_bc or "").lower().strip()
    mapping = {
        "fedex first overnight": "FIRST_OVERNIGHT", "first overnight": "FIRST_OVERNIGHT",
        "fedex priority overnight": "FEDEX_PRIORITY_OVERNIGHT", "priority overnight": "FEDEX_PRIORITY_OVERNIGHT",
        "fedex standard overnight": "STANDARD_OVERNIGHT", "standard overnight": "STANDARD_OVERNIGHT",
        "fedex 2day am": "FEDEX_2_DAY_AM", "fedex 2 day am": "FEDEX_2_DAY_AM", "2day am": "FEDEX_2_DAY_AM", "2 day am": "FEDEX_2_DAY_AM",
        "fedex 2day": "FEDEX_2_DAY", "fedex 2 day": "FEDEX_2_DAY", "2-day": "FEDEX_2_DAY", "2 day": "FEDEX_2_DAY",
        "fedex express saver": "FEDEX_EXPRESS_SAVER", "express saver": "FEDEX_EXPRESS_SAVER",
        "fedex ground": "FEDEX_GROUND", "ground": "FEDEX_GROUND",
        "fedex international priority": "INTERNATIONAL_PRIORITY", "international priority": "INTERNATIONAL_PRIORITY",
        "fedex international economy": "INTERNATIONAL_ECONOMY", "international economy": "INTERNATIONAL_ECONOMY",
        "fedex home delivery": "GROUND_HOME_DELIVERY", "home delivery": "GROUND_HOME_DELIVERY",
        "free shipping": "FEDEX_GROUND" 
    }
    api_code = mapping.get(method_name_lower)
    if api_code:
        print(f"DEBUG FEDEX_MAP: Mapped (direct) '{method_name_from_bc}' to FedEx Service Code '{api_code}'")
        return api_code
    if "first overnight" in method_name_lower: api_code = "FIRST_OVERNIGHT"
    elif "priority overnight" in method_name_lower: api_code = "FEDEX_PRIORITY_OVERNIGHT"
    elif "standard overnight" in method_name_lower: api_code = "STANDARD_OVERNIGHT"
    elif "2 day am" in method_name_lower or "2day am" in method_name_lower: api_code = "FEDEX_2_DAY_AM"
    elif "2-day" in method_name_lower or "2 day" in method_name_lower or "2day" in method_name_lower : api_code = "FEDEX_2_DAY"
    elif "express saver" in method_name_lower: api_code = "FEDEX_EXPRESS_SAVER"
    elif "home delivery" in method_name_lower: api_code = "GROUND_HOME_DELIVERY"
    elif "ground" in method_name_lower: api_code = "FEDEX_GROUND" 
    elif "international priority" in method_name_lower: api_code = "INTERNATIONAL_PRIORITY"
    elif "international economy" in method_name_lower: api_code = "INTERNATIONAL_ECONOMY"
    else:
        print(f"WARN FEDEX_MAP: Could not map FedEx service '{method_name_from_bc}'. Defaulting to 'FEDEX_GROUND'. This might be incorrect.")
        api_code = "FEDEX_GROUND" 
    print(f"DEBUG FEDEX_MAP: Mapped (fallback/default) '{method_name_from_bc}' to FedEx Service Code '{api_code}'")
    return api_code

def generate_ups_label_raw(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token):
    if not access_token: print("ERROR UPS_LABEL_RAW: Access token not provided."); return None, None
    bc_order_id_str = str(order_data.get('bigcommerce_order_id', 'N/A_UnknownOrder'))
    unique_ts = int(datetime.now(timezone.utc).timestamp()*1000) 
    headers = {
        "Authorization": f"Bearer {access_token}", "Content-Type": "application/json",
        "Accept": "application/json", "transId": f"Order_{bc_order_id_str}_{unique_ts}",
        "transactionSrc": "G1POApp_v13_ConditionalPayment" 
    }
    ups_service_code = map_shipping_method_to_ups_code(customer_shipping_method_name)
    ship_to_state_input = order_data.get('customer_shipping_state', '')
    ship_to_country_code_from_data = order_data.get('customer_shipping_country', 'US')
    ship_to_country_code_upper = ship_to_country_code_from_data.upper() if ship_to_country_code_from_data else 'US'
    ship_to_state_processed = ''
    state_mapping_us_ca = {
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
        "alberta": "AB", "british columbia": "BC", "manitoba": "MB", "new brunswick": "NB",
        "newfoundland and labrador": "NL", "nova scotia": "NS", "ontario": "ON",
        "prince edward island": "PE", "quebec": "QC", "saskatchewan": "SK",
        "northwest territories": "NT", "nunavut": "NU", "yukon": "YT"
    }
    valid_us_ca_state_codes = {v: k for k, v in state_mapping_us_ca.items()}
    if ship_to_country_code_upper in ['US', 'CA']:
        input_state_upper_stripped = ship_to_state_input.upper().strip()
        if len(input_state_upper_stripped) == 2 and input_state_upper_stripped in valid_us_ca_state_codes:
            ship_to_state_processed = input_state_upper_stripped 
        else: 
            ship_to_state_processed = state_mapping_us_ca.get(ship_to_state_input.lower().strip(), "")
            if not ship_to_state_processed:
                print(f"ERROR UPS Payload: {ship_to_country_code_upper} State/Province '{ship_to_state_input}' could not be mapped.")
                return None, None
    else: 
        ship_to_state_processed = ship_to_state_input.strip()
        if not ship_to_state_processed: 
             print(f"WARN UPS Payload: ShipTo State/Province is empty for country {ship_to_country_code_upper}.")
    ship_to_company_name = order_data.get('customer_company', '').strip()
    ship_to_contact_person_name = order_data.get('customer_name', '').strip()
    ups_ship_to_name = ship_to_company_name if ship_to_company_name else ship_to_contact_person_name
    if not ups_ship_to_name: 
        print("ERROR UPS Payload: ShipTo Name missing.")
        return None, None
    ups_attention_name = ship_to_contact_person_name if ship_to_company_name and ship_to_contact_person_name else ship_to_contact_person_name
    is_bill_recipient_flag = order_data.get('is_bill_to_customer_account', False)
    customer_ups_acct_num = order_data.get('customer_ups_account_number')
    shipper_payload_block = {
        "Name": ship_from_address.get('name'), "AttentionName": ship_from_address.get('contact_person'),
        "Phone": {"Number": (ship_from_address.get('phone') or "").replace('-', '').replace('(', '').replace(')', '').replace(' ', '')},
        "ShipperNumber": UPS_ACCOUNT_NUMBER, 
        "Address": {
            "AddressLine": [addr for addr in [ship_from_address.get('street_1'), ship_from_address.get('street_2')] if addr and addr.strip()],
            "City": ship_from_address.get('city'), "StateProvinceCode": ship_from_address.get('state'),
            "PostalCode": ship_from_address.get('zip'), "CountryCode": ship_from_address.get('country', 'US').upper()
        }}
    payload_shipment_part = {
        "Description": order_data.get('customer_company', "Order") + " Shipment", "Shipper": shipper_payload_block,
        "ShipTo": {"Name": ups_ship_to_name, "AttentionName": ups_attention_name,
            "Phone": {"Number": (order_data.get('customer_phone') or "").replace('-', '').replace('(', '').replace(')', '').replace(' ', '')},
            "Address": {"AddressLine": [addr for addr in [order_data.get('customer_shipping_address_line1'), order_data.get('customer_shipping_address_line2')] if addr and addr.strip()],
                "City": order_data.get('customer_shipping_city'), "StateProvinceCode": ship_to_state_processed,
                "PostalCode": str(order_data.get('customer_shipping_zip', '')), "CountryCode": ship_to_country_code_upper}},
        "Service": {"Code": ups_service_code}, 
        "Package": [{"Description": "Box of Parts", "Packaging": {"Code": "02"}, 
            "PackageWeight": {"UnitOfMeasurement": {"Code": "LBS"}, "Weight": str(round(float(max(0.1, total_weight_lbs)), 1))},
            "ReferenceNumber": [{"Code": "02", "Value": str(bc_order_id_str)}]}]}
    if is_bill_recipient_flag and customer_ups_acct_num:
        print(f"DEBUG UPS_LABEL_RAW: Using 'PaymentDetails' (current spec) for BillThirdParty. Account: {customer_ups_acct_num}")
        third_party_postal_code = str(order_data.get('customer_shipping_zip', '')) 
        third_party_country_code = str(ship_to_country_code_upper) 
        if not third_party_postal_code: print(f"ERROR UPS Payload (Payment): Postal code missing for 3rd party bill."); return None, None
        payment_details_payload = { "ShipmentCharge": [{"Type": "01", "BillThirdParty": {"AccountNumber": str(customer_ups_acct_num), "Address": {"PostalCode": third_party_postal_code, "CountryCode": third_party_country_code}}}]}
        payload_shipment_part["PaymentDetails"] = payment_details_payload
        # print(f"DEBUG UPS_LABEL_RAW (PRE-CALL): PaymentDetails (BillThirdParty): {json.dumps(payment_details_payload, indent=2)}")
    else: 
        print(f"DEBUG UPS_LABEL_RAW: Using 'PaymentInformation' (OLD spec) for BillShipper. Account: {UPS_ACCOUNT_NUMBER}")
        if not UPS_ACCOUNT_NUMBER or not UPS_ACCOUNT_NUMBER.strip(): print(f"CRITICAL ERROR UPS_LABEL_RAW: UPS_BILLING_ACCOUNT_NUMBER missing."); return None, None 
        payment_information_payload_old_spec = { "ShipmentCharge": { "Type": "01", "BillShipper": {"AccountNumber": UPS_ACCOUNT_NUMBER}}}
        payload_shipment_part["PaymentInformation"] = payment_information_payload_old_spec 
        # print(f"DEBUG UPS_LABEL_RAW (PRE-CALL): PaymentInformation (BillShipper - OLD STRUCT): {json.dumps(payment_information_payload_old_spec, indent=2)}")
    payload = { "ShipmentRequest": { "Request": {"RequestOption": "nonvalidate", "TransactionReference": {"CustomerContext": f"Order_{bc_order_id_str}"}}, "Shipment": payload_shipment_part, "LabelSpecification": {"LabelImageFormat": {"Code": "GIF"}, "HTTPUserAgent": "Mozilla/5.0"}}}
    # print(f"DEBUG UPS_LABEL_RAW (PRE-CALL): Shipper Block: {json.dumps(shipper_payload_block, indent=2)}")
    # print(f"DEBUG UPS_LABEL_RAW (PRE-CALL): Full Payload: {json.dumps(payload, indent=2)}", flush=True)
    try:
        response = requests.post(UPS_SHIPPING_API_ENDPOINT, headers=headers, json=payload)
        response_data = response.json() 
        # *** ADDED LOGGING FOR FULL SUCCESS RESPONSE ***
        if response.status_code == 200 and response_data.get("ShipmentResponse", {}).get("Response", {}).get("ResponseStatus", {}).get("Code") == "1":
            print(f"DEBUG UPS_LABEL_RAW (Full Response for Success Code 1): {json.dumps(response_data, indent=2, ensure_ascii=False)}", flush=True)
        # *** END ADDED LOGGING ***
        response.raise_for_status() 
        shipment_response = response_data.get("ShipmentResponse", {})
        response_status_obj = shipment_response.get("Response", {}).get("ResponseStatus", {})
        if response_status_obj.get("Code") == "1": 
            shipment_results = shipment_response.get("ShipmentResults", {})
            tracking_number = shipment_results.get("ShipmentIdentificationNumber")
            package_results_list = shipment_results.get("PackageResults", [])
            label_image_base64 = None
            if package_results_list and isinstance(package_results_list, list) and len(package_results_list) > 0 and package_results_list[0]: # Added len check
                label_image_base64 = package_results_list[0].get("ShippingLabel", {}).get("GraphicImage")
            if tracking_number and label_image_base64: return base64.b64decode(label_image_base64), tracking_number
            elif tracking_number: print(f"WARN UPS_LABEL_RAW: Tracking {tracking_number} obtained, but no label image."); return None, tracking_number
            else: print(f"ERROR UPS_LABEL_RAW: Success code '1' but no tracking. Results: {shipment_results}"); return None, None
        else: 
            error_description = response_status_obj.get("Description", "Unknown UPS Error"); alerts = shipment_response.get("Response", {}).get("Alert", []) 
            if not isinstance(alerts, list): alerts = [alerts] 
            error_details_str = "; ".join([f"Code {alert.get('Code')}: {alert.get('Description')}" for alert in alerts if alert]) if alerts else "No details."
            print(f"ERROR UPS_LABEL_RAW: UPS API Error. Desc: '{error_description}'. Alerts: '{error_details_str}'. Resp: {json.dumps(response_data, indent=2)}")
            return None, None
    except requests.exceptions.HTTPError as http_err:
        response_content = "Could not decode JSON or no response."
        try: response_content = http_err.response.json() if http_err.response is not None else "No response."
        except json.JSONDecodeError: response_content = http_err.response.text if http_err.response is not None else "No text."
        print(f"ERROR UPS_LABEL_RAW: HTTPError: {http_err}. Response: {str(response_content)[:1000]}"); return None, None
    except requests.exceptions.RequestException as req_err: print(f"ERROR UPS_LABEL_RAW: ReqException: {req_err}"); traceback.print_exc(); return None, None
    except json.JSONDecodeError as json_err:
        response_text_snippet = response.text[:500] if hasattr(response, 'text') and response.text else "N/A"
        print(f"ERROR UPS_LABEL_RAW: JSONDecodeError: {json_err}. Resp text snippet: {response_text_snippet}"); return None, None
    except Exception as e: print(f"ERROR UPS_LABEL_RAW: Unexpected Exception: {e}"); traceback.print_exc(); return None, None


def generate_fedex_label_raw(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token):
    """Generates raw FedEx label data (PDF) and tracking number."""
    if not access_token:
        print("ERROR FEDEX_LABEL_RAW: FedEx Access token not provided.")
        return None, None
    if not FEDEX_SHIPPER_ACCOUNT_NUMBER: 
        print("ERROR FEDEX_LABEL_RAW: FEDEX_SHIPPER_ACCOUNT_NUMBER not configured.")
        return None, None
    fedex_service_type_enum = map_shipping_method_to_fedex_code(customer_shipping_method_name)
    if not fedex_service_type_enum: 
        print(f"ERROR FEDEX_LABEL_RAW: Could not map shipping method '{customer_shipping_method_name}'.")
        return None, None
    ship_to_street_lines = [s for s in [order_data.get('customer_shipping_address_line1'), order_data.get('customer_shipping_address_line2')] if s and s.strip()]
    if not ship_to_street_lines:
        print("ERROR FEDEX_LABEL_RAW: Ship To address line 1 is missing.")
        return None, None
    ship_to_state_input = order_data.get('customer_shipping_state', '')
    ship_to_country_code_from_data = order_data.get('customer_shipping_country', 'US')
    ship_to_country_code_upper = ship_to_country_code_from_data.upper() if ship_to_country_code_from_data else 'US'
    ship_to_state_processed = ''
    state_mapping_us_ca = {"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "puerto rico": "PR", "alberta": "AB", "british columbia": "BC", "manitoba": "MB", "new brunswick": "NB", "newfoundland and labrador": "NL", "nova scotia": "NS", "ontario": "ON", "prince edward island": "PE", "quebec": "QC", "saskatchewan": "SK", "northwest territories": "NT", "nunavut": "NU", "yukon": "YT"}
    valid_us_ca_state_codes = {v: k for k, v in state_mapping_us_ca.items()}
    if ship_to_country_code_upper in ['US', 'CA']:
        input_state_upper_stripped = ship_to_state_input.upper().strip()
        if len(input_state_upper_stripped) == 2 and input_state_upper_stripped in valid_us_ca_state_codes: ship_to_state_processed = input_state_upper_stripped
        else:
            ship_to_state_processed = state_mapping_us_ca.get(ship_to_state_input.lower().strip(), "")
            if not ship_to_state_processed: 
                print(f"ERROR FEDEX_LABEL_RAW: {ship_to_country_code_upper} State/Province '{ship_to_state_input}' unmappable.")
                return None, None
    else: ship_to_state_processed = ship_to_state_input.strip()
    payment_info = {}
    is_bill_recipient_fedex = order_data.get('is_bill_to_customer_fedex_account', False)
    customer_fedex_acct_num_from_order = order_data.get('customer_fedex_account_number')
    if is_bill_recipient_fedex and customer_fedex_acct_num_from_order:
        print(f"DEBUG FEDEX_LABEL_RAW: Attempting Bill Recipient FedEx Account: {customer_fedex_acct_num_from_order}")
        payment_info = {"paymentType": "RECIPIENT", "payor": {"responsibleParty": {"accountNumber": {"value": str(customer_fedex_acct_num_from_order)}}}}
    else: 
        print(f"DEBUG FEDEX_LABEL_RAW: Defaulting to Bill SENDER. Account: {FEDEX_SHIPPER_ACCOUNT_NUMBER}")
        payment_info = {"paymentType": "SENDER", "payor": {"responsibleParty": {"accountNumber": {"value": str(FEDEX_SHIPPER_ACCOUNT_NUMBER)}}}}
    shipper_contact_name = ship_from_address.get('contact_person', ship_from_address.get('name', 'Shipping Dept'))
    shipper_company_name = ship_from_address.get('name', 'Your Company LLC')
    if not all([ship_from_address.get('street_1'), ship_from_address.get('city'), ship_from_address.get('state'), ship_from_address.get('zip'), ship_from_address.get('country'), ship_from_address.get('phone')]):
        print("ERROR FEDEX_LABEL_RAW: Shipper (Ship From) address not fully configured."); return None, None
    requested_shipment_payload = {
        "shipper": {"contact": {"personName": shipper_contact_name, "companyName": shipper_company_name, "phoneNumber": (ship_from_address.get('phone') or "").replace('-', '').replace('(', '').replace(')', '').replace(' ', '')}, 
                    "address": {"streetLines": [s for s in [ship_from_address.get('street_1'), ship_from_address.get('street_2')] if s and s.strip()], "city": ship_from_address.get('city'), "stateOrProvinceCode": ship_from_address.get('state').upper(), "postalCode": str(ship_from_address.get('zip')), "countryCode": ship_from_address.get('country', 'US').upper()}},
        "recipients": [{"contact": {"personName": order_data.get('customer_name', 'N/A'), "companyName": order_data.get('customer_company', ''), "phoneNumber": (order_data.get('customer_phone') or "").replace('-', '').replace('(', '').replace(')', '').replace(' ', '')}, 
                       "address": {"streetLines": ship_to_street_lines, "city": order_data.get('customer_shipping_city'), "stateOrProvinceCode": ship_to_state_processed, "postalCode": str(order_data.get('customer_shipping_zip', '')), "countryCode": ship_to_country_code_upper, "residential": False }}],
        "shipDatestamp": datetime.now(timezone.utc).strftime('%Y-%m-%d'), "serviceType": fedex_service_type_enum, "packagingType": "YOUR_PACKAGING", "pickupType": "DROPOFF_AT_FEDEX_LOCATION",
        "shippingChargesPayment": payment_info, "labelSpecification": {"imageType": "PDF", "labelStockType": "PAPER_85X11_TOP_HALF_LABEL"},
        "requestedPackageLineItems": [{"weight": {"units": "LB", "value": round(float(max(0.1, total_weight_lbs)), 1)}, "customerReferences": [{"customerReferenceType": "CUSTOMER_REFERENCE", "value": str(order_data.get('bigcommerce_order_id', 'N/A'))}]}]}
    final_api_payload = {"labelResponseOptions": "LABEL", "requestedShipment": requested_shipment_payload, "accountNumber": {"value": str(FEDEX_SHIPPER_ACCOUNT_NUMBER)}}
    headers = {"Authorization": f"Bearer {access_token}", "X-locale": "en_US", "Content-Type": "application/json"}
    try:
        # print(f"DEBUG FEDEX_LABEL_RAW: Full Payload to FedEx API: {json.dumps(final_api_payload, indent=2)}", flush=True) 
        response = requests.post(FEDEX_SHIP_API_URL, headers=headers, json=final_api_payload)
        print(f"DEBUG FEDEX_LABEL_RAW: FedEx API Response Status: {response.status_code}", flush=True)
        response_data = response.json()
        # print(f"DEBUG FEDEX_LABEL_RAW: FedEx API Response Body: {json.dumps(response_data, indent=2)}", flush=True) 
        response.raise_for_status() 
        if response_data.get("errors"): 
            errors = response_data.get("errors", []); error_messages = "; ".join([f"Code {err.get('code')}: {err.get('message')}" for err in errors])
            print(f"ERROR FEDEX_LABEL_RAW: FedEx API returned errors: {error_messages}. Full: {errors}"); return None, None
        output = response_data.get("output", {}); transaction_shipments = output.get("transactionShipments", [])
        if not transaction_shipments: print(f"ERROR FEDEX_LABEL_RAW: 'transactionShipments' missing. Output: {output}"); return None, None
        first_shipment = transaction_shipments[0]; tracking_number = first_shipment.get("masterTrackingNumber"); encoded_label_data = None
        piece_responses = first_shipment.get("pieceResponses", [])
        if piece_responses and piece_responses[0].get("packageDocuments"):
            for doc in piece_responses[0].get("packageDocuments", []):
                if doc.get("encodedLabel") or doc.get("content"): encoded_label_data = doc.get("encodedLabel") or doc.get("content"); break
        elif first_shipment.get("packageDocuments"):
             for doc in first_shipment.get("packageDocuments", []):
                if doc.get("encodedLabel") or doc.get("content"): encoded_label_data = doc.get("encodedLabel") or doc.get("content"); break
        if tracking_number and encoded_label_data:
            print(f"INFO FEDEX_LABEL_RAW: FedEx Label generated. Tracking: {tracking_number}")
            try: return base64.b64decode(encoded_label_data), tracking_number
            except Exception as b64_e: print(f"ERROR FEDEX_LABEL_RAW: Failed to decode base64 label: {b64_e}"); return None, tracking_number
        elif tracking_number: print(f"WARN FEDEX_LABEL_RAW: Tracking {tracking_number} obtained, but no label data. Details: {first_shipment}"); return None, tracking_number
        else: print(f"ERROR FEDEX_LABEL_RAW: No tracking or label. Details: {first_shipment}"); return None, None
    except requests.exceptions.HTTPError as http_err:
        response_content = "Could not decode JSON or no response."
        try: response_content = http_err.response.json() if http_err.response is not None else "No response."
        except json.JSONDecodeError: response_content = http_err.response.text if http_err.response is not None else "No text."
        print(f"ERROR FEDEX_LABEL_RAW: HTTPError: {http_err}. Response: {str(response_content)[:1000]}"); return None, None
    except requests.exceptions.RequestException as req_err: print(f"ERROR FEDEX_LABEL_RAW: ReqException: {req_err}"); traceback.print_exc(); return None, None
    except json.JSONDecodeError as json_err:
        response_text_snippet = response.text[:500] if hasattr(response, 'text') and response.text else "N/A"
        print(f"ERROR FEDEX_LABEL_RAW: JSONDecodeError: {json_err}. Resp text snippet: {response_text_snippet}"); return None, None
    except Exception as e: print(f"ERROR FEDEX_LABEL_RAW: Unexpected Exception: {e}"); traceback.print_exc(); return None, None

def generate_fedex_label(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name):
    """High-level function to get FedEx OAuth token and then generate label."""
    print(f"DEBUG FEDEX_GEN_LABEL: Initiating FedEx label for order {order_data.get('bigcommerce_order_id', 'N/A')}, Wt {total_weight_lbs}, Method '{customer_shipping_method_name}'")
    access_token = get_fedex_oauth_token()
    if not access_token:
        print("ERROR FEDEX_GEN_LABEL: Failed to get FedEx OAuth token."); return None, None
    label_pdf_bytes, tracking_number = generate_fedex_label_raw(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token)
    if label_pdf_bytes and tracking_number: print(f"INFO FEDEX_GEN_LABEL: FedEx PDF label generated. Tracking: {tracking_number}."); return label_pdf_bytes, tracking_number
    elif tracking_number: print(f"WARN FEDEX_GEN_LABEL: Got FedEx tracking {tracking_number}, but no label PDF."); return None, tracking_number
    else: print(f"ERROR FEDEX_GEN_LABEL: Failed to generate FedEx label/tracking."); return None, None

def convert_image_bytes_to_pdf_bytes(image_bytes, image_format="GIF"):
    """Converts image bytes (e.g., GIF from UPS) to PDF bytes, aligning image to top."""
    if not PILLOW_AVAILABLE:
        print("ERROR IMG_TO_PDF: Pillow/ReportLab not available."); return None
    if not image_bytes:
        print("ERROR IMG_TO_PDF: No image bytes provided."); return None
    
    try:
        img_stream = io.BytesIO(image_bytes)
        img = PILImage.open(img_stream)
        
        if hasattr(img, 'seek'): 
            img.seek(0) 
        
        img = img.convert("RGBA") 
        img_width_px, img_height_px = img.size

        if img_width_px == 0 or img_height_px == 0:
            print("ERROR IMG_TO_PDF: Image dimensions are zero. Cannot process.")
            return None

        page_width_pt, page_height_pt = letter 
        margin_pt = 1 * inch # Use inch from reportlab.lib.units

        drawable_area_width_pt = page_width_pt - (2 * margin_pt)
        # drawable_area_height_pt = page_height_pt - (2 * margin_pt) # Not strictly needed for top-align y_offset

        img_aspect_ratio = img_width_px / img_height_px
        
        draw_width_pt = drawable_area_width_pt # Maximize width within margins
        draw_height_pt = draw_width_pt / img_aspect_ratio

        # If calculated height exceeds page height (minus margins), scale by height instead
        if draw_height_pt > (page_height_pt - 2 * margin_pt):
            draw_height_pt = page_height_pt - (2 * margin_pt)
            draw_width_pt = draw_height_pt * img_aspect_ratio
        
        # X offset for horizontal centering
        x_offset_pt = margin_pt + (drawable_area_width_pt - draw_width_pt) / 2
        
        # *** MODIFICATION FOR TOP ALIGNMENT ***
        # Y offset for top alignment (ReportLab y-coordinates are from bottom of page)
        # Position the bottom of the image so its top aligns with the top margin boundary.
        y_offset_pt = page_height_pt - margin_pt - draw_height_pt
        # Ensure y_offset is not below the bottom margin (e.g. if image is very tall)
        y_offset_pt = max(y_offset_pt, margin_pt)


        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        
        png_stream = io.BytesIO()
        img.save(png_stream, format="PNG")
        png_stream.seek(0) 

        reportlab_image = ImageReader(png_stream) 
        
        c.drawImage(reportlab_image, x_offset_pt, y_offset_pt, 
                    width=draw_width_pt, height=draw_height_pt, 
                    mask='auto', preserveAspectRatio=True)
        
        c.showPage()
        c.save()
        
        pdf_bytes_out = pdf_buffer.getvalue()
        pdf_buffer.close()
        png_stream.close()
        img_stream.close()
        
        print("DEBUG IMG_TO_PDF: Image converted to PDF bytes (top-aligned)."); return pdf_bytes_out
        
    except Exception as e: print(f"ERROR IMG_TO_PDF: Conversion failed: {e}"); traceback.print_exc(); return None

def generate_ups_label(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name):
    # print(f"DEBUG UPS_GEN_LABEL: Order {order_data.get('bigcommerce_order_id', 'N/A')}, Wt {total_weight_lbs}, Method '{customer_shipping_method_name}'") # Less verbose
    access_token = get_ups_oauth_token()
    if not access_token: print("ERROR UPS_GEN_LABEL: Failed to get UPS OAuth token."); return None, None 
    raw_label_image_bytes, tracking_number = generate_ups_label_raw(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token)
    if not tracking_number and not raw_label_image_bytes: print("ERROR UPS_GEN_LABEL: Raw gen failed."); return None, None
    if not raw_label_image_bytes and tracking_number: print(f"WARN UPS_GEN_LABEL: Tracking {tracking_number}, but no raw label image."); return None, tracking_number 
    final_label_pdf_bytes = convert_image_bytes_to_pdf_bytes(raw_label_image_bytes, image_format="GIF")
    if not final_label_pdf_bytes: print(f"ERROR UPS_GEN_LABEL: PDF conversion failed for track {tracking_number}."); return None, tracking_number 
    # print(f"INFO UPS_GEN_LABEL: PDF label generated for track {tracking_number}.") # Less verbose
    return final_label_pdf_bytes, tracking_number

def create_bigcommerce_shipment(bigcommerce_order_id, tracking_number, shipping_method_name, line_items_in_shipment, order_address_id, comments=None, shipping_provider=None):
    """Creates a shipment record in BigCommerce."""
    print(f"DEBUG BC_CREATE_SHIPMENT: Order {bigcommerce_order_id}, Track {tracking_number}")
    if not CURRENT_BC_API_BASE_URL_V2 or not CURRENT_BC_HEADERS or not CURRENT_BC_HEADERS.get("X-Auth-Token"): print("ERROR BC_CREATE_SHIPMENT: BC API not configured."); return False
    if not all([bigcommerce_order_id, tracking_number, line_items_in_shipment]) or order_address_id is None: print(f"ERROR BC_CREATE_SHIPMENT: Missing args."); return False
    shipments_url = f"{CURRENT_BC_API_BASE_URL_V2}orders/{bigcommerce_order_id}/shipments"; tracking_carrier = ""
    sm_lower = (shipping_method_name or "").lower()
    if "ups" in sm_lower: tracking_carrier = "ups"
    elif "fedex" in sm_lower: tracking_carrier = "fedex"
    elif "usps" in sm_lower: tracking_carrier = "usps"
    shipment_payload = {"order_address_id": int(order_address_id), "tracking_number": str(tracking_number), "items": line_items_in_shipment}
    if shipping_method_name: shipment_payload["shipping_method"] = str(shipping_method_name)
    if tracking_carrier: shipment_payload["tracking_carrier"] = tracking_carrier
    if comments: shipment_payload["comments"] = str(comments)
    if shipping_provider: shipment_payload["shipping_provider"] = str(shipping_provider)
    print(f"DEBUG BC_CREATE_SHIPMENT: Payload: {json.dumps(shipment_payload)}")
    try:
        response = requests.post(shipments_url, headers=CURRENT_BC_HEADERS, json=shipment_payload)
        response.raise_for_status(); shipment_creation_data = response.json()
        print(f"INFO BC_CREATE_SHIPMENT: Success for BC Order {bigcommerce_order_id}. BC Ship ID: {shipment_creation_data.get('id')}"); return True
    except requests.exceptions.HTTPError as http_err: print(f"ERROR BC_CREATE_SHIPMENT: HTTPError for {bigcommerce_order_id}: {http_err}. Resp: {http_err.response.text if http_err.response else 'N/A'}"); return False
    except Exception as e: print(f"ERROR BC_CREATE_SHIPMENT: Unexpected error for {bigcommerce_order_id}: {e}"); traceback.print_exc(); return False

def set_bigcommerce_order_status(bigcommerce_order_id, status_id):
    """Updates the status of an order in BigCommerce."""
    print(f"DEBUG BC_SET_STATUS: Order {bigcommerce_order_id}, Status ID {status_id}")
    if not CURRENT_BC_API_BASE_URL_V2 or not CURRENT_BC_HEADERS or not CURRENT_BC_HEADERS.get("X-Auth-Token"): print("ERROR BC_SET_STATUS: BC API not configured."); return False
    if not bigcommerce_order_id or status_id is None: print(f"ERROR BC_SET_STATUS: Missing args."); return False
    order_update_url = f"{CURRENT_BC_API_BASE_URL_V2}orders/{bigcommerce_order_id}"; status_update_payload = {"status_id": int(status_id)}
    print(f"DEBUG BC_SET_STATUS: Payload: {json.dumps(status_update_payload)}")
    try:
        response = requests.put(order_update_url, headers=CURRENT_BC_HEADERS, json=status_update_payload)
        response.raise_for_status()
        print(f"INFO BC_SET_STATUS: Success for BC Order {bigcommerce_order_id} to Status ID {status_id}."); return True
    except requests.exceptions.HTTPError as http_err: print(f"ERROR BC_SET_STATUS: HTTPError for {bigcommerce_order_id}: {http_err}. Resp: {http_err.response.text if http_err.response else 'N/A'}"); return False
    except Exception as e: print(f"ERROR BC_SET_STATUS: Unexpected error for {bigcommerce_order_id}: {e}"); traceback.print_exc(); return False

if __name__ == '__main__':
    print("\n--- Running shipping_service.py in standalone test mode ---")
    print("\n--- Testing UPS OAuth Token ---")
    ups_token = get_ups_oauth_token()
    if ups_token: print("UPS OAuth Token (first 30):", ups_token[:30] + "...")
    else: print("Failed to get UPS OAuth Token.")
    print(f"\n--- Testing FedEx OAuth Token (Env: {FEDEX_API_ENVIRONMENT}) ---")
    fedex_token = get_fedex_oauth_token() # Ensure you get a fresh token

    if fedex_token:
        print(f"\n--- FedEx Priority Overnight Test ({FEDEX_API_ENVIRONMENT.upper()} Environment) ---")
        
        # --- CUSTOMIZE YOUR TEST ORDER DATA HERE ---
        mock_order_data_priority_overnight = {
            'bigcommerce_order_id': f'TEST_FX_PO_{int(datetime.now(timezone.utc).timestamp())}',
            'customer_company': 'Test  Recipient Inc.', 
            'customer_name': 'Pat Smith',
            'customer_phone': '8001234567', # Use a valid format
            'customer_shipping_address_line1': '4916 S 184th Plaza', # Recipient address
            'customer_shipping_address_line2': '',       # Recipient address line 2 (optional)
            'customer_shipping_city': 'Omaha',                 # Recipient city
            'customer_shipping_state': 'NE',                      # Recipient state (e.g., 'CA' for California)
            'customer_shipping_zip': '68135',                     # Recipient ZIP
            'customer_shipping_country': 'US',                    # Recipient country (e.g., 'US')
            'customer_email': 'pat.priority@example.com',
            'is_bill_to_customer_fedex_account': False, # IMPORTANT: Set to False for Bill SENDER
            'customer_fedex_account_number': None       # Not needed for Bill SENDER
        }

        # Ship From address is loaded from .env variables within the script
        mock_ship_from_details = {
            'name': os.getenv("SHIP_FROM_NAME"), 
            'contact_person': os.getenv("SHIP_FROM_CONTACT"),
            'street_1': os.getenv("SHIP_FROM_STREET1"), 
            'street_2': os.getenv("SHIP_FROM_STREET2", ""),
            'city': os.getenv("SHIP_FROM_CITY"), 
            'state': os.getenv("SHIP_FROM_STATE"),
            'zip': os.getenv("SHIP_FROM_ZIP"), 
            'country': os.getenv("SHIP_FROM_COUNTRY", "US"),
            'phone': os.getenv("SHIP_FROM_PHONE")
        }

        # Check if essential SHIP_FROM details are present
        if any(not mock_ship_from_details.get(key) for key in ['name', 'street_1', 'city', 'state', 'zip', 'country', 'phone']):
            print("ERROR: FedEx Priority Overnight Test ABORTED. Essential SHIP_FROM details missing in .env.")
        else:
            service_to_test = "2 Day" # Your desired service
            weight_to_test = 2  # Example weight in lbs

            print(f"\nAttempting FedEx Label (Bill SENDER - {service_to_test}) in {FEDEX_API_ENVIRONMENT.upper()}")
            
            # Using generate_fedex_label which calls get_fedex_oauth_token and then generate_fedex_label_raw
            # OR, if you already have a token and want to use the _raw function directly:
            # pdf_bytes_fx, tracking_fx = generate_fedex_label_raw(
            #                                 mock_order_data_priority_overnight, 
            #                                 mock_ship_from_details, 
            #                                 weight_to_test, 
            #                                 service_to_test,
            #                                 fedex_token # Pass the token here
            #                             )

            # Using the higher-level function that gets its own token:
            pdf_bytes_fx, tracking_fx = generate_fedex_label(
                                            mock_order_data_priority_overnight,
                                            mock_ship_from_details,
                                            weight_to_test,
                                            service_to_test
                                        )

            if pdf_bytes_fx and tracking_fx:
                print(f"FedEx Priority Overnight Test: SUCCESS! Tracking: {tracking_fx}")
                filename = f"{FEDEX_API_ENVIRONMENT}_fx_priority_label_{tracking_fx}.pdf"
                try:
                    with open(filename, "wb") as f:
                        f.write(pdf_bytes_fx)
                    print(f"  Label saved as {filename}")
                except Exception as e:
                    print(f"  Error writing label file: {e}")
            elif tracking_fx:
                print(f"FedEx Priority Overnight Test: PARTIAL SUCCESS. Tracking: {tracking_fx}, but no PDF label data.")
            else:
                print(f"FedEx Priority Overnight Test: FAILED.")
    else:
        print("Failed to get FedEx OAuth Token, cannot proceed with Priority Overnight test.")

    print("\n--- shipping_service.py standalone test finished ---")