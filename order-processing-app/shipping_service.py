# shipping_service.py
# PRINT DIAGNOSTIC VERSION MARKER
print("DEBUG SHIPPING_SERVICE: TOP OF FILE shipping_service.py REACHED")
print("DEBUG SHIPPING_SERVICE: --- VERSION WITH INTERNATIONAL SHIPMENT FUNCTION ---")

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
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    import io
    PILLOW_AVAILABLE = True
    print("DEBUG SHIPPING_SERVICE (Module Level): Pillow & ReportLab imported successfully for PDF conversion.")
except ImportError:
    PILLOW_AVAILABLE = False
    print("WARN SHIPPING_SERVICE (Module Level): Pillow or ReportLab not found. GIF to PDF conversion will not be available.")
# --- End Image Conversion ---

STATE_MAPPING_US_CA = {
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
    "alberta": "AB", "british columbia": "BC", "manitota": "MB", "new brunswick": "NB",
    "newfoundland and labrador": "NL", "nova scotia": "NS", "ontario": "ON",
    "prince edward island": "PE", "quebec": "QC", "saskatchewan": "SK",
    "northwest territories": "NT", "nunavut": "NU", "yukon": "YT"
}
VALID_US_CA_STATE_CODES = {v: k for k, v in STATE_MAPPING_US_CA.items()}

def _get_processed_state_code(state_input, country_code_upper, party_type="ShipTo"):
    if country_code_upper in ['US', 'CA']:
        input_state_upper_stripped = str(state_input or '').upper().strip()
        if len(input_state_upper_stripped) == 2 and input_state_upper_stripped in VALID_US_CA_STATE_CODES:
            return input_state_upper_stripped
        else:
            processed_code = STATE_MAPPING_US_CA.get(str(state_input or '').lower().strip(), "")
            if not processed_code:
                print(f"ERROR SHIPPING_PAYLOAD ({party_type}): {country_code_upper} State/Province '{state_input}' could not be mapped to a 2-letter code.")
                return None
            return processed_code
    else:
        processed_code = str(state_input or '').strip()
        if not processed_code:
            print(f"WARN SHIPPING_PAYLOAD ({party_type}): State/Province is empty for country {country_code_upper}.")
        return processed_code


def get_ups_oauth_token():
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
    method_name = (method_name_from_bc or "").lower().strip()
    shipping_method_mapping = {
        'ups® ground': '03', 'ups ground': '03', 'ground': '03',
        'ups® next day air®': '01', 'ups next day air': '01', 'next day air': '01',
        'ups® 2nd day air®': '02', 'ups 2nd day air': '02', 'second day air': '02',
        'ups® next day air early a.m.®': '14', 'ups next day air early a.m.': '14',
        'next day air early am': '14', 'ups next day air early am': '14',
        'ups® worldwide expedited®': '08', 'ups worldwide expedited': '08', 'worldwide expedited': '08',
        'ups worldwide express': '07', 'worldwide express': '07',
        'ups® worldwide express plus®': '54', 'ups worldwide express plus': '54', 'worldwide express plus': '54',
        'ups worldwide saver': '65', 'worldwide saver': '65',
        'free shipping': '03',
    }
    # Direct mapping for service codes passed from the frontend
    if method_name in shipping_method_mapping.values():
        print(f"DEBUG UPS_MAP: Directly using provided service code '{method_name}'")
        return method_name
        
    code = shipping_method_mapping.get(method_name)
    if code is None:
        if 'next day air early' in method_name or 'early a.m.' in method_name or 'early am' in method_name: code = '14'
        elif 'next day air' in method_name or 'nda' in method_name: code = '01'
        elif '2nd day air' in method_name or 'second day' in method_name: code = '02'
        elif 'worldwide expedited' in method_name: code = '08'
        elif 'worldwide express plus' in method_name: code = '54'
        elif 'worldwide express' in method_name: code = '07'
        elif 'worldwide saver' in method_name: code = '65'
        elif 'ground' in method_name: code = '03'
        else:
            print(f"WARN UPS_MAP: Could not map UPS service '{method_name_from_bc}'. Defaulting to '03' (Ground).")
            code = '03'
    print(f"DEBUG UPS_MAP: Mapped '{method_name_from_bc}' to UPS Service Code '{code}'")
    return code


def map_shipping_method_to_fedex_code(method_name_from_bc):
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
    if method_name_from_bc in mapping.values():
        print(f"DEBUG FEDEX_MAP: Mapped (direct code) '{method_name_from_bc}' to FedEx Service Code '{method_name_from_bc}'")
        return method_name_from_bc
    api_code = mapping.get(method_name_lower)
    if api_code:
        print(f"DEBUG FEDEX_MAP: Mapped (lower case) '{method_name_from_bc}' to FedEx Service Code '{api_code}'")
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

