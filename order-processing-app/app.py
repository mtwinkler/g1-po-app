# order-processing-app/app.py

import os
import time
import traceback
from functools import wraps
from flask import Flask, jsonify, request, g, current_app
from flask_cors import CORS
import sqlalchemy
from sqlalchemy import text 
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector as GcpSqlConnector
import requests
from datetime import datetime, timezone, timedelta
from sqlalchemy.dialects.postgresql import insert 
from decimal import Decimal
import inspect
import re
import base64
import sys
import html
import json # Ensure json is imported for any direct use

# --- Firebase Admin SDK Imports ---
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth

# --- GCS Import ---
try:
    from google.cloud import storage
except ImportError:
    print("WARN APP_SETUP: google-cloud-storage library not found. Please install it (`pip install google-cloud-storage`).")
    storage = None

# --- Import your custom service modules (blueprints will import these as needed) ---
try:
    import document_generator
except ImportError as e:
    print(f"WARN: Could not import document_generator: {e}")
    document_generator = None

try:
    import shipping_service
except ImportError as e:
    print(f"WARN: Could not import shipping_service: {e}")
    shipping_service = None

try:
    import email_service
except ImportError as e:
    print(f"WARN: Could not import email_service: {e}")
    email_service = None

try:
    import iif_generator
except ImportError as e:
    print(f"WARN APP_SETUP: Could not import iif_generator: {e}. Daily IIF task will fail.")
    iif_generator = None

print("DEBUG APP_SETUP: Imports done.")

try:
    load_dotenv()
    print("DEBUG APP_SETUP: load_dotenv finished.")
except Exception as e_dotenv:
    print(f"ERROR APP_SETUP: load_dotenv failed: {e_dotenv}")

