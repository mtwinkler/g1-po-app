# app.py - Cleaned and Updated (Adding Local Status Update - FINAL STEP)

import os
import time # For PO Number generation
import traceback # For detailed error logging in development
from flask import Flask, jsonify, request, g
from flask_cors import CORS # <--- IMPORT CORS
import sqlalchemy
from sqlalchemy import text # For sqlalchemy.text for raw SQL / transaction control
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector as GcpSqlConnector # Alias connector
import requests
from datetime import datetime, timezone # For po_date
from sqlalchemy.dialects.postgresql import insert
from decimal import Decimal # If you need to handle decimal conversion for total_amount explicitly
import inspect # For checking function arguments if needed
import re

# --- Firebase Admin SDK Imports ---
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth # Alias to avoid conflict


# --- GCS Import ---
try:
    from google.cloud import storage
except ImportError:
    print("WARN APP_SETUP: google-cloud-storage library not found. Please install it (`pip install google-cloud-storage`).")
    storage = None
# --- End GCS Import ---

# --- Import your custom service modules ---
# Ensure these files exist and are accessible
try:
    import document_generator
except ImportError as e:
    print(f"WARN: Could not import document_generator: {e}")
    document_generator = None # Set to None to allow app to start, but document generation will fail

try:
    import shipping_service
except ImportError as e:
    print(f"WARN: Could not import shipping_service: {e}")
    shipping_service = None # Set to None, shipping/BC updates will fail

try:
    import email_service # <<< Import email_service
except ImportError as e:
    print(f"WARN: Could not import email_service: {e}")
    email_service = None
# --- End Service Imports ---

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

# --- ADD CORS CONFIGURATION HERE ---
CORS(app, 
     resources={r"/api/*": {"origins": "https://g1-po-app-77790.web.app"}},
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], # OPTIONS is needed for CORS preflight
     allow_headers=["Content-Type", "Authorization"], # Add any other headers your client sends
     supports_credentials=True # Good to have for flexibility
)
print("DEBUG APP_SETUP: CORS configured.")

app.debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

# --- Firebase Admin SDK Initialization ---
try:
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    firebase_project_id = "g1-po-app-77790" # Explicitly set your Firebase Project ID

    if cred_path:
        # Local development or specific service account usage
        # Ensure the service account key in cred_path BELONGS to firebase_project_id
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            'projectId': firebase_project_id,
        })
        print(f"DEBUG APP_SETUP: Firebase Admin SDK initialized using service account key from: {cred_path} for project {firebase_project_id}")
    else:
        # Cloud Run or other GCP environments where GOOGLE_APPLICATION_CREDENTIALS is not set
        # The runtime service account of Cloud Run MUST have permissions on firebase_project_id
        firebase_admin.initialize_app(options={
            'projectId': firebase_project_id,
        })
        print(f"DEBUG APP_SETUP: Firebase Admin SDK initialized using default environment credentials, explicitly targeting project {firebase_project_id}.")

except Exception as e_firebase_admin:
    print(f"ERROR APP_SETUP: Firebase Admin SDK initialization failed: {e_firebase_admin}")
    traceback.print_exc()
# --- End Firebase Admin SDK Init ---

# --- Configuration ---
db_connection_name = os.getenv("DB_CONNECTION_NAME")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
db_driver = os.getenv("DB_DRIVER", "pg8000") # Default to pg8000

bc_store_hash = os.getenv("BIGCOMMERCE_STORE_HASH")
bc_client_id = os.getenv("BIGCOMMERCE_CLIENT_ID") # Needed? Check usage
bc_access_token = os.getenv("BIGCOMMERCE_ACCESS_TOKEN")
domestic_country_code = os.getenv("DOMESTIC_COUNTRY_CODE", "US")
bc_processing_status_id = os.getenv("BC_PROCESSING_STATUS_ID")
bc_shipped_status_id = os.getenv("BC_SHIPPED_STATUS_ID")

# --- Ship From Address Config ---
SHIP_FROM_NAME = os.getenv("SHIP_FROM_NAME", "Your Company Name")
SHIP_FROM_CONTACT = os.getenv("SHIP_FROM_CONTACT", "Shipping Dept")
SHIP_FROM_STREET1 = os.getenv("SHIP_FROM_STREET1")
SHIP_FROM_STREET2 = os.getenv("SHIP_FROM_STREET2", "") # Optional
SHIP_FROM_CITY = os.getenv("SHIP_FROM_CITY")
SHIP_FROM_STATE = os.getenv("SHIP_FROM_STATE") # e.g., "NE"
SHIP_FROM_ZIP = os.getenv("SHIP_FROM_ZIP")
SHIP_FROM_COUNTRY = os.getenv("SHIP_FROM_COUNTRY", "US") # ISO 2-letter code
SHIP_FROM_PHONE = os.getenv("SHIP_FROM_PHONE")

# --- GCS Configuration ---
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
# --- End GCS Config ---

# ***** NEW: Company Logo Configuration *****
COMPANY_LOGO_GCS_URI = os.getenv("COMPANY_LOGO_GCS_URI") # e.g., "gs://your-bucket-name/path/to/your/logo.png"
if COMPANY_LOGO_GCS_URI:
    print(f"DEBUG APP_SETUP: Company logo URI configured: {COMPANY_LOGO_GCS_URI}")
else:
    print("WARN APP_SETUP: COMPANY_LOGO_GCS_URI environment variable not set. PDFs will not have a logo.")
# ***** END NEW CONFIG *****

# BigCommerce API Setup
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

# --- Database Connection Pool Initialization ---
engine = None
gcp_connector_instance = None
try:
    print("DEBUG APP_SETUP: Attempting DB engine init...")
    if not all([db_connection_name, db_user, db_password, db_name]):
        print("ERROR APP_SETUP: Missing one or more database connection environment variables.")
    else:
        print(f"DEBUG APP_SETUP: Initializing DB connection for {db_connection_name} using {db_driver}")
        gcp_connector_instance = GcpSqlConnector()

        def getconn(): # Closure to capture connector instance and credentials
            conn_gcp = gcp_connector_instance.connect(
                db_connection_name,
                db_driver,
                user=db_user,
                password=db_password,
                db=db_name
            )
            return conn_gcp

        engine = sqlalchemy.create_engine(
            f"postgresql+{db_driver}://", # DSN format for creator
            creator=getconn,
            pool_size=5,
            max_overflow=2,
            pool_timeout=30,
            pool_recycle=1800, # Recycle connections every 30 minutes
            echo=False # Set to True for verbose SQL logging if needed
        )
        print("DEBUG APP_SETUP: Database engine initialized successfully.")

except ImportError:
    print("ERROR APP_SETUP: google-cloud-sql-connector library not found. Please install it (`pip install google-cloud-sql-connector[pg8000]`).")
except Exception as e_engine:
    print(f"CRITICAL APP_SETUP: Database engine initialization failed: {e_engine}")
    import traceback
    traceback.print_exc()
    engine = None # Ensure engine is None if setup fails
    
print("DEBUG APP_SETUP: Finished DB engine init block.")
# --- End DB Setup ---

# --- GCS Client Initialization ---
storage_client = None
if storage:
    try:
        print("DEBUG APP_SETUP: Attempting GCS client init...") # Added log
        storage_client = storage.Client()
        print("DEBUG APP_SETUP: Google Cloud Storage client initialized successfully.")
    except Exception as gcs_e:
        print(f"ERROR APP_SETUP: Failed to initialize Google Cloud Storage client: {gcs_e}")
        traceback.print_exc()
        storage_client = None # Ensure client is None if init fails
else:
    print("WARN APP_SETUP: Google Cloud Storage library not loaded. File uploads will be skipped.")
print("DEBUG APP_SETUP: Finished GCS client init block.") # Added log
# --- End GCS Client Init ---


# === HELPER FUNCTIONS ===
def convert_row_to_dict(row):
    """Converts a SQLAlchemy Row object to a dictionary, handling Decimal and Datetime."""
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
    """Converts Decimal and Datetime objects in dicts/lists to strings for JSON."""
    if isinstance(data, dict): return {key: make_json_safe(value) for key, value in data.items()}
    elif isinstance(data, list): return [make_json_safe(item) for item in data]
    elif isinstance(data, Decimal): return str(data)
    elif isinstance(data, datetime):
        if data.tzinfo is None: data = data.replace(tzinfo=timezone.utc)
        return data.isoformat()
    else: return data