def generate_ups_label_raw(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token,
                           is_bill_to_customer_ups_account=False, customer_ups_account_number=None, customer_ups_account_zipcode=None):
    if not access_token: print("ERROR UPS_LABEL_RAW: Access token not provided."); return None, None
    bc_order_id_str = str(order_data.get('bigcommerce_order_id', 'N/A_UnknownOrder'))
    unique_ts = int(datetime.now(timezone.utc).timestamp()*1000)
    headers = {
        "Authorization": f"Bearer {access_token}", "Content-Type": "application/json",
        "Accept": "application/json", "transId": f"Order_{bc_order_id_str}_{unique_ts}",
        "transactionSrc": "G1POApp_v15_UPSClearBilling"
    }
    ups_service_code = map_shipping_method_to_ups_code(customer_shipping_method_name)

    ship_to_country_code_from_data = order_data.get('customer_shipping_country_iso2', 'US')
    print(f"DEBUG UPS_LABEL_RAW (ShipTo): Raw country_iso2: '{ship_to_country_code_from_data}'")
    ship_to_country_code_upper = ship_to_country_code_from_data.upper() if ship_to_country_code_from_data and len(ship_to_country_code_from_data) == 2 else 'US'
    if not ship_to_country_code_from_data or len(ship_to_country_code_from_data) != 2:
        print(f"WARN UPS_LABEL_RAW (ShipTo): Invalid/missing 'customer_shipping_country_iso2' ('{ship_to_country_code_from_data}'). Defaulting to 'US'. Original full name: '{order_data.get('customer_shipping_country')}'")
        ship_to_country_code_upper = 'US'
    print(f"DEBUG UPS_LABEL_RAW (ShipTo): Processed CountryCode: '{ship_to_country_code_upper}'")
    ship_to_state_input = order_data.get('customer_shipping_state', '')
    ship_to_state_processed = _get_processed_state_code(ship_to_state_input, ship_to_country_code_upper, "ShipTo")
    if ship_to_state_processed is None: return None, None
    print(f"DEBUG UPS_LABEL_RAW (ShipTo): Processed StateProvinceCode: '{ship_to_state_processed}' from input '{ship_to_state_input}'")

    ship_from_country_input = ship_from_address.get('country', 'US')
    print(f"DEBUG UPS_LABEL_RAW (Shipper): Raw country: '{ship_from_country_input}'")
    ship_from_country_code_upper = ship_from_country_input.upper() if ship_from_country_input and len(ship_from_country_input) == 2 else 'US'
    if not ship_from_country_input or len(ship_from_country_input) != 2:
         print(f"WARN UPS_LABEL_RAW (Shipper): Invalid or non-ISO2 'country' ('{ship_from_country_input}') in ship_from_address. Defaulting to 'US'.")
         ship_from_country_code_upper = 'US'
    print(f"DEBUG UPS_LABEL_RAW (Shipper): Processed CountryCode: '{ship_from_country_code_upper}'")
    ship_from_state_input = ship_from_address.get('state', '')
    ship_from_state_processed = _get_processed_state_code(ship_from_state_input, ship_from_country_code_upper, "Shipper")
    if ship_from_state_processed is None: return None, None
    print(f"DEBUG UPS_LABEL_RAW (Shipper): Processed StateProvinceCode: '{ship_from_state_processed}' from input '{ship_from_state_input}'")

    ship_to_company_name = order_data.get('customer_company', '').strip()
    ship_to_contact_person_name = order_data.get('customer_name', '').strip()
    
    # Determine the base name for ShipTo.Name
    base_ups_ship_to_name = ship_to_company_name if ship_to_company_name else ship_to_contact_person_name
    if not base_ups_ship_to_name: 
        print("ERROR UPS Payload: ShipTo Name (company or contact) is missing."); return None, None
    
    # Truncate ups_ship_to_name to 35 characters
    ups_ship_to_name = base_ups_ship_to_name[:35]
    print(f"DEBUG UPS_LABEL_RAW (ShipTo Name): Original='{base_ups_ship_to_name}', Truncated='{ups_ship_to_name}'")

    # AttentionName can also be truncated if necessary, though the limit might be different or less strict.
    # For now, let's assume it's mainly the Name field. If AttentionName also causes issues, apply similar truncation.
    ups_attention_name = ship_to_contact_person_name if ship_to_company_name and ship_to_contact_person_name else ship_to_contact_person_name
    ups_attention_name = ups_attention_name[:35] # Example: Truncating AttentionName as well
    print(f"DEBUG UPS_LABEL_RAW (AttentionName): Original Contact='{ship_to_contact_person_name}', Truncated Attention='{ups_attention_name}'")

    # Construct Shipper block. ShipperNumber might be removed later if billing third party.
    base_ship_from_name = ship_from_address.get('name', '').strip()
    if not base_ship_from_name:
        print("ERROR UPS Payload: ShipFrom Name (Shipper.Name) is missing from ship_from_address.")
        # Depending on how critical this is, you might return None, None or use a default.
        # For now, let's assume it's critical as per the UPS error.
        return None, None 
    
    truncated_ship_from_name = base_ship_from_name[:35]
    print(f"DEBUG UPS_LABEL_RAW (Shipper Name): Original='{base_ship_from_name}', Truncated='{truncated_ship_from_name}'")

    base_ship_from_attention_name = ship_from_address.get('contact_person', '').strip()
    # If AttentionName is not critical or can be omitted if too long, adjust logic.
    # For consistency, truncating it if present.
    truncated_ship_from_attention_name = base_ship_from_attention_name[:35]
    if base_ship_from_attention_name: # Only log if there was an original attention name
        print(f"DEBUG UPS_LABEL_RAW (Shipper AttentionName): Original='{base_ship_from_attention_name}', Truncated='{truncated_ship_from_attention_name}'")

    shipper_payload_block = {
        "Name": truncated_ship_from_name, 
        "AttentionName": truncated_ship_from_attention_name,
        "Phone": {"Number": (ship_from_address.get('phone') or "").replace('-', '').replace('(', '').replace(')', '').replace(' ', '')},
        "Address": {
            "AddressLine": [addr for addr in [ship_from_address.get('street_1'), ship_from_address.get('street_2')] if addr and addr.strip()],
            "City": ship_from_address.get('city'), "StateProvinceCode": ship_from_state_processed,
            "PostalCode": ship_from_address.get('zip'), "CountryCode": ship_from_country_code_upper
        }}
    # Add ShipperNumber only if it's not a third-party billing scenario where it might conflict
    # This will be decided after checking is_bill_to_customer_ups_account

    payload_shipment_part = {
        "Description": order_data.get('customer_company', "Order") + " Shipment", # Shipper block added below
        "ShipTo": {"Name": ups_ship_to_name, "AttentionName": ups_attention_name,
            "Phone": {"Number": (order_data.get('customer_phone') or "").replace('-', '').replace('(', '').replace(')', '').replace(' ', '')},
            "Address": {"AddressLine": [addr for addr in [order_data.get('customer_shipping_address_line1'), order_data.get('customer_shipping_address_line2')] if addr and addr.strip()],
                "City": order_data.get('customer_shipping_city'), "StateProvinceCode": ship_to_state_processed,
                "PostalCode": str(order_data.get('customer_shipping_zip', '')), "CountryCode": ship_to_country_code_upper
                }},
        "Service": {"Code": ups_service_code},
        "Package": [{"Description": "Box of Parts", "Packaging": {"Code": "02"},
            "PackageWeight": {"UnitOfMeasurement": {"Code": "LBS"}, "Weight": str(round(float(max(0.1, total_weight_lbs)), 1))},
            "ReferenceNumber": [{"Code": "02", "Value": str(bc_order_id_str)}]}]}

    # Explicitly remove any existing payment keys before setting the new one
    print(f"DEBUG UPS_PAYMENT_PRE-CLEAN: Keys in payload_shipment_part: {list(payload_shipment_part.keys())}")
    payload_shipment_part.pop("PaymentInformation", None)
    payload_shipment_part.pop("PaymentDetails", None)
    print(f"DEBUG UPS_PAYMENT_POST-CLEAN: Keys in payload_shipment_part: {list(payload_shipment_part.keys())}")

    is_valid_ups_zip = customer_ups_account_zipcode and \
                       isinstance(customer_ups_account_zipcode, str) and \
                       customer_ups_account_zipcode.strip() and \
                       customer_ups_account_zipcode.strip().lower() != 'none'

    print(f"DEBUG UPS_PAYMENT_CHECK: is_bill_to_customer_ups_account = {is_bill_to_customer_ups_account} (type: {type(is_bill_to_customer_ups_account)})")
    print(f"DEBUG UPS_PAYMENT_CHECK: customer_ups_account_number = '{customer_ups_account_number}' (type: {type(customer_ups_account_number)})")
    print(f"DEBUG UPS_PAYMENT_CHECK: customer_ups_account_zipcode (effective) = '{customer_ups_account_zipcode}' (type: {type(customer_ups_account_zipcode)})")
    print(f"DEBUG UPS_PAYMENT_CHECK: is_valid_ups_zip (derived from effective_zip) = {is_valid_ups_zip}")

    if is_bill_to_customer_ups_account:
        if customer_ups_account_number and is_valid_ups_zip:
            print(f"DEBUG UPS_LABEL_RAW: Using 'PaymentInformation' for BillThirdParty (UPS). Account: {customer_ups_account_number}, Zip: {customer_ups_account_zipcode}")
            third_party_country_code_for_ups = ship_to_country_code_upper

            # Construct as PaymentInformation with ShipmentCharge as an object
            payment_information_payload = { # Renamed from payment_details_payload
                "ShipmentCharge": {         # ShipmentCharge is now an object, not a list
                    "Type": "01",
                    "BillThirdParty": {
                        "AccountNumber": str(customer_ups_account_number),
                        "Address": {
                            "PostalCode": str(customer_ups_account_zipcode).strip(),
                            "CountryCode": third_party_country_code_for_ups
                        }
                    }
                }
            }
            payload_shipment_part["PaymentInformation"] = payment_information_payload # Changed from PaymentDetails
            shipper_payload_block["ShipperNumber"] = UPS_ACCOUNT_NUMBER
            print(f"DEBUG UPS_PAYMENT_FINAL_SET: PaymentInformation set. ShipperNumber {UPS_ACCOUNT_NUMBER} retained in Shipper block. Keys: {list(payload_shipment_part.keys())}")
        else:
                print(f"ERROR UPS_LABEL_RAW: Attempted BillThirdParty (UPS) but data was insufficient. Account: '{customer_ups_account_number}', Valid Zip: {is_valid_ups_zip} (from '{customer_ups_account_zipcode}'). Label generation for this PO will fail.")
                return None, None
    else: # Bill G1's account (Shipper)
        print(f"DEBUG UPS_LABEL_RAW: Using 'PaymentInformation' for BillShipper (UPS). Account: {UPS_ACCOUNT_NUMBER}")
        if not UPS_ACCOUNT_NUMBER or not UPS_ACCOUNT_NUMBER.strip():
            print(f"CRITICAL ERROR UPS_LABEL_RAW: UPS_BILLING_ACCOUNT_NUMBER (G1's account) missing for BillShipper."); return None, None

        # BillShipper also uses PaymentInformation with ShipmentCharge as an object
        payment_information_payload = { # Consistent naming
            "ShipmentCharge": {         # ShipmentCharge is an object
                "Type": "01",
                "BillShipper": {
                    "AccountNumber": UPS_ACCOUNT_NUMBER
                }
            }
        }
        payload_shipment_part["PaymentInformation"] = payment_information_payload
        shipper_payload_block["ShipperNumber"] = UPS_ACCOUNT_NUMBER
        print(f"DEBUG UPS_PAYMENT_FINAL_SET: PaymentInformation set. ShipperNumber {UPS_ACCOUNT_NUMBER} set in Shipper block. Keys: {list(payload_shipment_part.keys())}")


    payload_shipment_part["Shipper"] = shipper_payload_block # Add Shipper block to the shipment part

    payload = { "ShipmentRequest": { "Request": {"RequestOption": "nonvalidate", "TransactionReference": {"CustomerContext": f"Order_{bc_order_id_str}"}}, "Shipment": payload_shipment_part, "LabelSpecification": {"LabelImageFormat": {"Code": "GIF"}, "HTTPUserAgent": "Mozilla/5.0"}}}
    print(f"DEBUG UPS_INTL_SHIPMENT: Sending payload to {UPS_SHIPPING_API_ENDPOINT}") # This line you already have

    try:
        response = requests.post(UPS_SHIPPING_API_ENDPOINT, headers=headers, json=payload)
        response_data = response.json()
        if response.status_code == 200 and response_data.get("ShipmentResponse", {}).get("Response", {}).get("ResponseStatus", {}).get("Code") == "1":
            print(f"DEBUG UPS_LABEL_RAW (Full Response for Success Code 1): {json.dumps(response_data, indent=2, ensure_ascii=False)}", flush=True)
        response.raise_for_status()
        shipment_response = response_data.get("ShipmentResponse", {})
        response_status_obj = shipment_response.get("Response", {}).get("ResponseStatus", {})
        if response_status_obj.get("Code") == "1":
            shipment_results = shipment_response.get("ShipmentResults", {})
            tracking_number = shipment_results.get("ShipmentIdentificationNumber")
            package_results_list = shipment_results.get("PackageResults", [])
            label_image_base64 = None
            if package_results_list and isinstance(package_results_list, list) and len(package_results_list) > 0 and package_results_list[0]:
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