COUNTRY_ISO_TO_NAME = {
    'AF': 'Afghanistan', 'AL': 'Albania', 'DZ': 'Algeria', 'AS': 'American Samoa',
    'AD': 'Andorra', 'AO': 'Angola', 'AI': 'Anguilla', 'AQ': 'Antarctica',
    'AG': 'Antigua and Barbuda', 'AR': 'Argentina', 'AM': 'Armenia', 'AW': 'Aruba',
    'AU': 'Australia', 'AT': 'Austria', 'AZ': 'Azerbaijan', 'BS': 'Bahamas',
    'BH': 'Bahrain', 'BD': 'Bangladesh', 'BB': 'Barbados', 'BY': 'Belarus',
    'BE': 'Belgium', 'BZ': 'Belize', 'BJ': 'Benin', 'BM': 'Bermuda', 'BT': 'Bhutan',
    'BO': 'Bolivia', 'BA': 'Bosnia and Herzegovina', 'BW': 'Botswana',
    'BR': 'Brazil', 'IO': 'British Indian Ocean Territory',
    'VG': 'British Virgin Islands', 'BN': 'Brunei', 'BG': 'Bulgaria',
    'BF': 'Burkina Faso', 'BI': 'Burundi', 'KH': 'Cambodia', 'CM': 'Cameroon',
    'CA': 'Canada', 'CV': 'Cape Verde', 'KY': 'Cayman Islands',
    'CF': 'Central African Republic', 'TD': 'Chad', 'CL': 'Chile', 'CN': 'China',
    'CX': 'Christmas Island', 'CC': 'Cocos (Keeling) Islands', 'CO': 'Colombia',
    'KM': 'Comoros', 'CG': 'Congo - Brazzaville',
    'CD': 'Congo - Kinshasa (DRC)', 'CK': 'Cook Islands', 'CR': 'Costa Rica',
    'CI': 'Côte d’Ivoire', 'HR': 'Croatia', 'CU': 'Cuba', 'CY': 'Cyprus',
    'CZ': 'Czechia', 'DK': 'Denmark', 'DJ': 'Djibouti', 'DM': 'Dominica',
    'DO': 'Dominican Republic', 'EC': 'Ecuador', 'EG': 'Egypt',
    'SV': 'El Salvador', 'GQ': 'Equatorial Guinea', 'ER': 'Eritrea',
    'EE': 'Estonia', 'SZ': 'Eswatini', 'ET': 'Ethiopia',
    'FK': 'Falkland Islands (Islas Malvinas)', 'FO': 'Faroe Islands', 'FJ': 'Fiji',
    'FI': 'Finland', 'FR': 'France', 'GF': 'French Guiana',
    'PF': 'French Polynesia', 'TF': 'French Southern Territories', 'GA': 'Gabon',
    'GM': 'Gambia', 'GE': 'Georgia', 'DE': 'Germany', 'GH': 'Ghana',
    'GI': 'Gibraltar', 'GR': 'Greece', 'GL': 'Greenland', 'GD': 'Grenada',
    'GP': 'Guadeloupe', 'GU': 'Guam', 'GT': 'Guatemala', 'GG': 'Guernsey',
    'GN': 'Guinea', 'GW': 'Guinea-Bissau', 'GY': 'Guyana', 'HT': 'Haiti',
    'HN': 'Honduras', 'HK': 'Hong Kong SAR China', 'HU': 'Hungary',
    'IS': 'Iceland', 'IN': 'India', 'ID': 'Indonesia', 'IR': 'Iran',
    'IQ': 'Iraq', 'IE': 'Ireland', 'IM': 'Isle of Man', 'IL': 'Israel',
    'IT': 'Italy', 'JM': 'Jamaica', 'JP': 'Japan', 'JE': 'Jersey',
    'JO': 'Jordan', 'KZ': 'Kazakhstan', 'KE': 'Kenya', 'KI': 'Kiribati',
    'KW': 'Kuwait', 'KG': 'Kyrgyzstan', 'LA': 'Laos', 'LV': 'Latvia',
    'LB': 'Lebanon', 'LS': 'Lesotho', 'LR': 'Liberia', 'LY': 'Libya',
    'LI': 'Liechtenstein', 'LT': 'Lithuania', 'LU': 'Luxembourg',
    'MO': 'Macao SAR China', 'MG': 'Madagascar', 'MW': 'Malawi',
    'MY': 'Malaysia', 'MV': 'Maldives', 'ML': 'Mali', 'MT': 'Malta',
    'MH': 'Marshall Islands', 'MQ': 'Martinique', 'MR': 'Mauritania',
    'MU': 'Mauritius', 'YT': 'Mayotte', 'MX': 'Mexico', 'FM': 'Micronesia',
    'MD': 'Moldova', 'MC': 'Monaco', 'MN': 'Mongolia', 'ME': 'Montenegro',
    'MS': 'Montserrat', 'MA': 'Morocco', 'MZ': 'Mozambique', 'MM': 'Myanmar (Burma)',
    'NA': 'Namibia', 'NR': 'Nauru', 'NP': 'Nepal', 'NL': 'Netherlands',
    'NC': 'New Caledonia', 'NZ': 'New Zealand', 'NI': 'Nicaragua',
    'NE': 'Niger', 'NG': 'Nigeria', 'NU': 'Niue', 'NF': 'Norfolk Island',
    'KP': 'North Korea', 'MK': 'North Macedonia', 'MP': 'Northern Mariana Islands',
    'NO': 'Norway', 'OM': 'Oman', 'PK': 'Pakistan', 'PW': 'Palau',
    'PS': 'Palestinian Territories', 'PA': 'Panama', 'PG': 'Papua New Guinea',
    'PY': 'Paraguay', 'PE': 'Peru', 'PH': 'Philippines', 'PN': 'Pitcairn Islands',
    'PL': 'Poland', 'PT': 'Portugal', 'PR': 'Puerto Rico', 'QA': 'Qatar',
    'RE': 'Réunion', 'RO': 'Romania', 'RU': 'Russia', 'RW': 'Rwanda',
    'WS': 'Samoa', 'SM': 'San Marino', 'ST': 'São Tomé & Príncipe',
    'SA': 'Saudi Arabia', 'SN': 'Senegal', 'RS': 'Serbia', 'SC': 'Seychelles',
    'SL': 'Sierra Leone', 'SG': 'Singapore', 'SX': 'Sint Maarten',
    'SK': 'Slovakia', 'SI': 'Slovenia', 'SB': 'Solomon Islands', 'SO': 'Somalia',
    'ZA': 'South Africa', 'GS': 'South Georgia & South Sandwich Islands',
    'KR': 'South Korea', 'SS': 'South Sudan', 'ES': 'Spain', 'LK': 'Sri Lanka',
    'BL': 'St. Barthélemy', 'SH': 'St. Helena', 'KN': 'St. Kitts & Nevis',
    'LC': 'St. Lucia', 'MF': 'St. Martin', 'PM': 'St. Pierre & Miquelon',
    'VC': 'St. Vincent & Grenadines', 'SD': 'Sudan', 'SR': 'Suriname',
    'SJ': 'Svalbard & Jan Mayen', 'SE': 'Sweden', 'CH': 'Switzerland',
    'SY': 'Syria', 'TW': 'Taiwan', 'TJ': 'Tajikistan', 'TZ': 'Tanzania',
    'TH': 'Thailand', 'TL': 'Timor-Leste', 'TG': 'Togo', 'TK': 'Tokelau',
    'TO': 'Tonga', 'TT': 'Trinidad & Tobago', 'TN': 'Tunisia', 'TR': 'Turkey',
    'TM': 'Turkmenistan', 'TC': 'Turks & Caicos Islands', 'TV': 'Tuvalu',
    'UM': 'U.S. Outlying Islands', 'VI': 'U.S. Virgin Islands', 'UG': 'Uganda',
    'UA': 'Ukraine', 'AE': 'United Arab Emirates', 'GB': 'United Kingdom',
    'US': 'United States', 'UY': 'Uruguay', 'UZ': 'Uzbekistan', 'VU': 'Vanuatu',
    'VA': 'Vatican City', 'VE': 'Venezuela', 'VN': 'Vietnam',
    'WF': 'Wallis & Futuna', 'EH': 'Western Sahara', 'YE': 'Yemen',
    'ZM': 'Zambia', 'ZW': 'Zimbabwe',
}

