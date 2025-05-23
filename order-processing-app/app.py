# order-processing-app/app.py

import os
import time
import traceback
from functools import wraps
from flask import Flask, jsonify, request, g, current_app
from flask_cors import CORS
import sqlalchemy
from sqlalchemy import text # Keep this for /test_db and potentially direct use in helpers
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector as GcpSqlConnector
import requests
from datetime import datetime, timezone, timedelta
from sqlalchemy.dialects.postgresql import insert # Keep for helpers or if used directly
from decimal import Decimal
import inspect
import re
import base64
import sys
import html

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
# These are fine here as they are not part of the app context itself but standalone modules
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

app = Flask(__name__)
print("DEBUG APP_SETUP: Flask object created.")

# --- Replace the existing CORS block with this ---
# This new block reads the allowed origin from an environment variable,
# making it work for both local development and your deployed app.
allowed_origin = os.environ.get('ALLOWED_CORS_ORIGIN')

if allowed_origin:
    print(f"DEBUG APP_SETUP: CORS configured for origin: {allowed_origin}")
    CORS(app,
         resources={r"/api/*": {"origins": [allowed_origin]}}, # It's best practice for origins to be a list
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         allow_headers=["Content-Type", "Authorization"],
         supports_credentials=True
    )
else:
    print("WARN APP_SETUP: ALLOWED_CORS_ORIGIN environment variable not set. CORS will not be configured.")
# -----------------------------------------------

app.debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

# --- Firebase Admin SDK Initialization ---
try:
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    firebase_project_id = "g1-po-app-77790"

    if cred_path:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            'projectId': firebase_project_id,
        })
        print(f"DEBUG APP_SETUP: Firebase Admin SDK initialized using service account key from: {cred_path} for project {firebase_project_id}")
    else:
        # Fallback for environments where GOOGLE_APPLICATION_CREDENTIALS might not be set
        # (e.g., Cloud Run with default service account identity)
        firebase_admin.initialize_app(options={
            'projectId': firebase_project_id, # Explicitly set project ID
        })
        print(f"DEBUG APP_SETUP: Firebase Admin SDK initialized using default environment credentials, explicitly targeting project {firebase_project_id}.")

except Exception as e_firebase_admin:
    print(f"ERROR APP_SETUP: Firebase Admin SDK initialization failed: {e_firebase_admin}")
    traceback.print_exc()
# --- End Firebase Admin SDK Init ---

# --- Configuration (remains the same) ---
db_connection_name = os.getenv("DB_CONNECTION_NAME")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
db_driver = os.getenv("DB_DRIVER", "pg8000")

bc_store_hash = os.getenv("BIGCOMMERCE_STORE_HASH")
bc_client_id = os.getenv("BIGCOMMERCE_CLIENT_ID") # Keep if used directly anywhere else
bc_access_token = os.getenv("BIGCOMMERCE_ACCESS_TOKEN")
domestic_country_code = os.getenv("DOMESTIC_COUNTRY_CODE", "US")
bc_processing_status_id = os.getenv("BC_PROCESSING_STATUS_ID")
bc_shipped_status_id = os.getenv("BC_SHIPPED_STATUS_ID")

G1_ONSITE_FULFILLMENT_IDENTIFIER = "_G1_ONSITE_FULFILLMENT_"

SHIP_FROM_NAME = os.getenv("SHIP_FROM_NAME", "Your Company Name")
SHIP_FROM_CONTACT = os.getenv("SHIP_FROM_CONTACT", "Shipping Dept")
SHIP_FROM_STREET1 = os.getenv("SHIP_FROM_STREET1")
SHIP_FROM_STREET2 = os.getenv("SHIP_FROM_STREET2", "")
SHIP_FROM_CITY = os.getenv("SHIP_FROM_CITY")
SHIP_FROM_STATE = os.getenv("SHIP_FROM_STATE")
SHIP_FROM_ZIP = os.getenv("SHIP_FROM_ZIP")
SHIP_FROM_COUNTRY = os.getenv("SHIP_FROM_COUNTRY", "US")
SHIP_FROM_PHONE = os.getenv("SHIP_FROM_PHONE")