def generate_ups_international_shipment(shipment_payload_from_frontend):
    """
    Generates a UPS international shipping label and documents using a detailed payload from the frontend.
    If the label is returned as GIF, it attempts to convert it to PDF.

    Args:
        shipment_payload_from_frontend (dict): The complete JSON payload, which is expected
                                               to contain the 'ShipmentRequest' structure.

    Returns:
        tuple: A tuple containing (pdf_bytes, tracking_number).
               The pdf_bytes will be PDF, even if the original label was GIF.
               Returns (None, None) on failure.
               Returns (None, tracking_number) if tracking is found but the label processing fails.
    """
    print("DEBUG UPS_INTL_SHIPMENT: Initiating international shipment generation.")

    access_token = get_ups_oauth_token()
    if not access_token:
        print("ERROR UPS_INTL_SHIPMENT: Failed to get UPS OAuth token.")
        return None, None

    # Make a deep copy if you need to modify the original shipment_payload_from_frontend
    # elsewhere, though for this function, modifying it directly is usually fine.
    payload = shipment_payload_from_frontend

    if 'ShipmentRequest' not in payload or 'Shipment' not in payload.get('ShipmentRequest', {}):
        print(f"ERROR UPS_INTL_SHIPMENT: The provided payload is missing 'ShipmentRequest' or 'ShipmentRequest.Shipment'.")
        return None, None

    # --- START STATE/PROVINCE CODE TRANSFORMATION ---
    # Modify StateProvinceCode for ShipTo address if US or CA
    try:
        ship_to_address_container = payload.get('ShipmentRequest', {}).get('Shipment', {}).get('ShipTo', {})
        if ship_to_address_container and 'Address' in ship_to_address_container:
            ship_to_address = ship_to_address_container['Address']
            ship_to_country_code = ship_to_address.get('CountryCode', '').upper()
            ship_to_state_input = ship_to_address.get('StateProvinceCode')

            if ship_to_country_code == 'CA' and ship_to_state_input: # Specifically for Canada, or use `in ['US', 'CA']` if US also needs it
                print(f"DEBUG UPS_INTL_SHIPMENT (ShipTo): Original StateProvinceCode: '{ship_to_state_input}' for Country: '{ship_to_country_code}'")
                processed_ship_to_state = _get_processed_state_code(ship_to_state_input, ship_to_country_code, "ShipTo")
                if processed_ship_to_state: # _get_processed_state_code returns "" for non-US/CA or mapped code
                    payload['ShipmentRequest']['Shipment']['ShipTo']['Address']['StateProvinceCode'] = processed_ship_to_state
                    print(f"DEBUG UPS_INTL_SHIPMENT (ShipTo): Processed StateProvinceCode: '{processed_ship_to_state}'")
                elif processed_ship_to_state is None: # Mapping error specifically for US/CA
                     print(f"ERROR UPS_INTL_SHIPMENT (ShipTo): State processing failed for '{ship_to_state_input}', '{ship_to_country_code}'. Value not updated.")
    except Exception as e_shipto_state:
        print(f"WARN UPS_INTL_SHIPMENT: Could not process ShipTo StateProvinceCode: {e_shipto_state}")

    # Modify StateProvinceCode for SoldTo address (within InternationalForms) if US or CA
    try:
        international_forms = payload.get('ShipmentRequest', {}).get('Shipment', {}).get('ShipmentServiceOptions', {}).get('InternationalForms', {})
        if international_forms and 'Contacts' in international_forms and 'SoldTo' in international_forms['Contacts']:
            sold_to_address_container = international_forms['Contacts']['SoldTo']
            if sold_to_address_container and 'Address' in sold_to_address_container:
                sold_to_address = sold_to_address_container['Address']
                sold_to_country_code = sold_to_address.get('CountryCode', '').upper()
                sold_to_state_input = sold_to_address.get('StateProvinceCode')

                if sold_to_country_code == 'CA' and sold_to_state_input: # Specifically for Canada
                    print(f"DEBUG UPS_INTL_SHIPMENT (SoldTo): Original StateProvinceCode: '{sold_to_state_input}' for Country: '{sold_to_country_code}'")
                    processed_sold_to_state = _get_processed_state_code(sold_to_state_input, sold_to_country_code, "SoldTo")
                    if processed_sold_to_state:
                        payload['ShipmentRequest']['Shipment']['ShipmentServiceOptions']['InternationalForms']['Contacts']['SoldTo']['Address']['StateProvinceCode'] = processed_sold_to_state
                        print(f"DEBUG UPS_INTL_SHIPMENT (SoldTo): Processed StateProvinceCode: '{processed_sold_to_state}'")
                    elif processed_sold_to_state is None:
                         print(f"ERROR UPS_INTL_SHIPMENT (SoldTo): State processing failed for '{sold_to_state_input}', '{sold_to_country_code}'. Value not updated.")
    except Exception as e_soldto_state:
        print(f"WARN UPS_INTL_SHIPMENT: Could not process SoldTo StateProvinceCode: {e_soldto_state}")

    # Note: The Shipper address is typically your fixed US address, so transformation is unlikely needed there.
    # If it could be Canadian and come from a dynamic source, you'd add similar logic for:
    # payload['ShipmentRequest']['Shipment']['Shipper']['Address']
    # --- END STATE/PROVINCE CODE TRANSFORMATION ---

    customer_context = payload.get('ShipmentRequest', {}).get('Request', {}).get('TransactionReference', {}).get('CustomerContext', 'UnknownOrder')
    unique_ts = int(datetime.now(timezone.utc).timestamp() * 1000)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "transId": f"{customer_context}_{unique_ts}", # Ensure this is unique per request
        "transactionSrc": "G1POApp_v15_UPSIntl"
    }

    requested_label_format_code = payload.get('ShipmentRequest', {}).get('LabelSpecification', {}).get('LabelImageFormat', {}).get('Code', 'GIF').upper()
    print(f"DEBUG UPS_INTL_SHIPMENT: Requested label format from payload: {requested_label_format_code}")

    # Log the payload *after* potential modifications
    print(f"DEBUG UPS_INTL_SHIPMENT: EXACT PAYLOAD BEING SENT TO UPS API (after state/province conversion):\n{json.dumps(payload, indent=2)}")

    try:
        response = requests.post(UPS_SHIPPING_API_ENDPOINT, headers=headers, json=payload)
        response_data = response.json()
        
        if response.status_code == 200 and response_data.get("ShipmentResponse", {}).get("Response", {}).get("ResponseStatus", {}).get("Code") == "1":
            print(f"DEBUG UPS_INTL_SHIPMENT (Full Response for Success Code 1): {json.dumps(response_data, indent=2, ensure_ascii=False)}", flush=True)

        response.raise_for_status() 

        shipment_response = response_data.get("ShipmentResponse", {})
        response_status = shipment_response.get("Response", {}).get("ResponseStatus", {})

        if response_status.get("Code") == "1":  # '1' indicates success
            shipment_results = shipment_response.get("ShipmentResults", {})
            tracking_number = shipment_results.get("ShipmentIdentificationNumber")
            
            package_results_list = shipment_results.get("PackageResults", [])
            label_image_base64 = None
            actual_label_format_from_response = "UNKNOWN" # Initialize

            if package_results_list and isinstance(package_results_list, list) and len(package_results_list) > 0:
                shipping_label_data = package_results_list[0].get("ShippingLabel", {})
                label_image_base64 = shipping_label_data.get("GraphicImage")
                actual_label_format_from_response = shipping_label_data.get("ImageFormat", {}).get("Code", "UNKNOWN").upper()
                print(f"DEBUG UPS_INTL_SHIPMENT: Actual label format from UPS response: {actual_label_format_from_response}")


            if tracking_number and label_image_base64:
                print(f"INFO UPS_INTL_SHIPMENT: Success! Tracking: {tracking_number}. Label data (format: {actual_label_format_from_response}) received.")
                try:
                    raw_image_bytes = base64.b64decode(label_image_base64)
                    
                    # Check if conversion to PDF is needed
                    if actual_label_format_from_response == 'GIF': # If UPS confirms it sent a GIF
                        print(f"DEBUG UPS_INTL_SHIPMENT: Label format is GIF. Attempting conversion to PDF for tracking {tracking_number}.")
                        pdf_bytes = convert_image_bytes_to_pdf_bytes(raw_image_bytes, image_format="GIF")
                        if not pdf_bytes:
                            print(f"ERROR UPS_INTL_SHIPMENT: Failed to convert GIF label to PDF for tracking {tracking_number}.")
                            return None, tracking_number # Return tracking, but no label PDF
                        print(f"DEBUG UPS_INTL_SHIPMENT: GIF label successfully converted to PDF for tracking {tracking_number}.")
                    elif actual_label_format_from_response == 'PDF': # If UPS sent a PDF
                        print(f"DEBUG UPS_INTL_SHIPMENT: Label format is PDF. Using directly for tracking {tracking_number}.")
                        pdf_bytes = raw_image_bytes
                    else: # Unknown or other format that we don't explicitly handle for conversion
                        print(f"WARN UPS_INTL_SHIPMENT: Label format from UPS is '{actual_label_format_from_response}'. Proceeding with raw bytes. This might not be a PDF.")
                        pdf_bytes = raw_image_bytes # Pass through, hope for the best or handle downstream

                    return pdf_bytes, tracking_number
                except Exception as processing_err:
                    print(f"ERROR UPS_INTL_SHIPMENT: Failed to decode/process label data for tracking {tracking_number}: {processing_err}")
                    traceback.print_exc()
                    return None, tracking_number 
            elif tracking_number:
                print(f"WARN UPS_INTL_SHIPMENT: Tracking number {tracking_number} obtained, but no label image (GraphicImage) was found in the response.")
                return None, tracking_number
            else:
                print("ERROR UPS_INTL_SHIPMENT: API response code was '1' (Success), but no tracking number found.")
                return None, None
        else:
            error_description = response_status.get("Description", "Unknown UPS Error")
            alerts = shipment_response.get("Response", {}).get("Alert", [])
            if not isinstance(alerts, list): alerts = [alerts]
            error_details_str = "; ".join([f"Code {alert.get('Code')}: {alert.get('Description')}" for alert in alerts if alert]) if alerts else "No specific alerts."
            print(f"ERROR UPS_INTL_SHIPMENT: UPS API returned an error. Description: '{error_description}'. Details: '{error_details_str}'.")
            print(f"Full Error Response: {json.dumps(response_data, indent=2)}")
            return None, None

    except requests.exceptions.HTTPError as http_err:
        response_content = "Could not decode JSON or no response body."
        try: response_content = http_err.response.json() if http_err.response is not None else "No response object."
        except json.JSONDecodeError: response_content = http_err.response.text if http_err.response is not None else "No response text."
        print(f"ERROR UPS_INTL_SHIPMENT: HTTPError occurred: {http_err}. Response: {str(response_content)[:1000]}")
        return None, None
    except requests.exceptions.RequestException as req_err:
        print(f"ERROR UPS_INTL_SHIPMENT: RequestException occurred: {req_err}")
        traceback.print_exc()
        return None, None
    except json.JSONDecodeError as json_err:
        response_text_snippet = response.text[:500] if hasattr(response, 'text') and response.text else "N/A"
        print(f"ERROR UPS_INTL_SHIPMENT: Failed to decode JSON response from UPS API: {json_err}. Response snippet: {response_text_snippet}")
        return None, None
    except Exception as e:
        print(f"ERROR UPS_INTL_SHIPMENT: An unexpected exception occurred: {e}")
        traceback.print_exc()
        return None, None