app = Flask(__name__)
print("DEBUG APP_SETUP: Flask object created.")

allowed_origin = os.environ.get('ALLOWED_CORS_ORIGIN')
if allowed_origin:
    print(f"DEBUG APP_SETUP: CORS configured for origin: {allowed_origin}")
    CORS(app,
         resources={r"/api/*": {"origins": [allowed_origin]}}, 
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         allow_headers=["Content-Type", "Authorization"],
         supports_credentials=True
    )
else:
    print("WARN APP_SETUP: ALLOWED_CORS_ORIGIN environment variable not set. CORS will not be configured.")

app.debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

try:
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    firebase_project_id = "g1-po-app-77790" 
    if cred_path:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {'projectId': firebase_project_id})
        print(f"DEBUG APP_SETUP: Firebase Admin SDK initialized using service account key from: {cred_path} for project {firebase_project_id}")
    else:
        firebase_admin.initialize_app(options={'projectId': firebase_project_id})
        print(f"DEBUG APP_SETUP: Firebase Admin SDK initialized using default environment credentials, explicitly targeting project {firebase_project_id}.")
except Exception as e_firebase_admin:
    print(f"ERROR APP_SETUP: Firebase Admin SDK initialization failed: {e_firebase_admin}")
    traceback.print_exc()

# --- Configuration ---
db_connection_name = os.getenv("DB_CONNECTION_NAME")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
db_driver = os.getenv("DB_DRIVER", "pg8000")