# FedEx API Credentials (remain the same)
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

# --- Database Engine (remains the same) ---
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

# --- GCS Client (remains the same) ---
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

# --- Helper Functions (to be used by blueprints, kept here or moved to a shared utils.py later) ---
def convert_row_to_dict(row):
    if not row: return None
    row_dict = row._asdict() if hasattr(row, '_asdict') else dict(getattr(row, '_mapping', {}))
    row_dict = {str(k): v for k, v in row_dict.items()}
    for key, value in row_dict.items():
        if isinstance(value, Decimal): row_dict[key] = value
        elif isinstance(value, datetime):
            if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
            row_dict[key] = value
    return row_dict

def make_json_safe(data):
    if isinstance(data, dict): return {key: make_json_safe(value) for key, value in data.items()}
    elif isinstance(data, list): return [make_json_safe(item) for item in data]
    elif isinstance(data, Decimal): return str(data)
    elif isinstance(data, datetime):
        if data.tzinfo is None: data = data.replace(tzinfo=timezone.utc)
        return data.isoformat()
    else: return data

def _get_bc_shipping_address_id(bc_order_id): # Needs bc_api_base_url_v2, bc_headers
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

def get_hpe_mapping_with_fallback(original_sku_from_order, db_conn): # Needs engine for db_conn
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

# --- Firebase Token Verification Decorator (kept here or moved to auth.py later) ---
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

# === BASIC ROUTES (Kept in main app.py) ===
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

# === ALL OTHER /api/* ROUTES ARE MOVED TO BLUEPRINTS ===

# --- Import and Register Blueprints ---
# Make sure these imports are correctly placed, usually after app initialization
# and before the app.run() or the end of the file for WSGI.

from blueprints.orders import orders_bp
from blueprints.suppliers import suppliers_bp
from blueprints.hpe_mappings import hpe_mappings_bp
from blueprints.quickbooks import quickbooks_bp
from blueprints.reports import reports_bp
from blueprints.utils_routes import utils_bp # Matches the filename utils_routes.py

# Register blueprints with their respective URL prefixes
app.register_blueprint(orders_bp, url_prefix='/api')
app.register_blueprint(suppliers_bp, url_prefix='/api')
app.register_blueprint(hpe_mappings_bp, url_prefix='/api') # Covers /api/hpe-descriptions/* and /api/lookup/*
app.register_blueprint(quickbooks_bp, url_prefix='/api')   # Covers /api/tasks/* and /api/quickbooks/*
app.register_blueprint(reports_bp, url_prefix='/api')    # Covers /api/reports/*
app.register_blueprint(utils_bp, url_prefix='/api/utils')  # Covers /api/utils/*

print("DEBUG APP_SETUP: All Blueprints registered.")

# === Entry point for running the Flask app (remains the same) ===
if __name__ == '__main__':
    print(f"Starting G1 PO App Backend...")
    app.run(host='0.0.0.0', port=8080, debug=True)
    if engine is None:
        print("CRITICAL MAIN: Database engine not initialized. Flask app might not work correctly with DB operations.")
    # else: # Blueprints are already registered above globally for both __main__ and WSGI
        # The registration should happen once, globally.

    run_host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    run_port = int(os.getenv("FLASK_RUN_PORT", 8080))
    print(f"--> Running Flask development server on http://{run_host}:{run_port} with debug={app.debug}")
    app.run(host=run_host, port=run_port, debug=app.debug)
else:
    # This block is for when Gunicorn (or another WSGI server) runs the app
    print("DEBUG APP_SETUP: Script imported by WSGI server (like Gunicorn).")
    if engine is None:
        print("CRITICAL GUNICORN: Database engine not initialized during import. DB operations will fail.")
    # else: # Blueprints are already registered above globally
        # print("DEBUG GUNICORN: Database engine appears initialized during import.")
    # The blueprints should be registered globally before this block is reached by Gunicorn.

print("DEBUG APP_SETUP: Reached end of app.py top-level execution.")