def generate_fedex_label_raw(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token):
    if not access_token:
        print("ERROR FEDEX_LABEL_RAW: FedEx Access token not provided.")
        return None, None
    if not FEDEX_SHIPPER_ACCOUNT_NUMBER: # This is G1's account, still needed for the API request structure, but not for payment.
        print("ERROR FEDEX_LABEL_RAW: FEDEX_SHIPPER_ACCOUNT_NUMBER (G1's main account) not configured for API call.")
        return None, None

    fedex_service_type_enum = map_shipping_method_to_fedex_code(customer_shipping_method_name)
    if not fedex_service_type_enum:
        print(f"ERROR FEDEX_LABEL_RAW: Could not map shipping method '{customer_shipping_method_name}'.")
        return None, None

    ship_to_street_lines = [s for s in [order_data.get('customer_shipping_address_line1'), order_data.get('customer_shipping_address_line2')] if s and s.strip()]
    if not ship_to_street_lines:
        print("ERROR FEDEX_LABEL_RAW: Ship To address line 1 is missing.")
        return None, None

    # --- State/Province Code Processing (remains the same) ---
    ship_to_country_code_from_data = order_data.get('customer_shipping_country_iso2', 'US')
    # print(f"DEBUG FEDEX_LABEL_RAW (ShipTo): Raw country_iso2: '{ship_to_country_code_from_data}'")
    ship_to_country_code_upper = ship_to_country_code_from_data.upper() if ship_to_country_code_from_data and len(ship_to_country_code_from_data) == 2 else 'US'
    if not ship_to_country_code_from_data or len(ship_to_country_code_from_data) != 2:
        print(f"WARN FEDEX_LABEL_RAW (ShipTo): Invalid/missing 'customer_shipping_country_iso2' ('{ship_to_country_code_from_data}'). Defaulting to 'US'. Original full name: '{order_data.get('customer_shipping_country')}'")
        ship_to_country_code_upper = 'US'
    # print(f"DEBUG FEDEX_LABEL_RAW (ShipTo): Processed CountryCode: '{ship_to_country_code_upper}'")
    ship_to_state_input = order_data.get('customer_shipping_state', '')
    ship_to_state_processed = _get_processed_state_code(ship_to_state_input, ship_to_country_code_upper, "ShipTo")
    if ship_to_state_processed is None: return None, None
    # print(f"DEBUG FEDEX_LABEL_RAW (ShipTo): Processed StateProvinceCode: '{ship_to_state_processed}' from input '{ship_to_state_input}'")

    ship_from_country_input = ship_from_address.get('country', 'US')
    # print(f"DEBUG FEDEX_LABEL_RAW (Shipper): Raw country: '{ship_from_country_input}'")
    ship_from_country_code_upper = ship_from_country_input.upper() if ship_from_country_input and len(ship_from_country_input) == 2 else 'US'
    if not ship_from_country_input or len(ship_from_country_input) != 2:
         print(f"WARN FEDEX_LABEL_RAW (Shipper): Invalid or non-ISO2 'country' ('{ship_from_country_input}') in ship_from_address. Defaulting to 'US'.")
         ship_from_country_code_upper = 'US'
    # print(f"DEBUG FEDEX_LABEL_RAW (Shipper): Processed CountryCode: '{ship_from_country_code_upper}'")
    ship_from_state_input = ship_from_address.get('state', '')
    ship_from_state_processed = _get_processed_state_code(ship_from_state_input, ship_from_country_code_upper, "Shipper")
    if ship_from_state_processed is None: return None, None
    # print(f"DEBUG FEDEX_LABEL_RAW (Shipper): Processed StateProvinceCode: '{ship_from_state_processed}' from input '{ship_from_state_input}'")
    # --- End State/Province Code Processing ---

    # --- Payment Information for FedEx (MUST BE RECIPIENT) ---
    is_bill_to_customer_fedex_account_flag = order_data.get('is_bill_to_customer_fedex_account', False) # This flag comes from the frontend payload
    customer_fedex_acct_num_from_payload = order_data.get('customer_fedex_account_number') # This also comes from the frontend payload

    if not is_bill_to_customer_fedex_account_flag or not customer_fedex_acct_num_from_payload:
        error_msg = (f"ERROR FEDEX_LABEL_RAW: FedEx shipments must be 'Bill Recipient'. "
                     f"Required data from frontend payload was missing or invalid. "
                     f"is_bill_to_customer_fedex_account: {is_bill_to_customer_fedex_account_flag}, "
                     f"customer_fedex_account_number: '{customer_fedex_acct_num_from_payload}'.")
        print(error_msg)
        # Optionally, you could raise an exception here that the calling route can catch
        # to send a more specific error message back to the frontend.
        return None, None # Cannot proceed without recipient billing details

    print(f"DEBUG FEDEX_LABEL_RAW: Processing as Bill Recipient FedEx. Account: {customer_fedex_acct_num_from_payload}")
    payment_info = {
        "paymentType": "RECIPIENT",
        "payor": {
            "responsibleParty": {
                "accountNumber": {"value": str(customer_fedex_acct_num_from_payload)}
            }
        }
    }
    # --- End Payment Information ---

    shipper_contact_name = ship_from_address.get('contact_person', ship_from_address.get('name', 'Shipping Dept'))
    shipper_company_name = ship_from_address.get('name', 'Your Company LLC') # This is G1's company name

    if not all([ship_from_address.get('street_1'), ship_from_address.get('city'), ship_from_state_processed, ship_from_address.get('zip'), ship_from_country_code_upper, ship_from_address.get('phone')]):
        print("ERROR FEDEX_LABEL_RAW: Shipper (Ship From) address not fully configured or state mapping failed.")
        return None, None

    requested_shipment_payload = {
        "shipper": {
            "contact": {"personName": shipper_contact_name, "companyName": shipper_company_name, "phoneNumber": (ship_from_address.get('phone') or "").replace('-', '').replace('(', '').replace(')', '').replace(' ', '')},
            "address": {"streetLines": [s for s in [ship_from_address.get('street_1'), ship_from_address.get('street_2')] if s and s.strip()], "city": ship_from_address.get('city'), "stateOrProvinceCode": ship_from_state_processed, "postalCode": str(ship_from_address.get('zip')), "countryCode": ship_from_country_code_upper}
        },
        "recipients": [{
            "contact": {"personName": order_data.get('customer_name', 'N/A'), "companyName": order_data.get('customer_company', ''), "phoneNumber": (order_data.get('customer_phone') or "").replace('-', '').replace('(', '').replace(')', '').replace(' ', '')},
            "address": {"streetLines": ship_to_street_lines, "city": order_data.get('customer_shipping_city'), "stateOrProvinceCode": ship_to_state_processed, "postalCode": str(order_data.get('customer_shipping_zip', '')), "countryCode": ship_to_country_code_upper, "residential": False }
        }],
        "shipDatestamp": datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        "serviceType": fedex_service_type_enum,
        "packagingType": "YOUR_PACKAGING",
        "pickupType": "DROPOFF_AT_FEDEX_LOCATION", # Or USE_SCHEDULED_PICKUP if applicable
        "shippingChargesPayment": payment_info,
        "labelSpecification": {"imageType": "PDF", "labelStockType": "PAPER_85X11_TOP_HALF_LABEL"}, # Or your preferred stock
        "requestedPackageLineItems": [{
            "weight": {"units": "LB", "value": round(float(max(0.1, total_weight_lbs)), 1)},
            "customerReferences": [{"customerReferenceType": "CUSTOMER_REFERENCE", "value": str(order_data.get('bigcommerce_order_id', 'N/A'))}]
        }]
    }

    # The accountNumber for the API call itself is G1's main FedEx account, not the payor necessarily.
    final_api_payload = {
        "labelResponseOptions": "LABEL",
        "requestedShipment": requested_shipment_payload,
        "accountNumber": {"value": str(FEDEX_SHIPPER_ACCOUNT_NUMBER)} # G1's account for API authentication/authorization
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-locale": "en_US", # Or your locale
        "Content-Type": "application/json"
    }

    try:
        # ... (rest of the try-except block for API call, response handling, and base64 decoding remains the same) ...
        response = requests.post(FEDEX_SHIP_API_URL, headers=headers, json=final_api_payload)
        print(f"DEBUG FEDEX_LABEL_RAW: FedEx API Response Status: {response.status_code}", flush=True)
        # Log the exact payload sent for debugging purposes, be mindful of sensitive data in production logs
        # print(f"DEBUG FEDEX_LABEL_RAW: Payload sent to FedEx: {json.dumps(final_api_payload, indent=2)}")
        response_data = response.json()
        # print(f"DEBUG FEDEX_LABEL_RAW: Response Data from FedEx: {json.dumps(response_data, indent=2)}")
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        if response_data.get("errors"):
            errors = response_data.get("errors", [])
            error_messages = "; ".join([f"Code {err.get('code')}: {err.get('message')}" for err in errors])
            print(f"ERROR FEDEX_LABEL_RAW: FedEx API returned errors: {error_messages}. Full: {json.dumps(errors, indent=2)}")
            return None, None

        output = response_data.get("output", {})
        transaction_shipments = output.get("transactionShipments", [])
        if not transaction_shipments:
            print(f"ERROR FEDEX_LABEL_RAW: 'transactionShipments' missing from FedEx response. Output: {json.dumps(output, indent=2)}")
            return None, None

        first_shipment = transaction_shipments[0]
        tracking_number = first_shipment.get("masterTrackingNumber")
        encoded_label_data = None

        piece_responses = first_shipment.get("pieceResponses", [])
        if piece_responses and piece_responses[0].get("packageDocuments"):
            for doc in piece_responses[0].get("packageDocuments", []):
                if doc.get("encodedLabel") or doc.get("content"): # Check for both, sometimes 'content' is used
                    encoded_label_data = doc.get("encodedLabel") or doc.get("content")
                    break
        elif first_shipment.get("packageDocuments"): # Fallback for older or different response structures
             for doc in first_shipment.get("packageDocuments", []):
                if doc.get("encodedLabel") or doc.get("content"):
                    encoded_label_data = doc.get("encodedLabel") or doc.get("content")
                    break
        
        if tracking_number and encoded_label_data:
            print(f"INFO FEDEX_LABEL_RAW: FedEx Label generated successfully. Tracking: {tracking_number}")
            try:
                return base64.b64decode(encoded_label_data), tracking_number
            except Exception as b64_e:
                print(f"ERROR FEDEX_LABEL_RAW: Failed to decode base64 label data for tracking {tracking_number}: {b64_e}")
                return None, tracking_number # Return tracking even if decoding fails
        elif tracking_number:
            print(f"WARN FEDEX_LABEL_RAW: Tracking number {tracking_number} obtained, but no encoded label data found in the response. Details: {json.dumps(first_shipment, indent=2)}")
            return None, tracking_number
        else:
            print(f"ERROR FEDEX_LABEL_RAW: No tracking number or label data found in FedEx response. Details: {json.dumps(first_shipment, indent=2)}")
            return None, None

    except requests.exceptions.HTTPError as http_err:
        response_content = "Could not decode JSON or no response object available."
        if http_err.response is not None:
            try:
                response_content = http_err.response.json()
            except json.JSONDecodeError:
                response_content = http_err.response.text
        print(f"ERROR FEDEX_LABEL_RAW: HTTPError occurred during FedEx API call: {http_err}. Response: {str(response_content)[:1000]}")
        return None, None
    except requests.exceptions.RequestException as req_err:
        print(f"ERROR FEDEX_LABEL_RAW: RequestException occurred during FedEx API call: {req_err}")
        traceback.print_exc()
        return None, None
    except json.JSONDecodeError as json_err: # If response.json() fails
        response_text_snippet = response.text[:500] if hasattr(response, 'text') and response.text else "N/A"
        print(f"ERROR FEDEX_LABEL_RAW: Failed to decode JSON response from FedEx API: {json_err}. Response snippet: {response_text_snippet}")
        return None, None
    except Exception as e:
        print(f"ERROR FEDEX_LABEL_RAW: An unexpected exception occurred: {e}")
        traceback.print_exc()
        return None, None