bc_store_hash = os.getenv("BIGCOMMERCE_STORE_HASH")
bc_client_id = os.getenv("BIGCOMMERCE_CLIENT_ID") 
bc_access_token = os.getenv("BIGCOMMERCE_ACCESS_TOKEN")
domestic_country_code = os.getenv("DOMESTIC_COUNTRY_CODE", "US")
bc_processing_status_id = os.getenv("BC_PROCESSING_STATUS_ID")
bc_shipped_status_id = os.getenv("BC_SHIPPED_STATUS_ID")

G1_ONSITE_FULFILLMENT_IDENTIFIER = "_G1_ONSITE_FULFILLMENT_"
SHIPPER_EIN = os.getenv("SHIPPER_EIN", "421713620") # <-- ADDED THIS LINE
print(f"DEBUG APP_SETUP: SHIPPER_EIN set to: {SHIPPER_EIN}")


SHIP_FROM_NAME = os.getenv("SHIP_FROM_NAME", "Your Company Name")
SHIP_FROM_CONTACT = os.getenv("SHIP_FROM_CONTACT", "Shipping Dept")
SHIP_FROM_STREET1 = os.getenv("SHIP_FROM_STREET1")
SHIP_FROM_STREET2 = os.getenv("SHIP_FROM_STREET2", "")
SHIP_FROM_CITY = os.getenv("SHIP_FROM_CITY")
SHIP_FROM_STATE = os.getenv("SHIP_FROM_STATE")
SHIP_FROM_ZIP = os.getenv("SHIP_FROM_ZIP")
SHIP_FROM_COUNTRY = os.getenv("SHIP_FROM_COUNTRY", "US")
SHIP_FROM_PHONE = os.getenv("SHIP_FROM_PHONE")

FEDEX_CLIENT_ID_SANDBOX = os.getenv("FEDEX_CLIENT_ID_SANDBOX")
FEDEX_CLIENT_SECRET_SANDBOX = os.getenv("FEDEX_CLIENT_SECRET_SANDBOX")
FEDEX_ACCOUNT_NUMBER_SANDBOX = os.getenv("FEDEX_ACCOUNT_NUMBER_SANDBOX")
FEDEX_API_BASE_URL_SANDBOX = os.getenv("FEDEX_API_BASE_URL_SANDBOX", "https://apis-sandbox.fedex.com")
FEDEX_CLIENT_ID_PRODUCTION = os.getenv("FEDEX_CLIENT_ID_PRODUCTION")
FEDEX_CLIENT_SECRET_PRODUCTION = os.getenv("FEDEX_CLIENT_SECRET_PRODUCTION")
FEDEX_ACCOUNT_NUMBER_PRODUCTION = os.getenv("FEDEX_ACCOUNT_NUMBER_PRODUCTION")
FEDEX_API_BASE_URL_PRODUCTION = os.getenv("FEDEX_API_BASE_URL_PRODUCTION", "https://apis.fedex.com")
IS_PRODUCTION_ENV = os.getenv('FLASK_ENV') == 'production'
ACTIVE_FEDEX_CLIENT_ID = FEDEX_CLIENT_ID_PRODUCTION if IS_PRODUCTION_ENV else FEDEX_CLIENT_ID_SANDBOX
ACTIVE_FEDEX_CLIENT_SECRET = FEDEX_CLIENT_SECRET_PRODUCTION if IS_PRODUCTION_ENV else FEDEX_CLIENT_SECRET_SANDBOX
ACTIVE_FEDEX_ACCOUNT_NUMBER = FEDEX_ACCOUNT_NUMBER_PRODUCTION if IS_PRODUCTION_ENV else FEDEX_ACCOUNT_NUMBER_SANDBOX
ACTIVE_FEDEX_API_BASE_URL = FEDEX_API_BASE_URL_PRODUCTION if IS_PRODUCTION_ENV else FEDEX_API_BASE_URL_SANDBOX