def _get_bc_shipping_address_id(bc_order_id):
    """Helper to fetch the first shipping address ID from BigCommerce for an order."""
    if not bc_api_base_url_v2 or not bc_headers:
        print("ERROR _get_bc_shipping_address_id: BC API not configured.")
        return None
    try:
        shipping_addr_url = f"{bc_api_base_url_v2}orders/{bc_order_id}/shippingaddresses"
        print(f"DEBUG _get_bc_shipping_address_id: Fetching from {shipping_addr_url}")
        response = requests.get(shipping_addr_url, headers=bc_headers)
        response.raise_for_status()
        shipping_addresses = response.json()
        if shipping_addresses and isinstance(shipping_addresses, list) and shipping_addresses[0].get('id'):
            addr_id = shipping_addresses[0]['id']
            print(f"DEBUG _get_bc_shipping_address_id: Found order_address_id: {addr_id}")
            return addr_id
        else:
            print(f"WARN _get_bc_shipping_address_id: No shipping addresses found or missing ID for BC Order {bc_order_id}.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"ERROR _get_bc_shipping_address_id: Failed to fetch BC shipping address for order {bc_order_id}: {e}")
        return None
    except Exception as e:
        print(f"ERROR _get_bc_shipping_address_id: Unexpected error fetching BC shipping address: {e}")
        return None

def get_hpe_mapping_with_fallback(original_sku_from_order, db_conn):
    """
    Attempts to find an HPE Option PN mapping for a given SKU.
    If the original SKU doesn't map, and it contains an underscore,
    it tries mapping the part after the last underscore.

    Args:
        original_sku_from_order (str): The SKU from the order line item.
        db_conn (sqlalchemy.engine.Connection): Active database connection.

    Returns:
        tuple: (hpe_option_pn, hpe_pn_type, sku_used_for_mapping)
               Returns (None, None, original_sku_from_order) if no mapping is found.
    """
    hpe_option_pn = None
    hpe_pn_type = None
    sku_to_try = original_sku_from_order
    sku_actually_mapped = original_sku_from_order # Default to original

    if not sku_to_try: # Handle empty or None original_sku
        return None, None, original_sku_from_order

    # Attempt 1: Direct lookup with original_sku_from_order
    query = text("SELECT option_pn, pn_type FROM hpe_part_mappings WHERE sku = :sku")
    result = db_conn.execute(query, {"sku": sku_to_try}).fetchone()

    if result:
        hpe_option_pn = result.option_pn
        hpe_pn_type = result.pn_type
        print(f"DEBUG MAP_FALLBACK: Direct map for '{sku_to_try}' -> OptionPN: {hpe_option_pn}")
        return hpe_option_pn, hpe_pn_type, sku_to_try

    # Attempt 2: Fallback logic if original_sku_from_order contains '_'
    if '_' in original_sku_from_order:
        parts = original_sku_from_order.split('_')
        # Take the last part after the underscore, assuming it might be the relevant SKU
        sku_after_underscore = parts[-1] 
        if sku_after_underscore and sku_after_underscore != original_sku_from_order: # Ensure it's different and not empty
            print(f"DEBUG MAP_FALLBACK: No direct map for '{original_sku_from_order}'. Trying fallback with SKU part: '{sku_after_underscore}'")
            sku_to_try = sku_after_underscore
            result_fallback = db_conn.execute(query, {"sku": sku_to_try}).fetchone()

            if result_fallback:
                hpe_option_pn = result_fallback.option_pn
                hpe_pn_type = result_fallback.pn_type
                sku_actually_mapped = sku_to_try # This SKU resulted in the map
                print(f"DEBUG MAP_FALLBACK: Fallback map for '{sku_to_try}' -> OptionPN: {hpe_option_pn}")
                return hpe_option_pn, hpe_pn_type, sku_actually_mapped
            else:
                print(f"DEBUG MAP_FALLBACK: Fallback SKU part '{sku_to_try}' also not found in hpe_part_mappings.")
        else:
            print(f"DEBUG MAP_FALLBACK: SKU '{original_sku_from_order}' contains '_' but part after underscore is empty, invalid, or same as original.")
    else:
        print(f"DEBUG MAP_FALLBACK: No direct map for '{original_sku_from_order}' and no '_' for fallback.")

    return None, None, original_sku_from_order # No mapping found, return original SKU as sku_actually_mapped
print("DEBUG APP_SETUP: Helper functions defined.") # Added log

# === AUTHENTICATION DECORATOR ===
from functools import wraps

def verify_firebase_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        id_token = None

        if auth_header and auth_header.startswith('Bearer '):
            id_token = auth_header.split('Bearer ')[1]
        
        if not id_token:
            print("WARN AUTH: Missing Authorization Bearer token.")
            return jsonify({"error": "Unauthorized", "message": "Authorization token is missing or not Bearer type."}), 401

        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
            g.user_uid = decoded_token.get('uid') # Store UID in Flask's g context
            g.user_email = decoded_token.get('email')
            
            # ***** MODIFIED: Check for Custom Claim 'isApproved' *****
            if not decoded_token.get('isApproved') == True:
                print(f"WARN AUTH: User {g.user_email} (UID: {g.user_uid}) is authenticated but NOT AUTHORIZED (missing or false 'isApproved' claim).")
                return jsonify({"error": "Forbidden", "message": "You are not authorized to access this application."}), 403
            
            print(f"DEBUG AUTH: Token verified for user UID: {g.user_uid}, Email: {g.user_email}. User IS APPROVED.")

        except firebase_auth.ExpiredIdTokenError:
            print("WARN AUTH: Expired ID token.")
            return jsonify({"error": "Unauthorized", "message": "Token has expired. Please log in again."}), 401
        except firebase_auth.InvalidIdTokenError as e:
            print(f"ERROR AUTH: Invalid ID token: {e}")
            return jsonify({"error": "Unauthorized", "message": "Invalid ID token."}), 401
        except Exception as e:
            print(f"ERROR AUTH: Unexpected error during token verification: {e}")
            traceback.print_exc()
            return jsonify({"error": "Unauthorized", "message": "Could not verify authentication token."}), 401
        
        return f(*args, **kwargs)
    return decorated_function


# === BASIC ROUTES ===
@app.route('/')
def hello(): return 'G1 PO App Backend is Running!'
print("DEBUG APP_SETUP: Defined / route.") # Added log

@app.route('/test_db')
def test_db_connection():
    if engine is None: return jsonify({"message": "DB engine not initialized"}), 500
    conn = None
    try:
        conn = engine.connect()
        result = conn.execute(sqlalchemy.text("SELECT 1")).scalar_one_or_none()
        conn.close()
        if result == 1: return jsonify({"message": "DB connection successful!"})
        return jsonify({"message": "Unexpected DB result"}), 500
    except Exception as e:
        print(f"ERROR /test_db: {e}"); traceback.print_exc()
        if conn and not conn.closed: conn.close()
        return jsonify({"message": f"DB query failed: {e}"}), 500
print("DEBUG APP_SETUP: Defined /test_db route.") # Added log

# === ORDER ROUTES ===
# --- GET List Orders ---
@app.route('/api/orders', methods=['GET'])
@verify_firebase_token # Apply decorator
def get_orders():
    print("DEBUG GET_ORDERS: Received request")
    # --- NEW: Get status filter from query parameter ---
    status_filter = request.args.get('status') # e.g., /api/orders?status=new
    print(f"DEBUG GET_ORDERS: Status filter = {status_filter}")
    # ----------------------------------------------------

    db_conn = None
    try:
        if engine is None: return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()

        # --- NEW: Build query dynamically ---
        base_query = "SELECT * FROM orders"
        params = {}
        if status_filter and status_filter != 'all': # Add WHERE clause if filter is provided and not 'all'
            base_query += " WHERE status = :status_filter"
            params["status_filter"] = status_filter

        # Add ordering (adjust column if needed) - always good to have consistent order
        base_query += " ORDER BY order_date DESC, id DESC"
        # ----------------------------------

        query = text(base_query)
        records = db_conn.execute(query, params).fetchall()
        orders_list = [convert_row_to_dict(row) for row in records]

        # Add make_json_safe if necessary for complex types
        return jsonify(make_json_safe(orders_list)), 200 # Use make_json_safe

    except Exception as e:
        # ... (error handling remains the same) ...
        print(f"ERROR GET_ORDERS: {e}")
        # print(traceback.format_exc()) # Uncomment for detailed errors
        return jsonify({"error": "Failed to fetch orders", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed: db_conn.close()
        print("DEBUG GET_ORDERS: DB connection closed.")
print("DEBUG APP_SETUP: Defined /api/orders GET route.") # Added log

# --- GET Single Order Details ---
@app.route('/api/orders/<int:order_id>', methods=['GET'])
@verify_firebase_token # Apply decorator
def get_order_details(order_id):
    print(f"DEBUG GET_ORDER: Received request for order ID: {order_id}")
    db_conn = None
    try:
        if engine is None:
            print("ERROR GET_ORDER: Database engine not available.")
            return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()
        print(f"DEBUG GET_ORDER: DB connection established for order ID: {order_id}")

        order_query = text("SELECT * FROM orders WHERE id = :order_id")
        order_record = db_conn.execute(order_query, {"order_id": order_id}).fetchone()
        
        if not order_record:
            print(f"WARN GET_ORDER: Order with ID {order_id} not found.")
            return jsonify({"error": f"Order with ID {order_id} not found"}), 404
        order_data_dict = convert_row_to_dict(order_record)

        # Fetch base line items first
        base_line_items_sql = """
            SELECT
                oli.id AS line_item_id,
                oli.order_id AS parent_order_id,
                oli.bigcommerce_line_item_id,
                oli.sku AS original_sku,
                oli.name AS line_item_name,
                oli.quantity,
                oli.sale_price,
                oli.created_at AS line_item_created_at,
                oli.updated_at AS line_item_updated_at
            FROM order_line_items oli
            WHERE oli.order_id = :order_id_param
            ORDER BY oli.id
        """
        base_line_items_records = db_conn.execute(text(base_line_items_sql), {"order_id_param": order_id}).fetchall()
        
        augmented_line_items_list = []
        for row in base_line_items_records:
            item_dict = convert_row_to_dict(row)
            original_sku_for_item = item_dict.get('original_sku')

            # Use the new helper function
            hpe_option_pn, hpe_pn_type, sku_mapped = get_hpe_mapping_with_fallback(original_sku_for_item, db_conn)
            
            item_dict['hpe_option_pn'] = hpe_option_pn
            item_dict['hpe_pn_type'] = hpe_pn_type
            item_dict['hpe_po_description'] = None # Default

            if hpe_option_pn:
                # Fetch custom description for this hpe_option_pn
                desc_query = text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn")
                custom_desc_result = db_conn.execute(desc_query, {"option_pn": hpe_option_pn}).scalar_one_or_none()
                if custom_desc_result:
                    item_dict['hpe_po_description'] = custom_desc_result
            
            augmented_line_items_list.append(item_dict)

        print(f"DEBUG GET_ORDER: Found order ID {order_id} with {len(augmented_line_items_list)} augmented line items (with fallback logic).")
        
        response_data = {"order": make_json_safe(order_data_dict), "line_items": make_json_safe(augmented_line_items_list)}
        return jsonify(response_data), 200

    except Exception as e:
        original_error_traceback = traceback.format_exc()
        print(f"ERROR GET_ORDER: Error fetching order {order_id}: {e}")
        print("--- ORIGINAL ERROR TRACEBACK ---"); print(original_error_traceback); print("--- END ---")
        return jsonify({"error": "An unexpected error occurred while fetching order details.", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print(f"DEBUG GET_ORDER: Database connection closed for order ID {order_id}.")
        # ... (other logging for db_conn state if needed)
print("DEBUG APP_SETUP: Defined /api/orders/<id> GET route.") # Added log 

@app.route('/api/lookup/spare_part/<path:option_sku>', methods=['GET'])
@verify_firebase_token # Assuming this lookup also needs to be authenticated
def get_spare_part_for_option(option_sku):
    if not option_sku:
        return jsonify({"error": "Option SKU is required"}), 400
    
    db_conn = None
    print(f"DEBUG LOOKUP_SPARE: Received request for option SKU: {option_sku}")
    try:
        if engine is None:
            return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()

        # Step 1: Verify the input SKU is an 'option' type
        check_option_type_query = text("""
            SELECT pn_type 
            FROM hpe_part_mappings 
            WHERE sku = :option_sku OR option_pn = :option_sku 
        """) # Check in both sku and option_pn columns as 'option' SKUs might be listed as option_pn too.
             # Be more specific if 'option' type SKUs are *only* ever in the 'option_pn' column for other records,
             # or if 'sku' column is the primary key for an 'option' type part.
             # Assuming item.original_sku could be either 'sku' or 'option_pn' from hpe_part_mappings table itself.
             # For clarity, let's assume item.original_sku is indeed an option_pn that we are looking up.
        
        # More precise check if item.original_sku is always the 'option_pn' value for 'option' types
        check_option_type_query_precise = text("""
            SELECT pn_type
            FROM hpe_part_mappings
            WHERE option_pn = :option_sku AND pn_type = 'option' 
            LIMIT 1 
        """) # If an option part is identified by its option_pn field and pn_type='option'
        
        # Simpler assumption: If we find it as an option_pn, that's good enough to proceed to find its spare.
        # The most direct interpretation: item.original_sku *is* an option_pn.
        # So we need to find a spare whose option_pn is item.original_sku.

        find_spare_query = text("""
            SELECT sku 
            FROM hpe_part_mappings
            WHERE option_pn = :option_sku AND pn_type = 'spare'
        """)
        
        spare_part_sku_record = db_conn.execute(find_spare_query, {"option_sku": option_sku}).fetchone()

        if spare_part_sku_record and spare_part_sku_record.sku:
            spare_sku = spare_part_sku_record.sku
            print(f"DEBUG LOOKUP_SPARE: Found spare part SKU '{spare_sku}' for option SKU '{option_sku}'.")
            return jsonify({"spare_sku": spare_sku}), 200
        else:
            # Before returning not found, let's check if the original_sku was even a valid 'option' type.
            # This check can be based on how 'option' parts are stored. If item.original_sku is THE option_pn itself:
            is_option_query = text("SELECT 1 FROM hpe_part_mappings WHERE option_pn = :option_sku AND pn_type = 'option' LIMIT 1")
            # Or if item.original_sku is a generic SKU that *maps* to an option_pn which is also an 'option' type:
            # is_option_query = text("SELECT 1 FROM hpe_part_mappings WHERE sku = :option_sku AND pn_type = 'option' LIMIT 1")

            is_valid_option = db_conn.execute(is_option_query, {"option_sku": option_sku}).fetchone()
            
            if not is_valid_option:
                print(f"DEBUG LOOKUP_SPARE: Input SKU '{option_sku}' is not registered as an 'option' type or not found as an option_pn for an option type part.")
                # Return a specific response or just proceed to "spare not found"
                # Depending on requirements, you might not need this explicit check if the spare lookup failing is sufficient.
            
            print(f"DEBUG LOOKUP_SPARE: No spare part SKU found for option SKU '{option_sku}'.")
            return jsonify({"spare_sku": None, "message": "No corresponding spare part found or input SKU is not a valid option."}), 404

    except Exception as e:
        print(f"ERROR LOOKUP_SPARE: Error looking up spare part for option SKU {option_sku}: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to lookup spare part", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print(f"DEBUG LOOKUP_SPARE: DB connection closed for option SKU {option_sku}.")

# ***** NEW: Endpoint to get order counts by status *****
@app.route('/api/orders/status-counts', methods=['GET'])
@verify_firebase_token # Apply decorator
def get_order_status_counts():
    print("DEBUG GET_STATUS_COUNTS: Received request")
    db_conn = None
    try:
        if engine is None:
            print("ERROR GET_STATUS_COUNTS: Database engine not available.")
            return jsonify({"error": "Database engine not available."}), 500

        db_conn = engine.connect()
        print("DEBUG GET_STATUS_COUNTS: DB connection established.")

        sql_query = text("""
            SELECT status, COUNT(id) AS order_count
            FROM orders
            GROUP BY status;
        """)

        records = db_conn.execute(sql_query).fetchall()

        status_counts_dict = {}
        for row in records:
            row_dict = convert_row_to_dict(row) # Use your existing helper
            if row_dict and row_dict.get('status') is not None:
                status_counts_dict[row_dict['status']] = row_dict.get('order_count', 0)

        print(f"DEBUG GET_STATUS_COUNTS: Fetched counts: {status_counts_dict}")
        # Ensure all desired statuses are present, even if count is 0
        # (This is optional, frontend can handle missing keys, but good for consistency)
        defined_statuses = ['new', 'RFQ Sent', 'Processed', 'international_manual', 'pending', 'Completed Offline'] # Match frontend's expectations
        for s in defined_statuses:
            if s not in status_counts_dict:
                status_counts_dict[s] = 0

        return jsonify(make_json_safe(status_counts_dict)), 200 # Use your existing helper

    except Exception as e:
        print(f"ERROR GET_STATUS_COUNTS: {e}")
        # print(traceback.format_exc()) # Uncomment for detailed errors during development
        return jsonify({"error": "Failed to fetch order status counts", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print("DEBUG GET_STATUS_COUNTS: DB connection closed.")
print("DEBUG APP_SETUP: Defined /api/orders/status-counts GET route.") # Add a log for this new route
# ***** END NEW Endpoint *****

# --- NEW: Endpoint to update order status ---
@app.route('/api/orders/<int:order_id>/status', methods=['POST'])
@verify_firebase_token # Apply decorator
def update_order_status(order_id):
    """Updates the status of a specific order."""
    print(f"DEBUG UPDATE_STATUS: Received request for order ID: {order_id}")
    data = request.get_json()
    new_status = data.get('status')

    if not new_status:
        return jsonify({"error": "Missing 'status' in request body"}), 400

    # Optional: Validate the new_status against allowed values
    allowed_statuses = [
        'new',
        'Processed',
        'RFQ Sent',
        'international_manual',
        'pending',
        'Completed Offline', # <-- ADD THIS NEW STATUS
        'other_status' # Keep if used, or remove if not
    ]
    if new_status not in allowed_statuses:
        return jsonify({"error": f"Invalid status value: {new_status}"}), 400

    db_conn = None
    transaction = None
    try:
        if engine is None: return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()
        transaction = db_conn.begin()

        update_sql = text("""
            UPDATE orders
            SET status = :new_status, updated_at = CURRENT_TIMESTAMP
            WHERE id = :order_id
            RETURNING id, status, updated_at -- Return updated values
        """)
        result = db_conn.execute(update_sql, {"new_status": new_status, "order_id": order_id})
        updated_row = result.fetchone()

        if updated_row is None:
             transaction.rollback()
             print(f"WARN UPDATE_STATUS: Order ID {order_id} not found for status update.")
             return jsonify({"error": f"Order with ID {order_id} not found"}), 404

        transaction.commit()
        updated_data = convert_row_to_dict(updated_row)
        print(f"DEBUG UPDATE_STATUS: Successfully updated order {order_id} status to '{new_status}'.")
        return jsonify({
            "message": f"Order {order_id} status updated to {new_status}",
            "order": make_json_safe(updated_data) # Use make_json_safe
            }), 200

    except Exception as e:
        if transaction and transaction.is_active: transaction.rollback()
        print(f"ERROR UPDATE_STATUS: Failed for order {order_id}: {e}")
        # print(traceback.format_exc())
        return jsonify({"error": "Failed to update order status", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed: db_conn.close()
        print(f"DEBUG UPDATE_STATUS: DB connection closed for order ID {order_id}.")
print("DEBUG APP_SETUP: Defined /api/orders/<id>/status POST route.") # Added log

# --- Route to Ingest Orders from BigCommerce using requests ---
@app.route('/api/ingest_orders', methods=['POST'])
@verify_firebase_token # Apply decorator
def ingest_orders():
    """
    Ingests orders from BigCommerce based on status ID.
    Stores order details, including separate sales tax, and line items
    with tax-exclusive prices.
    """
    try:
        print("Received request for /api/ingest_orders")
        # --- Basic Configuration Checks (Same as before) ---
        if not bc_api_base_url_v2 or not bc_headers:
            return jsonify({"message": "BigCommerce API credentials not fully configured."}), 500
        try:
            target_status_id = int(bc_processing_status_id)
        except (ValueError, TypeError):
            return jsonify({"message": f"BC_PROCESSING_STATUS_ID '{bc_processing_status_id}' is invalid."}), 500
        if engine is None:
            return jsonify({"message": "Database engine not initialized."}), 500
        # --- End Basic Checks ---

        orders_list_endpoint = f"{bc_api_base_url_v2}orders"
        # Fetch orders with the specified status
        api_params = {'status_id': target_status_id, 'sort': 'date_created:asc', 'limit': 250}
        print(f"DEBUG INGEST: Fetching orders with status ID {target_status_id} from {orders_list_endpoint}")
        response = requests.get(orders_list_endpoint, headers=bc_headers, params=api_params)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        orders_list_from_bc = response.json()

        # --- Response Validation (Same as before) ---
        if not isinstance(orders_list_from_bc, list):
            print(f"ERROR INGEST: Unexpected API response format. Expected list, got {type(orders_list_from_bc)}")
            return jsonify({"message": "Ingestion failed: Unexpected API response format."}), 500
        if not orders_list_from_bc:
            print(f"INFO INGEST: Successfully ingested 0 orders with BC status ID '{target_status_id}'.")
            return jsonify({"message": f"Successfully ingested 0 orders with BC status ID '{target_status_id}'."}), 200
        # --- End Response Validation ---

        ingested_count = 0
        inserted_count_this_run = 0
        updated_count_this_run = 0

        # Use a connection from the pool
        with engine.connect() as conn:
            # Start a transaction
            with conn.begin():
                print(f"DEBUG INGEST: Processing {len(orders_list_from_bc)} orders from BigCommerce.")
                for bc_order_summary in orders_list_from_bc:
                    order_id_from_bc = bc_order_summary.get('id')
                    if order_id_from_bc is None:
                        print("WARN INGEST: Skipping order summary with missing 'id'.")
                        continue

                    print(f"DEBUG INGEST: Processing BC Order ID: {order_id_from_bc}")

                    # --- Fetch Shipping Address and Products (Same as before, but ensure error handling) ---
                    shipping_addresses_list = []
                    products_list = []
                    is_international = False
                    calculated_shipping_method_name = 'N/A'
                    customer_shipping_address = {}

                    try:
                        # Fetch shipping address
                        shipping_addr_url = f"{bc_api_base_url_v2}orders/{order_id_from_bc}/shippingaddresses"
                        shipping_res = requests.get(shipping_addr_url, headers=bc_headers)
                        shipping_res.raise_for_status()
                        shipping_addresses_list = shipping_res.json()
                        if shipping_addresses_list and isinstance(shipping_addresses_list, list) and shipping_addresses_list[0]:
                            customer_shipping_address = shipping_addresses_list[0]
                            shipping_country_code = customer_shipping_address.get('country_iso2')
                            is_international = bool(shipping_country_code and shipping_country_code != domestic_country_code)
                            calculated_shipping_method_name = customer_shipping_address.get('shipping_method', bc_order_summary.get('shipping_method', 'N/A'))
                        else:
                             print(f"WARN INGEST: No valid shipping address found for BC Order {order_id_from_bc}.")
                             # Decide if you want to skip or proceed without address details
                             # continue # Uncomment to skip if address is mandatory

                        # Fetch products
                        products_url = f"{bc_api_base_url_v2}orders/{order_id_from_bc}/products"
                        products_res = requests.get(products_url, headers=bc_headers)
                        products_res.raise_for_status()
                        products_list = products_res.json()
                        if not isinstance(products_list, list):
                            print(f"WARN INGEST: Products list for BC Order {order_id_from_bc} is not a list. Treating as empty.")
                            products_list = []

                    except requests.exceptions.RequestException as sub_req_e:
                        print(f"ERROR INGEST: Could not fetch sub-resources (address/products) for BC Order {order_id_from_bc}: {sub_req_e}. Skipping this order.")
                        continue # Skip this order if sub-resources fail
                    # --- End Fetch Sub-resources ---

                    # --- Basic Validation (e.g., require shipping details - adjust as needed) ---
                    # if not all(customer_shipping_address.get(k) for k in ['street_1', 'city', 'zip', 'country_iso2']):
                    #     print(f"WARN INGEST: Skipping BC Order {order_id_from_bc} due to missing essential shipping details.")
                    #     continue
                    # --- End Basic Validation ---

                    # --- Check if order exists locally ---
                    existing_order_row = conn.execute(
                        text("""
                            SELECT id, status, is_international, payment_method, bigcommerce_order_tax, customer_notes
                            FROM orders
                            WHERE bigcommerce_order_id = :bc_order_id
                        """),
                        {"bc_order_id": order_id_from_bc}
                    ).fetchone()
                    # --- End Check ---

                    # --- ** NEW: Extract Sales Tax and Total (Inc Tax) from BC Order Summary ---
                    # Use Decimal for monetary values
                    bc_total_tax = Decimal(bc_order_summary.get('total_tax', '0.00'))
                    bc_total_inc_tax = Decimal(bc_order_summary.get('total_inc_tax', '0.00'))
                    # --- End Extract ---

                    current_time_utc = datetime.now(timezone.utc)

                    raw_customer_message = bc_order_summary.get('customer_message', '')
                    cleaned_customer_message = raw_customer_message
                    if raw_customer_message:
                        pattern = re.compile(r'\*{10}.*?\*{10}', re.DOTALL) 
                        cleaned_customer_message = pattern.sub('', raw_customer_message).strip()
                        if raw_customer_message != cleaned_customer_message:
                            print(f"DEBUG INGEST: Cleaned customer notes for BC Order {order_id_from_bc}. Original: '{raw_customer_message[:100]}...', Cleaned: '{cleaned_customer_message[:100]}...'")

                    if existing_order_row:
                        db_status = existing_order_row.status
                        print(f"DEBUG INGEST: Order {order_id_from_bc} exists (App ID: {existing_order_row.id}). DB status: '{db_status}'.")

                        # Define statuses that mean "don't touch this order further during routine ingest"
                        finalized_or_manual_statuses = ['Processed', 'Completed Offline', 'pending', 'RFQ Sent', 'international_manual']
                        # Add any other status that signifies the order is beyond the 'new' automated ingest stage.

                        if db_status in finalized_or_manual_statuses:
                            print(f"DEBUG INGEST: Skipping further processing for BC Order {order_id_from_bc} as its local status is '{db_status}'.")
                            # You might still want to update minor fields if necessary, like payment_method or tax,
                            # but not the status or re-evaluate it as 'new'.
                            # The existing logic for updating payment_method, is_international, bigcommerce_order_tax
                            # can remain, but the status part should be skipped as handled by the `statuses_to_preserve`
                            # logic below (or ensure this `continue` is placed strategically).

                            # For a strict "ingest once and don't touch status again" policy for these statuses:
                            continue # This would skip ALL updates below for this order if its status is in finalized_or_manual_statuses

                        # --- Handle Existing Order (Update if necessary) ---
                        db_is_international = existing_order_row.is_international
                        db_payment_method = existing_order_row.payment_method
                        db_tax_amount = existing_order_row.bigcommerce_order_tax
                        db_customer_notes = existing_order_row.customer_notes # Now available

                        bc_payment_method = bc_order_summary.get('payment_method')

                        update_fields = {}
                        if db_is_international != is_international: update_fields['is_international'] = is_international
                        if db_payment_method != bc_payment_method: update_fields['payment_method'] = bc_payment_method
                        if db_tax_amount != bc_total_tax: update_fields['bigcommerce_order_tax'] = bc_total_tax

                        if db_customer_notes != cleaned_customer_message: # Always update notes if they differ
                            update_fields['customer_notes'] = cleaned_customer_message
                        
                        # Only update status if it's not a finalized/manual one AND it's different from what ingest would set
                        if db_status not in finalized_or_manual_statuses: # This condition is now mainly for non-finalized statuses
                            new_app_status_by_ingest = 'international_manual' if is_international else 'new'
                            if db_status != new_app_status_by_ingest:
                                print(f"DEBUG INGEST: Current status '{db_status}' for order {order_id_from_bc} is not a finalized/manual one and differs. Setting to '{new_app_status_by_ingest}'.")
                                update_fields['status'] = new_app_status_by_ingest
                        # The 'else' part of this specific block is no longer strictly necessary if the `continue` above is active,
                        # but leaving it doesn't harm (it just won't be reached for finalized_or_manual_statuses).
                        else:
                            print(f"DEBUG INGEST: Preserving current finalized/manual status '{db_status}' for order {order_id_from_bc} (this log might not be hit if 'continue' is active).")

                        if update_fields:
                            update_fields['updated_at'] = current_time_utc
                            set_clauses = [f"{key} = :{key}" for key in update_fields.keys()]
                            update_stmt_str = f"UPDATE orders SET {', '.join(set_clauses)} WHERE id = :id"
                            conn.execute(text(update_stmt_str), {"id": existing_order_row.id, **update_fields})
                            print(f"DEBUG INGEST: Updated Order {order_id_from_bc} (App ID: {existing_order_row.id}). Fields: {list(update_fields.keys())}")
                            updated_count_this_run += 1
                        else:
                            print(f"DEBUG INGEST: No updates needed for existing order {order_id_from_bc} beyond preserving status.")
                        # --- End Handle Existing Order ---
                    else:                        # --- Handle New Order (Insert) ---
                        target_app_status = 'international_manual' if is_international else 'new'

                        # Prepare values for the new order row
                        order_values = {
                            "bigcommerce_order_id": order_id_from_bc,
                            "customer_company": customer_shipping_address.get('company'),
                            "customer_name": f"{customer_shipping_address.get('first_name', '')} {customer_shipping_address.get('last_name', '')}".strip(),
                            "customer_shipping_address_line1": customer_shipping_address.get('street_1'),
                            "customer_shipping_address_line2": customer_shipping_address.get('street_2'),
                            "customer_shipping_city": customer_shipping_address.get('city'),
                            "customer_shipping_state": customer_shipping_address.get('state'),
                            "customer_shipping_zip": customer_shipping_address.get('zip'),
                            "customer_shipping_country": customer_shipping_address.get('country_iso2'),
                            "customer_phone": customer_shipping_address.get('phone'),
                            "customer_email": bc_order_summary.get('billing_address', {}).get('email', customer_shipping_address.get('email')), # Fallback email
                            "customer_shipping_method": calculated_shipping_method_name,
                            "customer_notes": cleaned_customer_message, 
                            "order_date": datetime.strptime(bc_order_summary['date_created'], '%a, %d %b %Y %H:%M:%S %z').replace(tzinfo=timezone.utc) if bc_order_summary.get('date_created') else current_time_utc,
                            "total_sale_price": bc_total_inc_tax, # Store total including tax here
                            "bigcommerce_order_tax": bc_total_tax, # ** NEW: Store the separate tax amount **
                            "status": target_app_status,
                            "is_international": is_international,
                            "payment_method": bc_order_summary.get('payment_method'),
                            "created_at": current_time_utc,
                            "updated_at": current_time_utc
                        }

                        # Define columns for insertion
                        order_table_cols = [sqlalchemy.column(c) for c in order_values.keys()]
                        # Create and execute the insert statement
                        insert_order_stmt = insert(sqlalchemy.table('orders', *order_table_cols)).values(order_values).returning(sqlalchemy.column('id'))
                        inserted_order_id = conn.execute(insert_order_stmt).scalar_one()
                        print(f"DEBUG INGEST: Inserted new Order {order_id_from_bc} (App ID {inserted_order_id}), status: {target_app_status}, Tax: {bc_total_tax}")
                        inserted_count_this_run += 1

                        # --- Insert Line Items for the New Order ---
                        if products_list:
                            for item in products_list:
                                if not isinstance(item, dict):
                                     print(f"WARN INGEST: Skipping invalid item data for order {inserted_order_id}: {item}")
                                     continue

                                # ** NEW: Use price_ex_tax for sale_price **
                                sale_price_excl_tax = Decimal(item.get('price_ex_tax', '0.00'))

                                line_item_values = {
                                    "order_id": inserted_order_id,
                                    "bigcommerce_line_item_id": item.get('id'),
                                    "sku": item.get('sku'),
                                    "name": item.get('name'),
                                    "quantity": item.get('quantity'),
                                    "sale_price": sale_price_excl_tax, # ** Store tax-exclusive price **
                                    "created_at": current_time_utc,
                                    "updated_at": current_time_utc
                                }
                                line_item_table_cols = [sqlalchemy.column(c) for c in line_item_values.keys()]
                                conn.execute(insert(sqlalchemy.table('order_line_items', *line_item_table_cols)).values(line_item_values))
                            print(f"DEBUG INGEST: Inserted {len(products_list)} line items for new order {inserted_order_id}.")
                        else:
                            print(f"WARN INGEST: No products found or processed for new BC Order {order_id_from_bc}.")
                        # --- End Insert Line Items ---
                        # --- End Handle New Order ---

                    ingested_count += 1 # Increment regardless of insert/update

        # Transaction automatically commits here if no exceptions occurred
        print(f"INFO INGEST: Successfully processed {ingested_count} orders. Inserted: {inserted_count_this_run}, Updated: {updated_count_this_run}.")
        return jsonify({"message": f"Processed {ingested_count} orders. Inserted {inserted_count_this_run} new. Updated {updated_count_this_run}."}), 200

    except requests.exceptions.RequestException as req_e:
        # --- Error Handling for API Requests (Same as before) ---
        error_message = f"BigCommerce API Request failed: {req_e}"
        status_code = req_e.response.status_code if req_e.response is not None else 'N/A'
        response_text = req_e.response.text if req_e.response is not None else 'N/A'
        print(f"ERROR INGEST: {error_message}, Status: {status_code}, Response: {response_text[:500]}")
        # Note: Transaction is automatically rolled back by 'with conn.begin()' context manager on exception
        return jsonify({"message": error_message, "status_code": status_code, "response_preview": response_text[:500]}), 500
    except sqlalchemy.exc.SQLAlchemyError as db_e:
        # --- Error Handling for Database Operations ---
        print(f"ERROR INGEST: Database error during ingestion: {db_e}")
        traceback.print_exc()
        # Transaction automatically rolled back
        return jsonify({"message": f"Database error during order ingestion: {db_e}", "error_type": type(db_e).__name__}), 500
    except Exception as e:
        # --- General Error Handling (Same as before) ---
        print(f"ERROR INGEST: Unexpected error during ingestion: {e}")
        traceback.print_exc()
        # Transaction automatically rolled back
        return jsonify({"message": f"Unexpected error during order ingestion: {e}", "error_type": type(e).__name__}), 500
# --- End ingest_orders ---

@app.route('/api/tasks/trigger-daily-iif', methods=['POST'])
def trigger_daily_iif_generation():
    """
    Triggers the generation and emailing of the daily IIF batch file.
    This endpoint is intended to be called by a scheduler (e.g., Google Cloud Scheduler).
    """
    print("INFO APP: Received request to trigger daily IIF generation.")
    
    if iif_generator is None:
        print("ERROR APP (IIF_TRIGGER): iif_generator module not loaded. Cannot run task.")
        return jsonify({"error": "IIF generation module not available."}), 500

    if engine is None:
        print("ERROR APP (IIF_TRIGGER): Database engine not initialized. Cannot run task.")
        return jsonify({"error": "Database engine not available."}), 500

    try:
        # The iif_generator.create_and_email_daily_iif_batch function
        # is designed to use the imported 'engine' if available,
        # or create its own if run standalone. Here, we explicitly pass app's engine.
        print("INFO APP (IIF_TRIGGER): Calling iif_generator.create_and_email_daily_iif_batch...")
        iif_generator.create_and_email_daily_iif_batch(engine) # Pass the app's engine instance
        
        print("INFO APP (IIF_TRIGGER): Daily IIF generation task completed successfully by the generator script.")
        return jsonify({"message": "Daily IIF generation task triggered successfully."}), 200
    except Exception as e:
        print(f"ERROR APP (IIF_TRIGGER): Error during IIF generation task: {e}")
        traceback.print_exc()
        return jsonify({"error": "An error occurred while triggering the IIF generation task.", "details": str(e)}), 500


# === SUPPLIER CRUD ROUTES ===
@app.route('/api/suppliers', methods=['POST'])
@verify_firebase_token # Apply decorator
def create_supplier():
    try:
        print("Received request for POST /api/suppliers")
        if engine is None:
            print("CREATE_SUPPLIER Error: Database engine not initialized.")
            return jsonify({"message": "Database engine not initialized."}), 500
        conn = None 
        trans = None 
        supplier_data = request.json
        print(f"DEBUG CREATE_SUPPLIER: Received data: {supplier_data}")
        required_fields = ['name', 'email']
        for field in required_fields:
            if not supplier_data or field not in supplier_data or not supplier_data[field]:
                print(f"DEBUG CREATE_SUPPLIER: Missing required field: {field}")
                return jsonify({"message": f"Missing required field: {field}"}), 400 
        name = supplier_data.get('name')
        email = supplier_data.get('email')
        payment_terms = supplier_data.get('payment_terms') 
        address_line1 = supplier_data.get('address_line1')
        address_line2 = supplier_data.get('address_line2')
        city = supplier_data.get('city')
        state = supplier_data.get('state')
        zip_code = supplier_data.get('zip') 
        country = supplier_data.get('country')
        phone = supplier_data.get('phone')
        contact_person = supplier_data.get('contact_person')
        actual_default_po_notes_value = supplier_data.get('defaultponotes') 
        conn = engine.connect()
        trans = conn.begin() 
        insert_supplier_stmt = insert(sqlalchemy.table(
            'suppliers', 
            sqlalchemy.column('name'),
            sqlalchemy.column('email'),
            sqlalchemy.column('payment_terms'),
            sqlalchemy.column('address_line1'),
            sqlalchemy.column('address_line2'),
            sqlalchemy.column('city'),
            sqlalchemy.column('state'),
            sqlalchemy.column('zip'),
            sqlalchemy.column('country'),
            sqlalchemy.column('phone'),
            sqlalchemy.column('contact_person'),
            sqlalchemy.column('defaultponotes'), 
            sqlalchemy.column('created_at'),
            sqlalchemy.column('updated_at')
        )).values( 
            name = name,
            email = email,
            payment_terms = payment_terms,
            address_line1 = address_line1,
            address_line2 = address_line2,
            city = city,
            state = state,
            zip = zip_code, 
            country = country,
            phone = phone,
            contact_person = contact_person,
            defaultponotes=actual_default_po_notes_value, 
            created_at = datetime.now(timezone.utc), 
            updated_at = datetime.now(timezone.utc) 
        ) 
        result = conn.execute(insert_supplier_stmt.returning(sqlalchemy.column('id')))
        inserted_supplier_id = result.fetchone()[0] 
        trans.commit() 
        print(f"DEBUG CREATE_SUPPLIER: Successfully inserted supplier with ID: {inserted_supplier_id}")
        return jsonify({
            "message": "Supplier created successfully",
            "supplier_id": inserted_supplier_id
        }), 201 
    except sqlalchemy.exc.IntegrityError as e:
        if conn and trans: 
             try:
                trans.rollback()
                print("DEBUG CREATE_SUPPLIER: Transaction rolled back due to Integrity Error.")
             except Exception as rollback_err:
                print(f"DEBUG CREATE_SUPPLIER: Error attempting Integrity Error rollback: {rollback_err}")
        print(f"DEBUG CREATE_SUPPLIER: Integrity Error: {e}")
        return jsonify({"message": f"Supplier creation failed: Duplicate entry (name or email likely already exists).", "error_type": "IntegrityError"}), 409 
    except Exception as e:
        if conn and trans: 
             try:
                trans.rollback()
                print("DEBUG CREATE_SUPPLIER: Transaction rolled back due to unexpected error.")
             except Exception as rollback_err:
                print(f"DEBUG CREATE_SUPPLIER: Error attempting unexpected exception rollback: {rollback_err}")
        print(f"DEBUG CREATE_SUPPLIER: Caught unexpected exception: {e}")
        return jsonify({"message": f"Supplier creation failed: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn:
             conn.close()
             print("DEBUG CREATE_SUPPLIER: Database connection closed.")
print("DEBUG APP_SETUP: Defined /api/suppliers POST route.")

@app.route('/api/suppliers', methods=['GET'])
@verify_firebase_token # Apply decorator
def list_suppliers():
    print("Received request for GET /api/suppliers")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500
    conn = None 
    try:
        conn = engine.connect()
        query = sqlalchemy.text("SELECT * FROM suppliers ORDER BY name")
        result = conn.execute(query)
        suppliers_list = []
        for row in result:
            supplier_dict = dict(row._mapping)
            for key, value in supplier_dict.items():
                 if isinstance(value, datetime):
                     supplier_dict[key] = value.isoformat()
            suppliers_list.append(supplier_dict)
        print(f"DEBUG LIST_SUPPLIERS: Found {len(suppliers_list)} suppliers.")
        return jsonify(suppliers_list), 200 
    except Exception as e:
        print(f"DEBUG LIST_SUPPLIERS: Caught unexpected exception: {e}")
        return jsonify({"message": f"Error fetching suppliers: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn:
             conn.close()
             print("DEBUG LIST_SUPPLIERS: Database connection closed.")
print("DEBUG APP_SETUP: Defined /api/suppliers GET route.")

@app.route('/api/suppliers/<int:supplier_id>', methods=['GET'])
@verify_firebase_token # Apply decorator
def get_supplier(supplier_id):
    print(f"Received request for GET /api/suppliers/{supplier_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500
    conn = None 
    try:
        conn = engine.connect()
        query = sqlalchemy.text("SELECT * FROM suppliers WHERE id = :supplier_id")
        result = conn.execute(query, {"supplier_id": supplier_id}).fetchone() 
        if result is None:
            print(f"DEBUG GET_SUPPLIER: Supplier with ID {supplier_id} not found.")
            return jsonify({"message": f"Supplier with ID {supplier_id} not found."}), 404 
        supplier_dict = dict(result._mapping) 
        for key, value in supplier_dict.items():
            if isinstance(value, datetime):
                supplier_dict[key] = value.isoformat()
            elif isinstance(value, Decimal):
                 supplier_dict[key] = float(value)
        print(f"DEBUG GET_SUPPLIER: Found supplier with ID: {supplier_id}.")
        return jsonify(supplier_dict), 200 
    except Exception as e:
        print(f"DEBUG GET_SUPPLIER: Caught unexpected exception: {e}")
        return jsonify({"message": f"Error fetching supplier: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn:
             conn.close()
             print(f"DEBUG GET_SUPPLIER: Database connection closed for ID {supplier_id}.")
print("DEBUG APP_SETUP: Defined /api/suppliers/<id> GET route.")

@app.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
@verify_firebase_token # Apply decorator
def update_supplier(supplier_id):
    print(f"Received request for PUT /api/suppliers/{supplier_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500
    conn = None 
    trans = None 
    try:
        supplier_data = request.json
        print(f"DEBUG UPDATE_SUPPLIER: Received data for supplier ID {supplier_id}: {supplier_data}")
        if not supplier_data:
            return jsonify({"message": "No update data provided."}), 400 
        conn = engine.connect()
        trans = conn.begin()
        existing_supplier = conn.execute(
            sqlalchemy.text("SELECT id FROM suppliers WHERE id = :supplier_id"),
            {"supplier_id": supplier_id}
        ).fetchone()
        if not existing_supplier:
            trans.rollback() 
            print(f"DEBUG UPDATE_SUPPLIER: Supplier with ID {supplier_id} not found.")
            return jsonify({"message": f"Supplier with ID {supplier_id} not found."}), 404 
        update_fields = []
        update_params = {"supplier_id": supplier_id, "updated_at": datetime.now(timezone.utc)} 
        allowed_fields = [
            'name', 'email', 'payment_terms', 'address_line1', 'address_line2',
            'city', 'state', 'zip', 'country', 'phone', 'contact_person'
        ]
        for field in allowed_fields:
            if field in supplier_data: 
                update_fields.append(f"{field} = :{field}")
                update_params[field] = supplier_data[field] 
        if not update_fields:
             trans.rollback() 
             print(f"DEBUG UPDATE_SUPPLIER: No valid update fields provided for supplier ID {supplier_id}.")
             return jsonify({"message": "No valid update fields provided."}), 400 
        update_query_text = f"UPDATE suppliers SET {', '.join(update_fields)}, updated_at = :updated_at WHERE id = :supplier_id"
        update_query = sqlalchemy.text(update_query_text)
        conn.execute(update_query, update_params)
        trans.commit() 
        print(f"DEBUG UPDATE_SUPPLIER: Successfully updated supplier with ID: {supplier_id}")
        return jsonify({"message": f"Supplier with ID {supplier_id} updated successfully"}), 200 
    except sqlalchemy.exc.IntegrityError as e:
        if conn and trans and trans.in_transaction():
             trans.rollback()
        print(f"DEBUG UPDATE_SUPPLIER: Integrity Error: {e}")
        return jsonify({"message": f"Supplier update failed: Duplicate entry (name or email likely already exists).", "error_type": "IntegrityError"}), 409 
    except Exception as e:
        if conn and trans and trans.in_transaction():
             trans.rollback()
        print(f"DEBUG UPDATE_SUPPLIER: Caught unexpected exception: {e}")
        return jsonify({"message": f"Supplier update failed: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn:
             conn.close()
             print(f"DEBUG UPDATE_SUPPLIER: Database connection closed for ID {supplier_id}.")
print("DEBUG APP_SETUP: Defined /api/suppliers/<id> PUT route.")

@app.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
@verify_firebase_token # Apply decorator
def delete_supplier(supplier_id):
    print(f"Received request for DELETE /api/suppliers/{supplier_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500
    conn = None 
    trans = None 
    try:
        conn = engine.connect()
        trans = conn.begin()
        delete_supplier_stmt = sqlalchemy.text("DELETE FROM suppliers WHERE id = :supplier_id")
        result = conn.execute(delete_supplier_stmt, {"supplier_id": supplier_id})
        if result.rowcount == 0:
            trans.rollback() 
            print(f"DEBUG DELETE_SUPPLIER: Supplier with ID {supplier_id} not found for deletion.")
            return jsonify({"message": f"Supplier with ID {supplier_id} not found."}), 404 
        trans.commit() 
        print(f"DEBUG DELETE_SUPPLIER: Successfully deleted supplier with ID: {supplier_id}")
        return jsonify({"message": f"Supplier with ID {supplier_id} deleted successfully"}), 200 
    except Exception as e:
        if conn and trans and trans.in_transaction():
             trans.rollback()
        print(f"DEBUG DELETE_SUPPLIER: Caught unexpected exception: {e}")
        return jsonify({"message": f"Supplier deletion failed: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn:
             conn.close()
             print(f"DEBUG DELETE_SUPPLIER: Database connection closed for ID {supplier_id}.")
print("DEBUG APP_SETUP: Defined /api/suppliers/<id> DELETE route.")

# === PRODUCT MAPPING CRUD ROUTES ===
@app.route('/api/products', methods=['POST'])
@verify_firebase_token # Apply decorator
def create_product_mapping():
    print("Received request for POST /api/products")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500
    conn = None 
    trans = None 
    try:
        product_data = request.json
        print(f"DEBUG CREATE_PRODUCT: Received data: {product_data}")
        required_fields = ['sku', 'standard_description']
        for field in required_fields:
            if not product_data or field not in product_data or not product_data[field]:
                print(f"DEBUG CREATE_PRODUCT: Missing required field: {field}")
                return jsonify({"message": f"Missing required field: {field}"}), 400 
        sku = product_data.get('sku')
        standard_description = product_data.get('standard_description')
        conn = engine.connect()
        trans = conn.begin() 
        insert_product_stmt = insert(sqlalchemy.table(
            'products', 
            sqlalchemy.column('sku'),
            sqlalchemy.column('standard_description'),
            sqlalchemy.column('created_at'),
            sqlalchemy.column('updated_at')
        )).values( 
            sku = sku,
            standard_description = standard_description,
            created_at = datetime.now(timezone.utc), 
            updated_at = datetime.now(timezone.utc) 
        ) 
        result = conn.execute(insert_product_stmt.returning(sqlalchemy.column('id')))
        inserted_product_id = result.fetchone()[0] 
        trans.commit() 
        print(f"DEBUG CREATE_PRODUCT: Successfully inserted product mapping with ID: {inserted_product_id}")
        return jsonify({
            "message": "Product mapping created successfully",
            "product_id": inserted_product_id
        }), 201 
    except sqlalchemy.exc.IntegrityError as e:
        if conn and trans: 
             try:
                trans.rollback()
                print("DEBUG CREATE_PRODUCT: Transaction rolled back due to Integrity Error.")
             except Exception as rollback_err:
                print(f"DEBUG CREATE_PRODUCT: Error attempting Integrity Error rollback: {rollback_err}")
        print(f"DEBUG CREATE_PRODUCT: Integrity Error: {e}")
        return jsonify({"message": f"Product mapping creation failed: Duplicate SKU already exists.", "error_type": "IntegrityError"}), 409 
    except Exception as e:
        if conn and trans: 
             try:
                trans.rollback()
                print("DEBUG CREATE_PRODUCT: Transaction rolled back due to unexpected error.")
             except Exception as rollback_err:
                print(f"DEBUG CREATE_PRODUCT: Error attempting unexpected exception rollback: {rollback_err}")
        print(f"DEBUG CREATE_PRODUCT: Caught unexpected exception: {e}")
        return jsonify({"message": f"Product mapping creation failed: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn:
             conn.close()
             print("DEBUG CREATE_PRODUCT: Database connection closed.")
print("DEBUG APP_SETUP: Defined /api/products POST route.")

@app.route('/api/products', methods=['GET'])
@verify_firebase_token # Apply decorator
def list_product_mappings():
    print("Received request for GET /api/products")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500
    conn = None 
    try:
        conn = engine.connect()
        query = sqlalchemy.text("SELECT * FROM products ORDER BY sku")
        result = conn.execute(query)
        product_mappings_list = []
        for row in result:
            product_dict = dict(row._mapping)
            for key, value in product_dict.items():
                 if isinstance(value, datetime):
                     product_dict[key] = value.isoformat()
            product_mappings_list.append(product_dict)
        print(f"DEBUG LIST_PRODUCTS: Found {len(product_mappings_list)} product mappings.")
        return jsonify(product_mappings_list), 200 
    except Exception as e:
        print(f"DEBUG LIST_PRODUCTS: Caught unexpected exception: {e}")
        return jsonify({"message": f"Error fetching product mappings: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn:
             conn.close()
             print("DEBUG LIST_PRODUCTS: Database connection closed.")         
print("DEBUG APP_SETUP: Defined /api/products GET route.")

@app.route('/api/products/<int:product_id>', methods=['GET'])
@verify_firebase_token # Apply decorator
def get_product_mapping(product_id):
    print(f"Received request for GET /api/products/{product_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500
    conn = None 
    try:
        conn = engine.connect()
        query = sqlalchemy.text("SELECT * FROM products WHERE id = :product_id")
        result = conn.execute(query, {"product_id": product_id}).fetchone() 
        if result is None:
            print(f"DEBUG GET_PRODUCT: Product mapping with ID {product_id} not found.")
            return jsonify({"message": f"Product mapping with ID {product_id} not found."}), 404 
        product_dict = dict(result._mapping) 
        for key, value in product_dict.items():
            if isinstance(value, datetime):
                product_dict[key] = value.isoformat()
        print(f"DEBUG GET_PRODUCT: Found product mapping with ID: {product_id}.")
        return jsonify(product_dict), 200 
    except Exception as e:
        print(f"DEBUG GET_PRODUCT: Caught unexpected exception: {e}")
        return jsonify({"message": f"Error fetching product mapping: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn:
             conn.close()
             print(f"DEBUG GET_PRODUCT: Database connection closed for ID {product_id}.")
print("DEBUG APP_SETUP: Defined /api/products/<id> GET route.")

@app.route('/api/products/<int:product_id>', methods=['PUT'])
@verify_firebase_token # Apply decorator
def update_product_mapping(product_id):
    print(f"Received request for PUT /api/products/{product_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500
    conn = None 
    trans = None 
    try:
        product_data = request.json
        print(f"DEBUG UPDATE_PRODUCT: Received data for product ID {product_id}: {product_data}")
        if not product_data:
            return jsonify({"message": "No update data provided."}), 400 
        conn = engine.connect()
        trans = conn.begin()
        existing_product = conn.execute(
            sqlalchemy.text("SELECT id FROM products WHERE id = :product_id"),
            {"product_id": product_id}
        ).fetchone()
        if not existing_product:
            trans.rollback() 
            print(f"DEBUG UPDATE_PRODUCT: Product mapping with ID {product_id} not found.")
            return jsonify({"message": f"Product mapping with ID {product_id} not found."}), 404 
        update_fields = []
        update_params = {"product_id": product_id, "updated_at": datetime.now(timezone.utc)} 
        allowed_fields = ['sku', 'standard_description']
        for field in allowed_fields:
            if field in product_data: 
                update_fields.append(f"{field} = :{field}")
                update_params[field] = product_data[field]
        if not update_fields:
             trans.rollback() 
             print(f"DEBUG UPDATE_PRODUCT: No valid update fields provided for product ID {product_id}.")
             return jsonify({"message": "No valid update fields provided."}), 400 
        update_query_text = f"UPDATE products SET {', '.join(update_fields)}, updated_at = :updated_at WHERE id = :product_id"
        update_query = sqlalchemy.text(update_query_text)
        conn.execute(update_query, update_params)
        trans.commit() 
        print(f"DEBUG UPDATE_PRODUCT: Successfully updated product mapping with ID: {product_id}")
        return jsonify({"message": f"Product mapping with ID {product_id} updated successfully"}), 200 
    except sqlalchemy.exc.IntegrityError as e:
        if conn and trans:
             try:
                trans.rollback()
                print("DEBUG UPDATE_PRODUCT: Transaction rolled back due to Integrity Error.")
             except Exception as rollback_err:
                print(f"DEBUG UPDATE_PRODUCT: Error attempting Integrity Error rollback: {rollback_err}")
        print(f"DEBUG UPDATE_PRODUCT: Integrity Error: {e}")
        return jsonify({"message": f"Product mapping update failed: Duplicate SKU already exists.", "error_type": "IntegrityError"}), 409 
    except Exception as e:
        if conn and trans:
             try:
                trans.rollback()
                print(f"DEBUG UPDATE_PRODUCT: Transaction rolled back due to unexpected error: {e}")
             except Exception as rollback_err:
                print(f"DEBUG UPDATE_PRODUCT: Error attempting unexpected exception rollback: {rollback_err}")
        print(f"DEBUG UPDATE_PRODUCT: Caught unexpected exception: {e}")
        return jsonify({"message": f"Product mapping update failed: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn:
             conn.close()
             print(f"DEBUG UPDATE_PRODUCT: Database connection closed for ID {product_id}.")
print("DEBUG APP_SETUP: Defined /api/products/<id> PUT route.")

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@verify_firebase_token # Apply decorator
def delete_product_mapping(product_id):
    print(f"Received request for DELETE /api/products/{product_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500
    conn = None 
    trans = None 
    try:
        conn = engine.connect()
        trans = conn.begin()
        delete_product_stmt = sqlalchemy.text("DELETE FROM products WHERE id = :product_id")
        result = conn.execute(delete_product_stmt, {"product_id": product_id})
        if result.rowcount == 0:
            trans.rollback() 
            print(f"DEBUG DELETE_PRODUCT: Product mapping with ID {product_id} not found for deletion.")
            return jsonify({"message": f"Product mapping with ID {product_id} not found."}), 404 
        trans.commit() 
        print(f"DEBUG DELETE_PRODUCT: Successfully deleted product mapping with ID: {product_id}")
        return jsonify({"message": f"Product mapping with ID {product_id} deleted successfully"}), 200 
    except Exception as e:
        if conn and trans:
             try:
                trans.rollback()
                print(f"DEBUG DELETE_PRODUCT: Transaction rolled back due to unexpected error: {e}")
             except Exception as rollback_err:
                print(f"DEBUG DELETE_PRODUCT: Error attempting unexpected exception rollback: {rollback_err}")
        print(f"DEBUG DELETE_PRODUCT: Caught unexpected exception: {e}")
        return jsonify({"message": f"Product mapping deletion failed: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn:
             conn.close()
             print(f"DEBUG DELETE_PRODUCT: Database connection closed for ID {product_id}.")
print("DEBUG APP_SETUP: Defined /api/products/<id> DELETE route.")

@app.route('/api/lookup/description/<path:sku_value>', methods=['GET'])
@verify_firebase_token # Apply decorator
def get_description_for_sku(sku_value):
    """Looks up the best description for a given SKU/OptionPN."""
    if not sku_value:
        return jsonify({"description": None}), 400 
    db_conn = None
    description = None
    print(f"DEBUG LOOKUP_DESC: Received request for SKU: {sku_value}")
    try:
        if engine is None: return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()
        desc_query_1 = text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :sku")
        result_1 = db_conn.execute(desc_query_1, {"sku": sku_value}).scalar_one_or_none()
        if result_1:
            description = result_1
            print(f"DEBUG LOOKUP_DESC: Found description in hpe_description_mappings for {sku_value}.")
        else:
            desc_query_2 = text("SELECT standard_description FROM products WHERE sku = :sku")
            result_2 = db_conn.execute(desc_query_2, {"sku": sku_value}).scalar_one_or_none()
            if result_2:
                description = result_2
                print(f"DEBUG LOOKUP_DESC: Found description in products for {sku_value}.")
            else:
                 part_map_query = text("SELECT option_pn FROM hpe_part_mappings WHERE sku = :sku")
                 option_pn_from_map = db_conn.execute(part_map_query, {"sku": sku_value}).scalar_one_or_none()
                 if option_pn_from_map:
                     print(f"DEBUG LOOKUP_DESC: Input SKU {sku_value} mapped to OptionPN {option_pn_from_map}. Looking up description...")
                     desc_query_3 = text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn")
                     result_3 = db_conn.execute(desc_query_3, {"option_pn": option_pn_from_map}).scalar_one_or_none()
                     if result_3:
                         description = result_3
                         print(f"DEBUG LOOKUP_DESC: Found description in hpe_description_mappings for mapped OptionPN {option_pn_from_map}.")
        print(f"DEBUG LOOKUP_DESC: Final description for {sku_value}: {description}")
        return jsonify({"description": description}), 200
    except Exception as e:
        print(f"ERROR LOOKUP_DESC: Error looking up description for SKU {sku_value}: {e}")
        return jsonify({"error": "Failed to lookup description", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print(f"DEBUG LOOKUP_DESC: DB connection closed for SKU {sku_value}.")
print("DEBUG APP_SETUP: Defined /api/lookup/description/<sku> GET route.")

# app.py

# Ensure these imports are at the top of your app.py if not already present
from flask import Flask, jsonify, request, g # Existing
from sqlalchemy import text # Existing
from decimal import Decimal # Existing
from datetime import datetime, timezone # Existing
import traceback # Existing
import os # Existing

# Assuming these are your existing service module imports
import document_generator
import shipping_service
import email_service
# and other necessary imports like sqlalchemy, GcpSqlConnector, requests, firebase_admin, storage, etc.

# Assuming 'engine', 'COMPANY_LOGO_GCS_URI', 'SHIP_FROM_...' variables,
# 'bc_api_base_url_v2', 'bc_shipped_status_id', 'bc_processing_status_id' (and potentially a BC_PARTIALLY_SHIPPED_STATUS_ID),
# 'storage_client', 'GCS_BUCKET_NAME' are defined globally or accessible.
# Also, helper functions like convert_row_to_dict, make_json_safe,
# _get_bc_shipping_address_id, get_hpe_mapping_with_fallback are defined.
# And the verify_firebase_token decorator.


# === PROCESS ORDER ROUTE (Comprehensive Update for Multi-Supplier, Packing Slip, BC Status, and SQL Fix) ===
@app.route('/api/orders/<int:order_id>/process', methods=['POST'])
@verify_firebase_token
def process_order(order_id):
    print(f"DEBUG PROCESS_ORDER_MULTI: Received request to process order ID: {order_id}")
    db_conn = None
    transaction = None
    processed_pos_info = []

    try:
        payload = request.get_json()
        if not payload or 'assignments' not in payload or not isinstance(payload['assignments'], list):
            return jsonify({"error": "Invalid or missing 'assignments' array in payload"}), 400

        assignments = payload['assignments']
        if not assignments:
            return jsonify({"error": "Assignments array cannot be empty if processing is intended."}), 400

        if engine is None:
            print("ERROR PROCESS_ORDER_MULTI: Database engine not available.")
            return jsonify({"error": "Database engine not available."}), 500

        db_conn = engine.connect()
        transaction = db_conn.begin()
        print("DEBUG PROCESS_ORDER_MULTI: DB connection and transaction started for all assignments.")

        order_record = db_conn.execute(text("SELECT * FROM orders WHERE id = :id"), {"id": order_id}).fetchone()
        if not order_record:
            if transaction and transaction.is_active: transaction.rollback()
            return jsonify({"error": f"Order with ID {order_id} not found"}), 404
        order_data_dict = convert_row_to_dict(order_record)

        order_status_from_db = order_data_dict.get('status')
        terminal_statuses = ['processed', 'completed offline']
        if order_status_from_db and order_status_from_db.lower() in terminal_statuses:
            if transaction and transaction.is_active: transaction.rollback()
            return jsonify({"error": f"Order {order_id} status is '{order_status_from_db}' and cannot be reprocessed."}), 400

        local_order_line_items_records = db_conn.execute(
            text("""
                SELECT id AS line_item_id, bigcommerce_line_item_id, sku AS original_sku,
                       name AS line_item_name, quantity
                FROM order_line_items WHERE order_id = :order_id_param ORDER BY id
            """),
            {"order_id_param": order_id}
        ).fetchall()
        local_order_line_items_list = [convert_row_to_dict(row) for row in local_order_line_items_records]
        all_original_order_line_item_db_ids = {item['line_item_id'] for item in local_order_line_items_list}
        processed_original_order_line_item_db_ids_this_batch = set()
        is_multi_po_scenario_for_po_pdf = len(assignments) > 1


        starting_po_sequence = 200001
        max_po_query = text("""
            SELECT MAX(CAST(numeric_po_number AS INTEGER))
            FROM (
                SELECT po_number AS numeric_po_number
                FROM purchase_orders
                WHERE CAST(po_number AS TEXT) ~ '^[0-9]+$'
            ) AS numeric_pos
        """)
        max_po_value_from_db = db_conn.execute(max_po_query).scalar_one_or_none()
        next_sequence_num = starting_po_sequence
        if max_po_value_from_db is not None:
            try:
                current_max_po = int(max_po_value_from_db)
                next_sequence_num = max(starting_po_sequence, current_max_po + 1)
            except ValueError:
                print(f"WARN PROCESS_ORDER_MULTI: Could not parse max PO number '{max_po_value_from_db}'. Defaulting.")

        ship_from_address = { # Define ship_from_address once if it's constant
            'name': SHIP_FROM_NAME, 'contact_person': SHIP_FROM_CONTACT,
            'street_1': SHIP_FROM_STREET1, 'street_2': SHIP_FROM_STREET2,
            'city': SHIP_FROM_CITY, 'state': SHIP_FROM_STATE, 'zip': SHIP_FROM_ZIP,
            'country': SHIP_FROM_COUNTRY, 'phone': SHIP_FROM_PHONE
        }
        if not all([SHIP_FROM_STREET1, SHIP_FROM_CITY, SHIP_FROM_STATE, SHIP_FROM_ZIP, SHIP_FROM_PHONE]):
            # This is a critical setup issue, should probably raise an error or return 500
            # For now, it will skip label generation within the loop.
            print(f"CRITICAL WARN PROCESS_ORDER_MULTI: Global SHIP_FROM address details incomplete. Label generation will be skipped for all POs.")


        for assignment_data in assignments:
            supplier_id = assignment_data.get('supplier_id')
            po_line_items_input = assignment_data.get('po_line_items')
            payment_instructions_from_frontend = assignment_data.get('payment_instructions', "")
            total_shipment_weight_lbs_str = assignment_data.get('total_shipment_weight_lbs')
            shipment_method_for_po = assignment_data.get('shipment_method')

            if not supplier_id or po_line_items_input is None:
                raise ValueError(f"Missing supplier_id or po_line_items in an assignment: {assignment_data}")
            if not isinstance(po_line_items_input, list):
                 raise ValueError(f"po_line_items for supplier {supplier_id} is not a list.")
            if not po_line_items_input: # Empty list
                 print(f"WARN PROCESS_ORDER_MULTI: PO for supplier {supplier_id} has no line items. Creating PO without items.")


            supplier_record = db_conn.execute(text("SELECT * FROM suppliers WHERE id = :id"), {"id": supplier_id}).fetchone()
            if not supplier_record:
                raise ValueError(f"Supplier with ID {supplier_id} not found.")
            supplier_data_dict = convert_row_to_dict(supplier_record)

            generated_po_number = str(next_sequence_num)
            next_sequence_num += 1
            print(f"DEBUG PROCESS_ORDER_MULTI: PO {generated_po_number} for supplier {supplier_id}")

            current_utc_datetime = datetime.now(timezone.utc)
            po_total_amount = sum(Decimal(str(item.get('quantity', 0))) * Decimal(str(item.get('unit_cost', '0'))) for item in po_line_items_input)

            insert_po_sql = text("""
                INSERT INTO purchase_orders (po_number, order_id, supplier_id, po_date, payment_instructions, status, total_amount, created_at, updated_at)
                VALUES (:po_number, :order_id, :supplier_id, :po_date, :payment_instructions, :status, :total_amount, :now, :now) RETURNING id
            """)
            po_params = {
                "po_number": generated_po_number, "order_id": order_id, "supplier_id": supplier_id,
                "po_date": current_utc_datetime, "payment_instructions": payment_instructions_from_frontend,
                "status": "New", "total_amount": po_total_amount, "now": current_utc_datetime
            }
            new_purchase_order_id = db_conn.execute(insert_po_sql, po_params).scalar_one()
            print(f"DEBUG PROCESS_ORDER_MULTI: Inserted PO DB ID: {new_purchase_order_id}")

            insert_po_item_sql = text("""
                INSERT INTO po_line_items (purchase_order_id, original_order_line_item_id, sku, description, quantity, unit_cost, condition, created_at, updated_at)
                VALUES (:po_id, :orig_id, :actual_sku_for_db, :desc, :qty, :cost, :cond, :now, :now)
            """)
            po_items_for_pdf_and_qb_this_po = []
            ids_in_this_po = set()

            for item_input in po_line_items_input:
                original_oli_id = item_input.get("original_order_line_item_id")
                if original_oli_id is None:
                    raise ValueError(f"Missing 'original_order_line_item_id' in po_line_items for PO {generated_po_number}")
                ids_in_this_po.add(original_oli_id)
                processed_original_order_line_item_db_ids_this_batch.add(original_oli_id)
                po_item_params = {
                    "po_id": new_purchase_order_id, "orig_id": original_oli_id,
                    "actual_sku_for_db": item_input.get('sku'), "desc": item_input.get('description'),
                    "qty": int(item_input.get("quantity", 0)), "cost": Decimal(str(item_input.get("unit_cost", '0'))),
                    "cond": item_input.get("condition", "New"), "now": current_utc_datetime
                }
                db_conn.execute(insert_po_item_sql, po_item_params)
                po_items_for_pdf_and_qb_this_po.append({
                    "sku": item_input.get('sku'), "description": item_input.get('description'),
                    "quantity": int(item_input.get("quantity",0)),
                    "unit_cost": Decimal(str(item_input.get("unit_cost", '0'))),
                    "condition": item_input.get("condition", "New")
                })
            print(f"DEBUG PROCESS_ORDER_MULTI: Inserted {len(po_items_for_pdf_and_qb_this_po)} lines for PO {generated_po_number}.")

            po_pdf_bytes, packing_slip_pdf_bytes, label_pdf_bytes, tracking_number_this_po = None, None, None, None
            po_pdf_gcs_uri_this_po, packing_slip_gcs_uri_this_po, label_gcs_uri_this_po = None, None, None

            if document_generator:
                po_pdf_data_args = {
                    "supplier_data": supplier_data_dict, "po_number": generated_po_number,
                    "po_date": current_utc_datetime, "po_items": po_items_for_pdf_and_qb_this_po,
                    "payment_terms": supplier_data_dict.get('payment_terms'),
                    "payment_instructions": payment_instructions_from_frontend,
                    "order_data": order_data_dict, "logo_gcs_uri": COMPANY_LOGO_GCS_URI,
                    "is_partial_fulfillment": is_multi_po_scenario_for_po_pdf
                }
                po_pdf_bytes = document_generator.generate_purchase_order_pdf(**po_pdf_data_args)

                prepared_items_in_this_shipment = []
                for po_item_detail in po_items_for_pdf_and_qb_this_po:
                    prepared_items_in_this_shipment.append({
                        'sku': po_item_detail.get('sku'), 'name': po_item_detail.get('description'),
                        'quantity': po_item_detail.get('quantity')
                    })
                prepared_items_shipping_separately = []
                for orig_item_from_bc_order in local_order_line_items_list:
                    if orig_item_from_bc_order.get('line_item_id') not in ids_in_this_po:
                        sep_sku_display = orig_item_from_bc_order.get('original_sku')
                        sep_desc_display = orig_item_from_bc_order.get('line_item_name', 'N/A')
                        hpe_option_pn_sep, _, _ = get_hpe_mapping_with_fallback(sep_sku_display, db_conn)
                        if hpe_option_pn_sep:
                            desc_query_sep = text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn")
                            custom_desc_sep = db_conn.execute(desc_query_sep, {"option_pn": hpe_option_pn_sep}).scalar_one_or_none()
                            if custom_desc_sep: sep_desc_display = custom_desc_sep
                            sep_sku_display = hpe_option_pn_sep
                        prepared_items_shipping_separately.append({
                            'sku': sep_sku_display, 'name': sep_desc_display,
                            'quantity': orig_item_from_bc_order.get('quantity')
                        })
                if po_pdf_bytes: # Only generate packing slip if PO PDF was made
                     packing_slip_data_args = {
                        "order_data": order_data_dict, # This contains customer address details including company
                        "items_in_this_shipment": prepared_items_in_this_shipment,
                        "items_shipping_separately": prepared_items_shipping_separately,
                        "logo_gcs_uri": COMPANY_LOGO_GCS_URI,
                        # "po_number_for_slip": generated_po_number # <--- REMOVE THIS LINE
                     }
                     packing_slip_pdf_bytes = document_generator.generate_packing_slip_pdf(**packing_slip_data_args)

            print(f"DEBUG PROCESS_ORDER_MULTI: PO {generated_po_number} - Evaluating label generation. Weight Str: '{total_shipment_weight_lbs_str}', Method: '{shipment_method_for_po}', Ship Service: {bool(shipping_service)}")
            if shipping_service and total_shipment_weight_lbs_str and shipment_method_for_po:
                try:
                    current_po_weight = float(total_shipment_weight_lbs_str)
                    if current_po_weight <= 0:
                        print(f"WARN PROCESS_ORDER_MULTI: PO {generated_po_number} - Invalid weight ({current_po_weight}). Skipping label.")
                    elif not all([SHIP_FROM_STREET1, SHIP_FROM_CITY, SHIP_FROM_STATE, SHIP_FROM_ZIP, SHIP_FROM_PHONE]): # Check critical ship_from fields
                         print(f"WARN PROCESS_ORDER_MULTI: PO {generated_po_number} - Critical SHIP_FROM address details missing. Skipping label generation.")
                    else:
                        print(f"DEBUG PROCESS_ORDER_MULTI: PO {generated_po_number} - CALLING generate_ups_label with weight: {current_po_weight}, method: {shipment_method_for_po}")
                        label_pdf_bytes, tracking_number_this_po = shipping_service.generate_ups_label(
                            order_data=order_data_dict, ship_from_address=ship_from_address,
                            total_weight_lbs=current_po_weight, customer_shipping_method_name=shipment_method_for_po
                        )
                        if not (label_pdf_bytes and tracking_number_this_po):
                            print(f"WARN PROCESS_ORDER_MULTI: UPS label gen failed or no data for PO {generated_po_number}. Tracking: {tracking_number_this_po}, Label Bytes Present: {bool(label_pdf_bytes)}")
                        else:
                            print(f"DEBUG PROCESS_ORDER_MULTI: UPS Label for PO {generated_po_number}. Tracking: {tracking_number_this_po}, Label Bytes: {len(label_pdf_bytes) if label_pdf_bytes else 0}")
                            insert_shipment_sql = text("""
                                INSERT INTO shipments (purchase_order_id, tracking_number, shipping_method_name, weight_lbs, created_at, updated_at)
                                VALUES (:po_id, :track_num, :method, :weight, :now, :now) RETURNING id
                            """)
                            shipment_params = {
                                "po_id": new_purchase_order_id, "track_num": tracking_number_this_po,
                                "method": shipment_method_for_po, "weight": current_po_weight, "now": current_utc_datetime
                            }
                            db_conn.execute(insert_shipment_sql, shipment_params).scalar_one()
                except ValueError as ve: # Handles float conversion error for weight
                     print(f"WARN PROCESS_ORDER_MULTI: Invalid weight format for PO {generated_po_number}: '{total_shipment_weight_lbs_str}'. Error: {ve}. Skipping label.")
                except Exception as label_e: # Catch other errors from label generation
                    print(f"ERROR PROCESS_ORDER_MULTI: UPS Label gen error for PO {generated_po_number}: {label_e}")
                    traceback.print_exc()
            else:
                print(f"DEBUG PROCESS_ORDER_MULTI: PO {generated_po_number} - SKIPPING label generation. Weight: '{total_shipment_weight_lbs_str}', Method: '{shipment_method_for_po}', Ship Service OK: {bool(shipping_service)}")


            if storage_client and GCS_BUCKET_NAME:
                ts_suffix = current_utc_datetime.strftime("%Y%m%d%H%M%S")
                common_prefix = f"processed_orders/order_{order_data_dict['bigcommerce_order_id']}_PO_{generated_po_number}"
                bucket = storage_client.bucket(GCS_BUCKET_NAME)
                if po_pdf_bytes:
                    po_blob_name = f"{common_prefix}/po_{generated_po_number}_{ts_suffix}.pdf"
                    bucket.blob(po_blob_name).upload_from_string(po_pdf_bytes, content_type='application/pdf')
                    po_pdf_gcs_uri_this_po = f"gs://{GCS_BUCKET_NAME}/{po_blob_name}"
                    db_conn.execute(text("UPDATE purchase_orders SET po_pdf_gcs_path = :path, updated_at = :now WHERE id = :id"),
                                    {"path": po_pdf_gcs_uri_this_po, "now": current_utc_datetime, "id": new_purchase_order_id})
                if packing_slip_pdf_bytes:
                    ps_blob_name = f"{common_prefix}/ps_{generated_po_number}_{ts_suffix}.pdf"
                    bucket.blob(ps_blob_name).upload_from_string(packing_slip_pdf_bytes, content_type='application/pdf')
                    packing_slip_gcs_uri_this_po = f"gs://{GCS_BUCKET_NAME}/{ps_blob_name}"
                    if tracking_number_this_po:
                         db_conn.execute(text("UPDATE shipments SET packing_slip_gcs_path = :path, updated_at = :now WHERE purchase_order_id = :po_id AND tracking_number = :track_num"),
                                {"path": packing_slip_gcs_uri_this_po, "now": current_utc_datetime, "po_id": new_purchase_order_id, "track_num": tracking_number_this_po})
                if label_pdf_bytes and tracking_number_this_po:
                    label_blob_name = f"{common_prefix}/label_{tracking_number_this_po}_{ts_suffix}.pdf"
                    bucket.blob(label_blob_name).upload_from_string(label_pdf_bytes, content_type='application/pdf')
                    label_gcs_uri_this_po = f"gs://{GCS_BUCKET_NAME}/{label_blob_name}"
                    db_conn.execute(text("UPDATE shipments SET label_gcs_path = :path, updated_at = :now WHERE purchase_order_id = :po_id AND tracking_number = :track_num"),
                                {"path": label_gcs_uri_this_po, "now": current_utc_datetime, "po_id": new_purchase_order_id, "track_num": tracking_number_this_po})

            attachments_for_this_email = []
            if po_pdf_bytes: attachments_for_this_email.append({"filename": f"PO_{generated_po_number}.pdf", "content": po_pdf_bytes, "content_type": "application/pdf"})
            if packing_slip_pdf_bytes: attachments_for_this_email.append({"filename": f"PackingSlip_{generated_po_number}.pdf", "content": packing_slip_pdf_bytes, "content_type": "application/pdf"})
            if label_pdf_bytes: attachments_for_this_email.append({"filename": f"ShippingLabel_{tracking_number_this_po}.pdf", "content": label_pdf_bytes, "content_type": "application/pdf"})
            else: print(f"DEBUG PROCESS_ORDER_MULTI: PO {generated_po_number} - No label_pdf_bytes to attach for email.")


            if email_service and supplier_data_dict.get('email') and attachments_for_this_email:
                supplier_email_success = email_service.send_po_email(
                    supplier_email=supplier_data_dict['email'], po_number=generated_po_number, attachments=attachments_for_this_email
                )
                if supplier_email_success:
                    print(f"DEBUG PROCESS_ORDER_MULTI: Email sent to supplier for PO {generated_po_number}.")
                    db_conn.execute(text("UPDATE purchase_orders SET status = :status, updated_at = :now WHERE id = :po_id"),
                                    {"status": "SENT_TO_SUPPLIER", "now": datetime.now(timezone.utc), "po_id": new_purchase_order_id})
                else: print(f"ERROR PROCESS_ORDER_MULTI: Email to supplier failed for PO {generated_po_number}.")
            elif not attachments_for_this_email:
                 print(f"WARN PROCESS_ORDER_MULTI: No attachments (PO, PS, Label) available for PO {generated_po_number}, skipping supplier email.")
            else: print(f"WARN PROCESS_ORDER_MULTI: Skipping supplier email for PO {generated_po_number}.")

            if email_service:
                 qb_po_data = {
                    "supplier_name": supplier_data_dict.get('name'), "po_number": generated_po_number,
                    "po_date": current_utc_datetime,
                    "shipping_method": shipment_method_for_po or order_data_dict.get('customer_shipping_method', "N/A"),
                    "payment_instructions_for_po": payment_instructions_from_frontend,
                    "fulfillment_order_id": order_data_dict.get('bigcommerce_order_id'),
                    "po_line_items": po_items_for_pdf_and_qb_this_po, "expected_delivery_date": None }
                 email_service.send_quickbooks_data_email(qb_po_data)

            # --- Create Shipment in BigCommerce (does NOT set final order status) ---
            if shipping_service and bc_api_base_url_v2 and tracking_number_this_po: # Only if tracking was generated
                bc_order_id_to_update = order_data_dict.get('bigcommerce_order_id')
                bc_order_address_id = _get_bc_shipping_address_id(bc_order_id_to_update)
                bc_line_items_for_this_shipment_api = []
                # ids_in_this_po contains original_order_line_item_id (DB ID) for items in current PO
                for orig_item_detail in local_order_line_items_list:
                    if orig_item_detail.get('line_item_id') in ids_in_this_po:
                        current_po_item_input_for_bc_qty = next(
                            (pi for pi in po_line_items_input if pi.get("original_order_line_item_id") == orig_item_detail.get('line_item_id')), None )
                        if current_po_item_input_for_bc_qty and orig_item_detail.get('bigcommerce_line_item_id'):
                             bc_line_items_for_this_shipment_api.append({
                                "order_product_id": orig_item_detail.get('bigcommerce_line_item_id'),
                                "quantity": current_po_item_input_for_bc_qty.get('quantity')
                             })
                if bc_order_id_to_update and bc_order_address_id is not None and bc_line_items_for_this_shipment_api:
                    print(f"DEBUG PROCESS_ORDER_MULTI: Creating BC Shipment for PO {generated_po_number}, Tracking: {tracking_number_this_po}")
                    shipment_created_successfully = shipping_service.create_bigcommerce_shipment(
                        bigcommerce_order_id=bc_order_id_to_update,
                        tracking_number=tracking_number_this_po,
                        shipping_method_name=shipment_method_for_po or order_data_dict.get('customer_shipping_method'),
                        line_items_in_shipment=bc_line_items_for_this_shipment_api,
                        order_address_id=bc_order_address_id
                    )
                    if not shipment_created_successfully:
                        print(f"ERROR PROCESS_ORDER_MULTI: Failed to create shipment in BigCommerce for PO {generated_po_number}")
                else:
                    print(f"WARN PROCESS_ORDER_MULTI: Missing data for BC shipment for PO {generated_po_number}. BC Order ID: {bc_order_id_to_update}, BC Address ID: {bc_order_address_id}, Items for BC API: {len(bc_line_items_for_this_shipment_api)}")
            elif tracking_number_this_po: # If tracking exists but service not configured
                print(f"WARN PROCESS_ORDER_MULTI: Skipping BC shipment creation for PO {generated_po_number} (shipping_service or config missing, but tracking exists).")

            processed_pos_info.append({
                "po_number": generated_po_number, "supplier_id": supplier_id,
                "tracking_number": tracking_number_this_po,
                "po_pdf_gcs_uri": po_pdf_gcs_uri_this_po,
                "packing_slip_gcs_uri": packing_slip_gcs_uri_this_po,
                "label_gcs_uri": label_gcs_uri_this_po
            })
        # --- End of loop through assignments ---

        is_last_shipment_for_order = False
        if all_original_order_line_item_db_ids.issubset(processed_original_order_line_item_db_ids_this_batch):
            is_last_shipment_for_order = True
            print(f"DEBUG PROCESS_ORDER_MULTI: All original items for order {order_id} covered by this processing batch.")
        else:
            remaining_items = all_original_order_line_item_db_ids - processed_original_order_line_item_db_ids_this_batch
            print(f"DEBUG PROCESS_ORDER_MULTI: Order {order_id} has {len(remaining_items)} original item ID(s) not in this batch: {remaining_items}. Not setting final BC 'Shipped' status yet.")

        if is_last_shipment_for_order:
            # Only set final "Shipped" status in BigCommerce if all items are covered.
            # Requires bc_shipped_status_id to be your final "Shipped" or "Completed" status ID.
            if shipping_service and bc_api_base_url_v2 and bc_shipped_status_id:
                bc_order_id_to_update = order_data_dict.get('bigcommerce_order_id')
                print(f"DEBUG PROCESS_ORDER_MULTI: Attempting to set final 'Shipped' status ({bc_shipped_status_id}) for BC Order {bc_order_id_to_update}.")
                status_updated = shipping_service.set_bigcommerce_order_status(
                    bigcommerce_order_id=bc_order_id_to_update,
                    status_id=int(bc_shipped_status_id)
                )
                if status_updated: print(f"INFO PROCESS_ORDER_MULTI: BC Order {bc_order_id_to_update} final status updated to {bc_shipped_status_id}.")
                else: print(f"ERROR PROCESS_ORDER_MULTI: Failed to set final 'Shipped' status for BC Order {bc_order_id_to_update}.")
            else:
                print(f"WARN PROCESS_ORDER_MULTI: Cannot set final BC 'Shipped' status for order {order_id} due to missing service or config.")
        else:
            # Optionally, if not the last shipment and you want to explicitly set "Partially Shipped"
            # and have a BC_PARTIALLY_SHIPPED_STATUS_ID defined:
            # if shipping_service and bc_api_base_url_v2 and os.getenv("BC_PARTIALLY_SHIPPED_STATUS_ID"):
            #     partially_shipped_id = int(os.getenv("BC_PARTIALLY_SHIPPED_STATUS_ID"))
            #     bc_order_id_to_update = order_data_dict.get('bigcommerce_order_id')
            #     print(f"DEBUG PROCESS_ORDER_MULTI: Attempting to set 'Partially Shipped' status ({partially_shipped_id}) for BC Order {bc_order_id_to_update}.")
            #     shipping_service.set_bigcommerce_order_status(
            #         bigcommerce_order_id=bc_order_id_to_update,
            #         status_id=partially_shipped_id
            #     ) # Error handling for this call can be added
            pass


        final_local_status_for_order_table = "Processed"
        db_conn.execute(text("UPDATE orders SET status = :status, updated_at = :now WHERE id = :order_id"),
                        {"status": final_local_status_for_order_table, "now": datetime.now(timezone.utc), "order_id": order_id})
        print(f"DEBUG PROCESS_ORDER_MULTI: Updated local 'orders' table {order_id} status to '{final_local_status_for_order_table}'.")

        transaction.commit()
        print(f"DEBUG PROCESS_ORDER_MULTI: Transaction committed for ALL assignments for order {order_id}.")
        
        return jsonify({
            "message": f"Order {order_id} (BC Order {order_data_dict.get('bigcommerce_order_id')}) processed. Generated {len(processed_pos_info)} PO(s).",
            "order_id": order_id,
            "processed_purchase_orders": make_json_safe(processed_pos_info)
        }), 201

    except ValueError as ve:
        if transaction and transaction.is_active: transaction.rollback()
        print(f"ERROR PROCESS_ORDER_MULTI: Validation Error: {ve}"); traceback.print_exc()
        return jsonify({"error": "Processing failed due to invalid data or state.", "details": str(ve)}), 400
    except ModuleNotFoundError as me: 
         if transaction and transaction.is_active: transaction.rollback()
         print(f"ERROR PROCESS_ORDER_MULTI: Missing Module Error: {me}"); traceback.print_exc()
         return jsonify({"error": "Processing failed due to missing internal module.", "details": str(me)}), 500
    except sqlalchemy.exc.SQLAlchemyError as db_e: 
        if transaction and transaction.is_active: transaction.rollback()
        print(f"ERROR PROCESS_ORDER_MULTI: Database Error: {db_e}"); traceback.print_exc()
        return jsonify({"error": "Processing failed due to a database error.", "details": str(db_e)}), 500
    except Exception as e: 
        if transaction and transaction.is_active:
             try: transaction.rollback()
             except Exception as rb_e: print(f"ERROR PROCESS_ORDER_MULTI: Error during transaction rollback: {rb_e}")
        print(f"ERROR PROCESS_ORDER_MULTI: Unhandled Exception: {e}"); traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred during order processing.", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print(f"DEBUG PROCESS_ORDER_MULTI: Database connection closed for order {order_id}.")

# NEW: Endpoint for Cloud Scheduler (no Firebase token verification)
@app.route('/api/tasks/scheduler/trigger-iif-for-today', methods=['POST'])
def scheduler_trigger_iif_for_today():
    """
    Triggers IIF generation for today's POs, called by Cloud Scheduler.
    Protected by checking a specific header if configured in Cloud Scheduler.
    """
    # Optional: Add a simple secret header check for basic protection
    # In Cloud Scheduler, add a header like 'X-CloudScheduler-Secret: YOUR_SECRET_VALUE'
    # scheduler_secret = request.headers.get('X-CloudScheduler-Secret')
    # expected_secret = os.getenv("SCHEDULER_SECRET")
    # if not expected_secret or scheduler_secret != expected_secret:
    #     print("WARN APP (SCHEDULER_IIF_TODAY): Missing or invalid scheduler secret header.")
    #     return jsonify({"error": "Forbidden"}), 403

    print("INFO APP (SCHEDULER_IIF_TODAY): Received request to trigger IIF for today from scheduler.")

    if iif_generator is None:
        print("ERROR APP (SCHEDULER_IIF_TODAY): iif_generator module not loaded.")
        return jsonify({"error": "IIF generation module not available."}), 500
    if engine is None:
        print("ERROR APP (SCHEDULER_IIF_TODAY): Database engine not initialized.")
        return jsonify({"error": "Database engine not available."}), 500

    try:
        print("INFO APP (SCHEDULER_IIF_TODAY): Calling iif_generator.create_and_email_iif_for_today...")
        success, _ = iif_generator.create_and_email_iif_for_today(engine)

        if success:
            print("INFO APP (SCHEDULER_IIF_TODAY): IIF for today task completed.")
            return jsonify({"message": "IIF generation task for today's POs triggered."}), 200
        else:
            print("ERROR APP (SCHEDULER_IIF_TODAY): IIF generation for today failed.")
            return jsonify({"error": "IIF generation for today failed in generator script."}), 500

    except Exception as e:
        print(f"ERROR APP (SCHEDULER_IIF_TODAY): Error: {e}")
        traceback.print_exc()
        return jsonify({"error": "An error occurred.", "details": str(e)}), 500

# NEW ROUTE FOR TODAY'S IIF
@app.route('/api/tasks/trigger-iif-for-today', methods=['POST'])
@verify_firebase_token
def user_trigger_iif_for_today():
    # (Keep the body of your existing trigger_iif_for_today function here)
    # Or, better, have this function call a common internal function that scheduler_trigger_iif_for_today also calls.

    print("INFO APP (USER_IIF_TODAY): Received request to trigger IIF for today by user.")
    if iif_generator is None: # ... (similar checks and call)
        return jsonify({"error": "IIF generation module not available."}), 500
    if engine is None:
        return jsonify({"error": "Database engine not available."}), 500
    try:
        success, _ = iif_generator.create_and_email_iif_for_today(engine)
        if success:
            return jsonify({"message": "IIF generation task for today's POs triggered and email sent (if configured)."}), 200
        else:
            return jsonify({"error": "IIF generation for today failed. Check logs for details."}), 500
    except Exception as e:
        print(f"ERROR APP (USER_IIF_TODAY): Error during IIF generation task for today: {e}")
        return jsonify({"error": "An error occurred.", "details": str(e)}), 500
          
# === Entry point for running the Flask app ===
if __name__ == '__main__':
    print(f"Starting G1 PO App Backend...")
    if engine is None:
        print("CRITICAL MAIN: Database engine not initialized. Flask app might not work correctly with DB operations.")
    else:
        run_host = os.getenv("FLASK_RUN_HOST", "127.0.0.1") 
        run_port = int(os.getenv("FLASK_RUN_PORT", 8080)) 
        print(f"--> Running Flask development server on http://{run_host}:{run_port} with debug={app.debug}")
        app.run(host=run_host, port=run_port, debug=app.debug)
else:
    print("DEBUG APP_SETUP: Script imported by WSGI server (like Gunicorn).")
    if engine is None:
        print("CRITICAL GUNICORN: Database engine not initialized during import. DB operations will fail.")
    else:
        print("DEBUG GUNICORN: Database engine appears initialized during import.")

print("DEBUG APP_SETUP: Reached end of app.py top-level execution.")