def generate_fedex_label(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name):
    print(f"DEBUG FEDEX_GEN_LABEL: Initiating FedEx label for order {order_data.get('bigcommerce_order_id', 'N/A')}, Wt {total_weight_lbs}, Method '{customer_shipping_method_name}'")
    access_token = get_fedex_oauth_token()
    if not access_token:
        print("ERROR FEDEX_GEN_LABEL: Failed to get FedEx OAuth token."); return None, None
    label_pdf_bytes, tracking_number = generate_fedex_label_raw(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token)
    if label_pdf_bytes and tracking_number: print(f"INFO FEDEX_GEN_LABEL: FedEx PDF label generated. Tracking: {tracking_number}."); return label_pdf_bytes, tracking_number
    elif tracking_number: print(f"WARN FEDEX_GEN_LABEL: Got FedEx tracking {tracking_number}, but no label PDF."); return None, tracking_number
    else: print(f"ERROR FEDEX_GEN_LABEL: Failed to generate FedEx label/tracking."); return None, None

def convert_image_bytes_to_pdf_bytes(image_bytes, image_format="GIF"):
    if not PILLOW_AVAILABLE: print("ERROR IMG_TO_PDF: Pillow/ReportLab not available."); return None
    if not image_bytes: print("ERROR IMG_TO_PDF: No image bytes provided."); return None
    try:
        img_stream = io.BytesIO(image_bytes)
        img = PILImage.open(img_stream)
        if hasattr(img, 'seek'): img.seek(0)
        img = img.convert("RGBA")
        img_width_px, img_height_px = img.size
        if img_width_px == 0 or img_height_px == 0: print("ERROR IMG_TO_PDF: Image dimensions are zero."); return None
        page_width_pt, page_height_pt = letter; margin_pt = 1 * inch
        drawable_area_width_pt = page_width_pt - (2 * margin_pt)
        img_aspect_ratio = img_width_px / img_height_px
        draw_width_pt = drawable_area_width_pt; draw_height_pt = draw_width_pt / img_aspect_ratio
        if draw_height_pt > (page_height_pt - 2 * margin_pt):
            draw_height_pt = page_height_pt - (2 * margin_pt)
            draw_width_pt = draw_height_pt * img_aspect_ratio
        x_offset_pt = margin_pt + (drawable_area_width_pt - draw_width_pt) / 2
        y_offset_pt = page_height_pt - margin_pt - draw_height_pt
        y_offset_pt = max(y_offset_pt, margin_pt)
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        png_stream = io.BytesIO()
        img.save(png_stream, format="PNG")
        png_stream.seek(0)
        reportlab_image = ImageReader(png_stream)
        c.drawImage(reportlab_image, x_offset_pt, y_offset_pt, width=draw_width_pt, height=draw_height_pt, mask='auto', preserveAspectRatio=True)
        c.showPage(); c.save()
        pdf_bytes_out = pdf_buffer.getvalue()
        pdf_buffer.close(); png_stream.close(); img_stream.close()
        print("DEBUG IMG_TO_PDF: Image converted to PDF bytes (top-aligned)."); return pdf_bytes_out
    except Exception as e: print(f"ERROR IMG_TO_PDF: Conversion failed: {e}"); traceback.print_exc(); return None