if not all([ACTIVE_FEDEX_CLIENT_ID, ACTIVE_FEDEX_CLIENT_SECRET, ACTIVE_FEDEX_ACCOUNT_NUMBER, ACTIVE_FEDEX_API_BASE_URL]):
    print("WARN APP_SETUP: FedEx API credentials not fully configured for the active environment.")
else:
    print(f"DEBUG APP_SETUP: FedEx API configured for {'Production' if IS_PRODUCTION_ENV else 'Sandbox'} environment.")

GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
COMPANY_LOGO_GCS_URI = os.getenv("COMPANY_LOGO_GCS_URI")
if COMPANY_LOGO_GCS_URI:
    print(f"DEBUG APP_SETUP: Company logo URI configured: {COMPANY_LOGO_GCS_URI}")
else:
    print("WARN APP_SETUP: COMPANY_LOGO_GCS_URI environment variable not set. PDFs will not have a logo.")

bc_api_base_url_v2 = None
bc_headers = None
if bc_store_hash and bc_access_token:
    bc_api_base_url_v2 = f"https://api.bigcommerce.com/stores/{bc_store_hash}/v2/"
    bc_headers = {
        "X-Auth-Token": bc_access_token,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
else:
    print("WARN APP_SETUP: BigCommerce API credentials not fully configured.")

engine = None
gcp_connector_instance = None
try:
    print("DEBUG APP_SETUP: Attempting DB engine init...")
    if not all([db_connection_name, db_user, db_password, db_name]):
        print("ERROR APP_SETUP: Missing one or more database connection environment variables.")
    else:
        print(f"DEBUG APP_SETUP: Initializing DB connection for {db_connection_name} using {db_driver}")
        gcp_connector_instance = GcpSqlConnector()
        def getconn():
            conn_gcp = gcp_connector_instance.connect(
                db_connection_name,
                db_driver,
                user=db_user,
                password=db_password,
                db=db_name
            )
            return conn_gcp
        engine = sqlalchemy.create_engine(
            f"postgresql+{db_driver}://",
            creator=getconn,
            pool_size=5, max_overflow=2, pool_timeout=30, pool_recycle=1800,
            echo=(app.debug)
        )
        print("DEBUG APP_SETUP: Database engine initialized successfully.")
except ImportError:
    print("ERROR APP_SETUP: google-cloud-sql-connector library not found. Please install it (`pip install google-cloud-sql-connector[pg8000]`).")
except Exception as e_engine:
    print(f"CRITICAL APP_SETUP: Database engine initialization failed: {e_engine}")
    traceback.print_exc()
    engine = None
print("DEBUG APP_SETUP: Finished DB engine init block.")

storage_client = None
if storage:
    try:
        print("DEBUG APP_SETUP: Attempting GCS client init...")
        storage_client = storage.Client()
        print("DEBUG APP_SETUP: Google Cloud Storage client initialized successfully.")
    except Exception as gcs_e:
        print(f"ERROR APP_SETUP: Failed to initialize Google Cloud Storage client: {gcs_e}")
        traceback.print_exc()
        storage_client = None
else:
    print("WARN APP_SETUP: Google Cloud Storage library not loaded. File uploads will be skipped.")
print("DEBUG APP_SETUP: Finished GCS client init block.")

def convert_row_to_dict(row):
    if not row: return None
    row_dict = row._asdict() if hasattr(row, '_asdict') else dict(getattr(row, '_mapping', {}))
    row_dict = {str(k): v for k, v in row_dict.items()}
    for key, value in row_dict.items():
        if isinstance(value, Decimal): row_dict[key] = value
        elif isinstance(value, datetime):
            if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
            row_dict[key] = value
        # Handle JSONB fields that might be strings and need parsing
        elif key == 'compliance_info' and isinstance(value, str): # Specifically for compliance_info
            try:
                row_dict[key] = json.loads(value) if value else {}
            except json.JSONDecodeError:
                print(f"WARN convert_row_to_dict: Could not parse compliance_info JSON string: {value}")
                row_dict[key] = {} # Default to empty dict on parse error
        elif key == 'compliance_info' and value is None: # Ensure None becomes empty dict for frontend
             row_dict[key] = {}


    return row_dict

def make_json_safe(data):
    if isinstance(data, dict): return {key: make_json_safe(value) for key, value in data.items()}
    elif isinstance(data, list): return [make_json_safe(item) for item in data]
    elif isinstance(data, Decimal): return str(data)
    elif isinstance(data, datetime):
        if data.tzinfo is None: data = data.replace(tzinfo=timezone.utc)
        return data.isoformat()
    else: return data

def _get_bc_shipping_address_id(bc_order_id): 
    if not bc_api_base_url_v2 or not bc_headers: return None
    try:
        shipping_addr_url = f"{bc_api_base_url_v2}orders/{bc_order_id}/shippingaddresses"
        response = requests.get(shipping_addr_url, headers=bc_headers)
        response.raise_for_status()
        shipping_addresses = response.json()
        if shipping_addresses and isinstance(shipping_addresses, list) and shipping_addresses[0].get('id'):
            return shipping_addresses[0]['id']
        return None
    except requests.exceptions.RequestException as e:
        print(f"ERROR _get_bc_shipping_address_id for order {bc_order_id}: {e}")
        return None

def get_hpe_mapping_with_fallback(original_sku_from_order, db_conn): 
    hpe_option_pn, hpe_pn_type, sku_actually_mapped = None, None, original_sku_from_order
    if not original_sku_from_order: return None, None, original_sku_from_order
    query_map = text("SELECT option_pn, pn_type FROM hpe_part_mappings WHERE sku = :sku")
    result = db_conn.execute(query_map, {"sku": original_sku_from_order}).fetchone()
    if result:
        hpe_option_pn, hpe_pn_type = result.option_pn, result.pn_type
    elif '_' in original_sku_from_order:
        sku_after_underscore = original_sku_from_order.split('_')[-1]
        if sku_after_underscore and sku_after_underscore != original_sku_from_order:
            result_fallback = db_conn.execute(query_map, {"sku": sku_after_underscore}).fetchone()
            if result_fallback:
                hpe_option_pn, hpe_pn_type = result_fallback.option_pn, result_fallback.pn_type
                sku_actually_mapped = sku_after_underscore
    return hpe_option_pn, hpe_pn_type, sku_actually_mapped


def get_country_name_from_iso(iso_code):
    if not iso_code:
        return None
    return COUNTRY_ISO_TO_NAME.get(iso_code.upper())


def verify_firebase_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'OPTIONS':
            response = current_app.make_default_options_response()
            return response
        auth_header = request.headers.get('Authorization')
        id_token = None
        if auth_header and auth_header.startswith('Bearer '):
            id_token = auth_header.split('Bearer ')[1]
        if not id_token:
            print("AUTH DECORATOR: No ID token found in Authorization header.")
            return jsonify({"error": "Unauthorized", "message": "Authorization token is missing."}), 401
        try:
            decoded_token = firebase_auth.verify_id_token(id_token, check_revoked=True)
            g.user_uid = decoded_token.get('uid')
            g.user_email = decoded_token.get('email')
            g.decoded_token = decoded_token
            if not decoded_token.get('isApproved') == True:
                print(f"WARN AUTH: User {g.user_email} (UID: {g.user_uid}) is not approved. 'isApproved' claim: {decoded_token.get('isApproved')}")
                return jsonify({"error": "Forbidden", "message": "User not approved for this application."}), 403
            print(f"DEBUG AUTH: User {g.user_email} (UID: {g.user_uid}) approved and token verified.")
        except firebase_auth.RevokedIdTokenError:
            print(f"ERROR AUTH: Firebase ID token has been revoked for user associated with the token.")
            return jsonify({"error": "Unauthorized", "message": "Token revoked. Please log in again."}), 401
        except firebase_auth.UserDisabledError:
            user_identifier = g.user_uid if hasattr(g, 'user_uid') and g.user_uid else (decoded_token.get('uid') if 'decoded_token' in locals() and decoded_token else 'Unknown')
            print(f"ERROR AUTH: Firebase user account (UID: {user_identifier}) associated with the token is disabled.")
            return jsonify({"error": "Unauthorized", "message": "User account disabled."}), 401
        except firebase_auth.InvalidIdTokenError as e:
            print(f"ERROR AUTH: Firebase ID token is invalid: {e}")
            return jsonify({"error": "Unauthorized", "message": f"Token invalid: {e}"}), 401
        except firebase_admin.exceptions.FirebaseError as e:
            print(f"ERROR AUTH: Firebase Admin SDK error during token verification: {e}")
            traceback.print_exc()
            return jsonify({"error": "Unauthorized", "message": "Token verification failed due to a Firebase error."}), 401
        except Exception as e:
            print(f"ERROR AUTH: General unexpected exception during token verification: {e}")
            traceback.print_exc()
            return jsonify({"error": "Unauthorized", "message": f"General token verification error: {e}"}), 401
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def hello(): return 'G1 PO App Backend is Running!'
print("DEBUG APP_SETUP: Defined / route.")

@app.route('/test_db')
def test_db_connection():
    if engine is None: return jsonify({"message": "DB engine not initialized"}), 500
    conn = None
    try:
        conn = engine.connect()
        result = conn.execute(sqlalchemy.text("SELECT 1")).scalar_one_or_none() # sqlalchemy.text
        conn.close()
        if result == 1: return jsonify({"message": "DB connection successful!"})
        return jsonify({"message": "Unexpected DB result"}), 500
    except Exception as e:
        print(f"ERROR /test_db: {e}"); traceback.print_exc()
        if conn and not conn.closed: conn.close()
        return jsonify({"message": f"DB query failed: {e}"}), 500
print("DEBUG APP_SETUP: Defined /test_db route.")


from blueprints.orders import orders_bp
from blueprints.suppliers import suppliers_bp
from blueprints.hpe_mappings import hpe_mappings_bp
from blueprints.quickbooks import quickbooks_bp
from blueprints.reports import reports_bp
from blueprints.utils_routes import utils_bp 
from blueprints.international import international_bp
from blueprints.customs_info_crud import customs_info_bp


app.register_blueprint(orders_bp, url_prefix='/api')
app.register_blueprint(suppliers_bp, url_prefix='/api')
app.register_blueprint(hpe_mappings_bp, url_prefix='/api') 
app.register_blueprint(quickbooks_bp, url_prefix='/api')   
app.register_blueprint(reports_bp, url_prefix='/api')    
app.register_blueprint(utils_bp, url_prefix='/api/utils')  
app.register_blueprint(international_bp, url_prefix='/api') 
app.register_blueprint(customs_info_bp, url_prefix='/api')

print("DEBUG APP_SETUP: All Blueprints registered.")


if __name__ == '__main__':
    print(f"Starting G1 PO App Backend...")
    if engine is None:
        print("CRITICAL MAIN: Database engine not initialized. Flask app might not work correctly with DB operations.")
    
    run_host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    run_port = int(os.getenv("FLASK_RUN_PORT", 8080))
    print(f"--> Running Flask development server on http://{run_host}:{run_port} with debug={app.debug}")
    app.run(host=run_host, port=run_port, debug=app.debug)
else:
    print("DEBUG APP_SETUP: Script imported by WSGI server (like Gunicorn).")
    if engine is None:
        print("CRITICAL GUNICORN: Database engine not initialized during import. DB operations will fail.")

print("DEBUG APP_SETUP: Reached end of app.py top-level execution.")