def generate_ups_label(order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name,
                       is_bill_to_customer_ups_account=False, customer_ups_account_number=None, customer_ups_account_zipcode=None):
    access_token = get_ups_oauth_token()
    if not access_token: print("ERROR UPS_GEN_LABEL: Failed to get UPS OAuth token."); return None, None
    raw_label_image_bytes, tracking_number = generate_ups_label_raw(
        order_data, ship_from_address, total_weight_lbs, customer_shipping_method_name, access_token,
        is_bill_to_customer_ups_account, customer_ups_account_number, customer_ups_account_zipcode
    )
    if not tracking_number and not raw_label_image_bytes: print("ERROR UPS_GEN_LABEL: Raw gen failed."); return None, None
    if not raw_label_image_bytes and tracking_number: print(f"WARN UPS_GEN_LABEL: Tracking {tracking_number}, but no raw label image."); return None, tracking_number
    final_label_pdf_bytes = convert_image_bytes_to_pdf_bytes(raw_label_image_bytes, image_format="GIF")
    if not final_label_pdf_bytes: print(f"ERROR UPS_GEN_LABEL: PDF conversion failed for track {tracking_number}."); return None, tracking_number
    return final_label_pdf_bytes, tracking_number

def create_bigcommerce_shipment(bigcommerce_order_id, tracking_number, shipping_method_name, line_items_in_shipment, order_address_id, comments=None, shipping_provider=None):
    print(f"DEBUG BC_CREATE_SHIPMENT: Order {bigcommerce_order_id}, Track {tracking_number}, Provider: {shipping_provider}")
    if not CURRENT_BC_API_BASE_URL_V2 or not CURRENT_BC_HEADERS or not CURRENT_BC_HEADERS.get("X-Auth-Token"): print("ERROR BC_CREATE_SHIPMENT: BC API not configured."); return False
    if not all([bigcommerce_order_id, tracking_number, line_items_in_shipment]) or order_address_id is None: print(f"ERROR BC_CREATE_SHIPMENT: Missing args."); return False
    shipments_url = f"{CURRENT_BC_API_BASE_URL_V2}orders/{bigcommerce_order_id}/shipments"
    tracking_carrier_for_bc = ""
    if shipping_provider:
        sp_lower = str(shipping_provider).lower()
        if "ups" in sp_lower: tracking_carrier_for_bc = "ups"
        elif "fedex" in sp_lower: tracking_carrier_for_bc = "fedex"
        elif "usps" in sp_lower: tracking_carrier_for_bc = "usps"
    if not tracking_carrier_for_bc and shipping_method_name:
        sm_lower = (shipping_method_name or "").lower()
        if "ups" in sm_lower: tracking_carrier_for_bc = "ups"
        elif "fedex" in sm_lower: tracking_carrier_for_bc = "fedex"
        elif "usps" in sm_lower: tracking_carrier_for_bc = "usps"
    shipment_payload = {"order_address_id": int(order_address_id), "tracking_number": str(tracking_number), "items": line_items_in_shipment}
    if shipping_method_name: shipment_payload["shipping_method"] = str(shipping_method_name)
    if tracking_carrier_for_bc: shipment_payload["tracking_carrier"] = tracking_carrier_for_bc
    if comments: shipment_payload["comments"] = str(comments)
    if shipping_provider: shipment_payload["shipping_provider"] = str(shipping_provider)
    print(f"DEBUG BC_CREATE_SHIPMENT: Payload to BC: {json.dumps(shipment_payload)}")
    try:
        response = requests.post(shipments_url, headers=CURRENT_BC_HEADERS, json=shipment_payload)
        response.raise_for_status(); shipment_creation_data = response.json()
        print(f"INFO BC_CREATE_SHIPMENT: Success for BC Order {bigcommerce_order_id}. BC Ship ID: {shipment_creation_data.get('id')}"); return True
    except requests.exceptions.HTTPError as http_err: print(f"ERROR BC_CREATE_SHIPMENT: HTTPError for {bigcommerce_order_id}: {http_err}. Resp: {http_err.response.text if http_err.response else 'N/A'}"); return False
    except Exception as e: print(f"ERROR BC_CREATE_SHIPMENT: Unexpected error for {bigcommerce_order_id}: {e}"); traceback.print_exc(); return False

def set_bigcommerce_order_status(bigcommerce_order_id, status_id):
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
    fedex_token = get_fedex_oauth_token()

    # Placeholder for international shipment test
    print("\n--- Placeholder for International Shipment Test ---")
    print("To test, create a mock payload similar to the one from InternationalOrderProcessor.jsx")
    print("and call generate_ups_international_shipment(mock_payload)")
    
    if fedex_token:
        print(f"\n--- FedEx Test ({FEDEX_API_ENVIRONMENT.upper()} Environment) ---")
        mock_order_data_fedex_test = {
            'bigcommerce_order_id': f'TEST_FX_LABEL_{int(datetime.now(timezone.utc).timestamp())}',
            'customer_company': 'FedEx Test Recipient Co.', 'customer_name': 'John Doe FedEx',
            'customer_phone': '8005551212', 'customer_shipping_address_line1': '123 Main Street',
            'customer_shipping_address_line2': 'Suite 100', 'customer_shipping_city': 'Beverly Hills',
            'customer_shipping_state': 'CA', 'customer_shipping_zip': '90210',
            'customer_shipping_country_iso2': 'US', 'customer_email': 'johndoe.fedex@example.com',
            'is_bill_to_customer_fedex_account': True, 'customer_fedex_account_number': 'YOUR_TEST_RECIPIENT_FEDEX_ACCOUNT'
        }
        mock_ship_from_details = {
            'name': os.getenv("SHIP_FROM_NAME"), 'contact_person': os.getenv("SHIP_FROM_CONTACT"),
            'street_1': os.getenv("SHIP_FROM_STREET1"), 'street_2': os.getenv("SHIP_FROM_STREET2", ""),
            'city': os.getenv("SHIP_FROM_CITY"), 'state': os.getenv("SHIP_FROM_STATE"),
            'zip': os.getenv("SHIP_FROM_ZIP"), 'country': os.getenv("SHIP_FROM_COUNTRY", "US"),
            'phone': os.getenv("SHIP_FROM_PHONE")
        }
        if any(not mock_ship_from_details.get(key) for key in ['name', 'street_1', 'city', 'state', 'zip', 'country', 'phone']):
            print("ERROR: FedEx Test ABORTED. Essential SHIP_FROM details missing in .env.")
        else:
            service_to_test = "FEDEX_GROUND"; weight_to_test = 3
            print(f"\nAttempting FedEx Label ({('Bill Recipient Acct: ' + mock_order_data_fedex_test['customer_fedex_account_number']) if mock_order_data_fedex_test['is_bill_to_customer_fedex_account'] else 'Bill SENDER'}) - Service: {service_to_test} in {FEDEX_API_ENVIRONMENT.upper()}")
            pdf_bytes_fx, tracking_fx = generate_fedex_label(mock_order_data_fedex_test, mock_ship_from_details, weight_to_test, service_to_test)
            if pdf_bytes_fx and tracking_fx:
                print(f"FedEx Test: SUCCESS! Tracking: {tracking_fx}")
                filename = f"{FEDEX_API_ENVIRONMENT}_fx_label_{service_to_test}_{tracking_fx}.pdf"
                try:
                    with open(filename, "wb") as f: f.write(pdf_bytes_fx)
                    print(f"  Label saved as {filename}")
                except Exception as e: print(f"  Error writing label file: {e}")
            elif tracking_fx: print(f"FedEx Test: PARTIAL SUCCESS. Tracking: {tracking_fx}, but no PDF label data.")
            else: print(f"FedEx Test: FAILED.")
    else: print("Failed to get FedEx OAuth Token, cannot proceed with FedEx test.")
    print("\n--- shipping_service.py standalone test finished ---")