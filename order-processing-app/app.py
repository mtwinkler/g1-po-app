# app.py - Corrected Full Version with G1 Onsite Fulfillment & base64 import

import os
import time 
import traceback 
from flask import Flask, jsonify, request, g
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
import base64 # <--- ADDED IMPORT FOR BASE64

# --- Firebase Admin SDK Imports ---
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth 


# --- GCS Import ---
try:
    from google.cloud import storage
except ImportError:
    print("WARN APP_SETUP: google-cloud-storage library not found. Please install it (`pip install google-cloud-storage`).")
    storage = None
# --- End GCS Import ---

# --- Import your custom service modules ---
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

CORS(app, 
     resources={r"/api/*": {"origins": "https://g1-po-app-77790.web.app"}}, 
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], 
     allow_headers=["Content-Type", "Authorization"], 
     supports_credentials=True 
)
print("DEBUG APP_SETUP: CORS configured.")

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
db_driver = os.getenv("DB_DRIVER", "pg8000") 

bc_store_hash = os.getenv("BIGCOMMERCE_STORE_HASH")
bc_client_id = os.getenv("BIGCOMMERCE_CLIENT_ID") 
bc_access_token = os.getenv("BIGCOMMERCE_ACCESS_TOKEN")
domestic_country_code = os.getenv("DOMESTIC_COUNTRY_CODE", "US")
bc_processing_status_id = os.getenv("BC_PROCESSING_STATUS_ID")
bc_shipped_status_id = os.getenv("BC_SHIPPED_STATUS_ID") 

# Identifier for G1 Onsite Fulfillment (must match frontend)
G1_ONSITE_FULFILLMENT_IDENTIFIER = "_G1_ONSITE_FULFILLMENT_"

# --- Ship From Address Config ---
SHIP_FROM_NAME = os.getenv("SHIP_FROM_NAME", "Your Company Name")
SHIP_FROM_CONTACT = os.getenv("SHIP_FROM_CONTACT", "Shipping Dept")
SHIP_FROM_STREET1 = os.getenv("SHIP_FROM_STREET1")
SHIP_FROM_STREET2 = os.getenv("SHIP_FROM_STREET2", "") 
SHIP_FROM_CITY = os.getenv("SHIP_FROM_CITY")
SHIP_FROM_STATE = os.getenv("SHIP_FROM_STATE") 
SHIP_FROM_ZIP = os.getenv("SHIP_FROM_ZIP")
SHIP_FROM_COUNTRY = os.getenv("SHIP_FROM_COUNTRY", "US") 
SHIP_FROM_PHONE = os.getenv("SHIP_FROM_PHONE")

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

from functools import wraps 
def verify_firebase_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        id_token = None
        if auth_header and auth_header.startswith('Bearer '):
            id_token = auth_header.split('Bearer ')[1]
        if not id_token:
            return jsonify({"error": "Unauthorized", "message": "Authorization token is missing."}), 401
        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
            g.user_uid = decoded_token.get('uid')
            g.user_email = decoded_token.get('email')
            if not decoded_token.get('isApproved') == True: 
                print(f"WARN AUTH: User {g.user_email} (UID: {g.user_uid}) is not approved. Decoded token claims: {decoded_token.get('isApproved')}")
                return jsonify({"error": "Forbidden", "message": "User not approved for this application."}), 403
        except firebase_auth.RevokedIdTokenError:
            print("ERROR AUTH: Firebase ID token has been revoked.")
            return jsonify({"error": "Unauthorized", "message": "Token revoked."}), 401
        except firebase_auth.UserDisabledError:
            user_identifier = g.user_uid if 'g' in globals() and hasattr(g, 'user_uid') else 'Unknown'
            print(f"ERROR AUTH: Firebase user account (UID: {user_identifier}) is disabled.")
            return jsonify({"error": "Unauthorized", "message": "User account disabled."}), 401
        except firebase_auth.InvalidIdTokenError as e:
            print(f"ERROR AUTH: Firebase ID token is invalid: {e}")
            return jsonify({"error": "Unauthorized", "message": f"Token invalid: {e}"}), 401
        except Exception as e: 
            print(f"ERROR AUTH: General token verification failed: {e}")
            traceback.print_exc()
            return jsonify({"error": "Unauthorized", "message": f"General token verification error: {e}"}), 401
        return f(*args, **kwargs)
    return decorated_function

# === BASIC ROUTES ===
@app.route('/')
def hello(): return 'G1 PO App Backend is Running!'
print("DEBUG APP_SETUP: Defined / route.") 

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
print("DEBUG APP_SETUP: Defined /test_db route.") 

# === ORDER ROUTES ===
@app.route('/api/orders', methods=['GET'])
@verify_firebase_token 
def get_orders():
    print("DEBUG GET_ORDERS: Received request")
    status_filter = request.args.get('status') 
    print(f"DEBUG GET_ORDERS: Status filter = {status_filter}")
    db_conn = None
    try:
        if engine is None: return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()
        base_query = "SELECT * FROM orders"
        params = {}
        if status_filter and status_filter != 'all': 
            base_query += " WHERE status = :status_filter"
            params["status_filter"] = status_filter
        base_query += " ORDER BY order_date DESC, id DESC"
        query = text(base_query)
        records = db_conn.execute(query, params).fetchall()
        orders_list = [convert_row_to_dict(row) for row in records]
        return jsonify(make_json_safe(orders_list)), 200 
    except Exception as e:
        print(f"ERROR GET_ORDERS: {e}")
        return jsonify({"error": "Failed to fetch orders", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed: db_conn.close()
        print("DEBUG GET_ORDERS: DB connection closed.")
print("DEBUG APP_SETUP: Defined /api/orders GET route.") 

@app.route('/api/orders/<int:order_id>', methods=['GET'])
@verify_firebase_token 
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
        base_line_items_sql = """
            SELECT oli.id AS line_item_id, oli.order_id AS parent_order_id, oli.bigcommerce_line_item_id,
                   oli.sku AS original_sku, oli.name AS line_item_name, oli.quantity, oli.sale_price,
                   oli.created_at AS line_item_created_at, oli.updated_at AS line_item_updated_at
            FROM order_line_items oli WHERE oli.order_id = :order_id_param ORDER BY oli.id """
        base_line_items_records = db_conn.execute(text(base_line_items_sql), {"order_id_param": order_id}).fetchall()
        augmented_line_items_list = []
        for row in base_line_items_records:
            item_dict = convert_row_to_dict(row)
            original_sku_for_item = item_dict.get('original_sku')
            hpe_option_pn, hpe_pn_type, sku_mapped = get_hpe_mapping_with_fallback(original_sku_for_item, db_conn)
            item_dict['hpe_option_pn'] = hpe_option_pn
            item_dict['hpe_pn_type'] = hpe_pn_type
            item_dict['hpe_po_description'] = None 
            if hpe_option_pn:
                desc_query = text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn")
                custom_desc_result = db_conn.execute(desc_query, {"option_pn": hpe_option_pn}).scalar_one_or_none()
                if custom_desc_result: item_dict['hpe_po_description'] = custom_desc_result
            augmented_line_items_list.append(item_dict)
        print(f"DEBUG GET_ORDER: Found order ID {order_id} with {len(augmented_line_items_list)} augmented line items.")
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
print("DEBUG APP_SETUP: Defined /api/orders/<id> GET route.") 

@app.route('/api/lookup/spare_part/<path:option_sku>', methods=['GET'])
@verify_firebase_token 
def get_spare_part_for_option(option_sku):
    if not option_sku: return jsonify({"error": "Option SKU is required"}), 400
    db_conn = None
    print(f"DEBUG LOOKUP_SPARE: Received request for option SKU: {option_sku}")
    try:
        if engine is None: return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()
        find_spare_query = text("SELECT sku FROM hpe_part_mappings WHERE option_pn = :option_sku AND pn_type = 'spare'")
        spare_part_sku_record = db_conn.execute(find_spare_query, {"option_sku": option_sku}).fetchone()
        if spare_part_sku_record and spare_part_sku_record.sku:
            spare_sku = spare_part_sku_record.sku
            print(f"DEBUG LOOKUP_SPARE: Found spare part SKU '{spare_sku}' for option SKU '{option_sku}'.")
            return jsonify({"spare_sku": spare_sku}), 200
        else:
            is_option_query = text("SELECT 1 FROM hpe_part_mappings WHERE option_pn = :option_sku AND pn_type = 'option' LIMIT 1")
            is_valid_option = db_conn.execute(is_option_query, {"option_sku": option_sku}).fetchone()
            if not is_valid_option:
                print(f"DEBUG LOOKUP_SPARE: Input SKU '{option_sku}' is not registered as an 'option' type.")
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
print("DEBUG APP_SETUP: Defined /api/lookup/spare_part/<path:option_sku> route.") # Restored log

@app.route('/api/orders/status-counts', methods=['GET'])
@verify_firebase_token 
def get_order_status_counts():
    print("DEBUG GET_STATUS_COUNTS: Received request")
    db_conn = None
    try:
        if engine is None:
            print("ERROR GET_STATUS_COUNTS: Database engine not available.")
            return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()
        print("DEBUG GET_STATUS_COUNTS: DB connection established.")
        sql_query = text("SELECT status, COUNT(id) AS order_count FROM orders GROUP BY status;")
        records = db_conn.execute(sql_query).fetchall()
        status_counts_dict = {}
        for row in records:
            row_dict = convert_row_to_dict(row) 
            if row_dict and row_dict.get('status') is not None:
                status_counts_dict[row_dict['status']] = row_dict.get('order_count', 0)
        print(f"DEBUG GET_STATUS_COUNTS: Fetched counts: {status_counts_dict}")
        defined_statuses = ['new', 'RFQ Sent', 'Processed', 'international_manual', 'pending', 'Completed Offline'] 
        for s in defined_statuses:
            if s not in status_counts_dict: status_counts_dict[s] = 0
        return jsonify(make_json_safe(status_counts_dict)), 200 
    except Exception as e:
        print(f"ERROR GET_STATUS_COUNTS: {e}")
        return jsonify({"error": "Failed to fetch order status counts", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print("DEBUG GET_STATUS_COUNTS: DB connection closed.")
print("DEBUG APP_SETUP: Defined /api/orders/status-counts GET route.") 

@app.route('/api/orders/<int:order_id>/status', methods=['POST'])
@verify_firebase_token 
def update_order_status(order_id):
    print(f"DEBUG UPDATE_STATUS: Received request for order ID: {order_id}")
    data = request.get_json()
    new_status = data.get('status')
    if not new_status: return jsonify({"error": "Missing 'status' in request body"}), 400
    allowed_statuses = ['new', 'Processed', 'RFQ Sent', 'international_manual', 'pending', 'Completed Offline', 'other_status'] 
    if new_status not in allowed_statuses: return jsonify({"error": f"Invalid status value: {new_status}"}), 400
    db_conn = None
    transaction = None
    try:
        if engine is None: return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()
        transaction = db_conn.begin()
        update_sql = text("UPDATE orders SET status = :new_status, updated_at = CURRENT_TIMESTAMP WHERE id = :order_id RETURNING id, status, updated_at")
        result = db_conn.execute(update_sql, {"new_status": new_status, "order_id": order_id})
        updated_row = result.fetchone()
        if updated_row is None:
             transaction.rollback()
             print(f"WARN UPDATE_STATUS: Order ID {order_id} not found for status update.")
             return jsonify({"error": f"Order with ID {order_id} not found"}), 404
        transaction.commit()
        updated_data = convert_row_to_dict(updated_row)
        print(f"DEBUG UPDATE_STATUS: Successfully updated order {order_id} status to '{new_status}'.")
        return jsonify({"message": f"Order {order_id} status updated to {new_status}", "order": make_json_safe(updated_data)}), 200
    except Exception as e:
        if transaction and transaction.is_active: transaction.rollback()
        print(f"ERROR UPDATE_STATUS: Failed for order {order_id}: {e}")
        return jsonify({"error": "Failed to update order status", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed: db_conn.close()
        print(f"DEBUG UPDATE_STATUS: DB connection closed for order ID {order_id}.")
print("DEBUG APP_SETUP: Defined /api/orders/<id>/status POST route.") 

@app.route('/api/ingest_orders', methods=['POST'])
@verify_firebase_token 
def ingest_orders():
    try:
        print("Received request for /api/ingest_orders")
        if not bc_api_base_url_v2 or not bc_headers:
            return jsonify({"message": "BigCommerce API credentials not fully configured."}), 500
        try: target_status_id = int(bc_processing_status_id)
        except (ValueError, TypeError): return jsonify({"message": f"BC_PROCESSING_STATUS_ID '{bc_processing_status_id}' is invalid."}), 500
        if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
        orders_list_endpoint = f"{bc_api_base_url_v2}orders"
        api_params = {'status_id': target_status_id, 'sort': 'date_created:asc', 'limit': 250}
        print(f"DEBUG INGEST: Fetching orders with status ID {target_status_id} from {orders_list_endpoint}")
        response = requests.get(orders_list_endpoint, headers=bc_headers, params=api_params)
        response.raise_for_status() 
        orders_list_from_bc = response.json()
        if not isinstance(orders_list_from_bc, list):
            print(f"ERROR INGEST: Unexpected API response format. Expected list, got {type(orders_list_from_bc)}")
            return jsonify({"message": "Ingestion failed: Unexpected API response format."}), 500
        if not orders_list_from_bc:
            print(f"INFO INGEST: Successfully ingested 0 orders with BC status ID '{target_status_id}'.")
            return jsonify({"message": f"Successfully ingested 0 orders with BC status ID '{target_status_id}'."}), 200
        ingested_count, inserted_count_this_run, updated_count_this_run = 0, 0, 0
        with engine.connect() as conn:
            with conn.begin(): 
                print(f"DEBUG INGEST: Processing {len(orders_list_from_bc)} orders from BigCommerce.")
                for bc_order_summary in orders_list_from_bc:
                    order_id_from_bc = bc_order_summary.get('id')
                    if order_id_from_bc is None:
                        print("WARN INGEST: Skipping order summary with missing 'id'.")
                        continue
                    print(f"DEBUG INGEST: Processing BC Order ID: {order_id_from_bc}")
                    shipping_addresses_list, products_list, is_international, calculated_shipping_method_name, customer_shipping_address = [], [], False, 'N/A', {}
                    try:
                        shipping_addr_url = f"{bc_api_base_url_v2}orders/{order_id_from_bc}/shippingaddresses"
                        shipping_res = requests.get(shipping_addr_url, headers=bc_headers)
                        shipping_res.raise_for_status()
                        shipping_addresses_list = shipping_res.json()
                        if shipping_addresses_list and isinstance(shipping_addresses_list, list) and shipping_addresses_list[0]:
                            customer_shipping_address = shipping_addresses_list[0]
                            shipping_country_code = customer_shipping_address.get('country_iso2')
                            is_international = bool(shipping_country_code and shipping_country_code != domestic_country_code)
                            calculated_shipping_method_name = customer_shipping_address.get('shipping_method', bc_order_summary.get('shipping_method', 'N/A'))
                        else: print(f"WARN INGEST: No valid shipping address found for BC Order {order_id_from_bc}.")
                        products_url = f"{bc_api_base_url_v2}orders/{order_id_from_bc}/products"
                        products_res = requests.get(products_url, headers=bc_headers)
                        products_res.raise_for_status()
                        products_list = products_res.json()
                        if not isinstance(products_list, list):
                            print(f"WARN INGEST: Products list for BC Order {order_id_from_bc} is not a list. Treating as empty.")
                            products_list = []
                    except requests.exceptions.RequestException as sub_req_e:
                        print(f"ERROR INGEST: Could not fetch sub-resources for BC Order {order_id_from_bc}: {sub_req_e}. Skipping this order.")
                        continue 
                    existing_order_row = conn.execute(text("SELECT id, status, is_international, payment_method, bigcommerce_order_tax, customer_notes FROM orders WHERE bigcommerce_order_id = :bc_order_id"), {"bc_order_id": order_id_from_bc}).fetchone()
                    bc_total_tax = Decimal(bc_order_summary.get('total_tax', '0.00'))
                    bc_total_inc_tax = Decimal(bc_order_summary.get('total_inc_tax', '0.00'))
                    current_time_utc = datetime.now(timezone.utc)
                    raw_customer_message = bc_order_summary.get('customer_message', '')
                    cleaned_customer_message = raw_customer_message
                    if raw_customer_message:
                        pattern = re.compile(r'\*{10}.*?\*{10}', re.DOTALL) 
                        cleaned_customer_message = pattern.sub('', raw_customer_message).strip()
                        if raw_customer_message != cleaned_customer_message: print(f"DEBUG INGEST: Cleaned customer notes for BC Order {order_id_from_bc}.")
                    if existing_order_row:
                        db_status = existing_order_row.status
                        print(f"DEBUG INGEST: Order {order_id_from_bc} exists (App ID: {existing_order_row.id}). DB status: '{db_status}'.")
                        finalized_or_manual_statuses = ['Processed', 'Completed Offline', 'pending', 'RFQ Sent', 'international_manual']
                        if db_status in finalized_or_manual_statuses:
                            print(f"DEBUG INGEST: Skipping further processing for BC Order {order_id_from_bc} as its local status is '{db_status}'.")
                            continue 
                        db_is_international, db_payment_method, db_tax_amount, db_customer_notes = existing_order_row.is_international, existing_order_row.payment_method, existing_order_row.bigcommerce_order_tax, existing_order_row.customer_notes
                        bc_payment_method = bc_order_summary.get('payment_method')
                        update_fields = {}
                        if db_is_international != is_international: update_fields['is_international'] = is_international
                        if db_payment_method != bc_payment_method: update_fields['payment_method'] = bc_payment_method
                        if db_tax_amount != bc_total_tax: update_fields['bigcommerce_order_tax'] = bc_total_tax
                        if db_customer_notes != cleaned_customer_message: update_fields['customer_notes'] = cleaned_customer_message
                        if db_status not in finalized_or_manual_statuses: 
                            new_app_status_by_ingest = 'international_manual' if is_international else 'new'
                            if db_status != new_app_status_by_ingest:
                                print(f"DEBUG INGEST: Current status '{db_status}' for order {order_id_from_bc} differs. Setting to '{new_app_status_by_ingest}'.")
                                update_fields['status'] = new_app_status_by_ingest
                        if update_fields:
                            update_fields['updated_at'] = current_time_utc
                            set_clauses = [f"{key} = :{key}" for key in update_fields.keys()]
                            update_stmt_str = f"UPDATE orders SET {', '.join(set_clauses)} WHERE id = :id"
                            conn.execute(text(update_stmt_str), {"id": existing_order_row.id, **update_fields})
                            print(f"DEBUG INGEST: Updated Order {order_id_from_bc} (App ID: {existing_order_row.id}). Fields: {list(update_fields.keys())}")
                            updated_count_this_run += 1
                        else: print(f"DEBUG INGEST: No updates needed for existing order {order_id_from_bc}.")
                    else: # New order insertion logic                   
                        target_app_status = 'international_manual' if is_international else 'new'
                        order_values = { "bigcommerce_order_id": order_id_from_bc, "customer_company": customer_shipping_address.get('company'), "customer_name": f"{customer_shipping_address.get('first_name', '')} {customer_shipping_address.get('last_name', '')}".strip(), "customer_shipping_address_line1": customer_shipping_address.get('street_1'), "customer_shipping_address_line2": customer_shipping_address.get('street_2'), "customer_shipping_city": customer_shipping_address.get('city'), "customer_shipping_state": customer_shipping_address.get('state'), "customer_shipping_zip": customer_shipping_address.get('zip'), "customer_shipping_country": customer_shipping_address.get('country_iso2'), "customer_phone": customer_shipping_address.get('phone'), "customer_email": bc_order_summary.get('billing_address', {}).get('email', customer_shipping_address.get('email')), "customer_shipping_method": calculated_shipping_method_name, "customer_notes": cleaned_customer_message, "order_date": datetime.strptime(bc_order_summary['date_created'], '%a, %d %b %Y %H:%M:%S %z').replace(tzinfo=timezone.utc) if bc_order_summary.get('date_created') else current_time_utc, "total_sale_price": bc_total_inc_tax, "bigcommerce_order_tax": bc_total_tax, "status": target_app_status, "is_international": is_international, "payment_method": bc_order_summary.get('payment_method'), "created_at": current_time_utc, "updated_at": current_time_utc }
                        order_table_cols = [sqlalchemy.column(c) for c in order_values.keys()]
                        insert_order_stmt = insert(sqlalchemy.table('orders', *order_table_cols)).values(order_values).returning(sqlalchemy.column('id'))
                        inserted_order_id = conn.execute(insert_order_stmt).scalar_one()
                        print(f"DEBUG INGEST: Inserted new Order {order_id_from_bc} (App ID {inserted_order_id}), status: {target_app_status}, Tax: {bc_total_tax}")
                        inserted_count_this_run += 1
                        if products_list:
                            for item in products_list:
                                if not isinstance(item, dict):
                                     print(f"WARN INGEST: Skipping invalid item data for order {inserted_order_id}: {item}")
                                     continue
                                sale_price_excl_tax = Decimal(item.get('price_ex_tax', '0.00'))
                                line_item_values = { "order_id": inserted_order_id, "bigcommerce_line_item_id": item.get('id'), "sku": item.get('sku'), "name": item.get('name'), "quantity": item.get('quantity'), "sale_price": sale_price_excl_tax, "created_at": current_time_utc, "updated_at": current_time_utc }
                                line_item_table_cols = [sqlalchemy.column(c) for c in line_item_values.keys()]
                                conn.execute(insert(sqlalchemy.table('order_line_items', *line_item_table_cols)).values(line_item_values))
                            print(f"DEBUG INGEST: Inserted {len(products_list)} line items for new order {inserted_order_id}.")
                        else: print(f"WARN INGEST: No products found or processed for new BC Order {order_id_from_bc}.")
                    ingested_count += 1 
            # Transaction commits here
        print(f"INFO INGEST: Successfully processed {ingested_count} orders. Inserted: {inserted_count_this_run}, Updated: {updated_count_this_run}.")
        return jsonify({"message": f"Processed {ingested_count} orders. Inserted {inserted_count_this_run} new. Updated {updated_count_this_run}."}), 200
    except requests.exceptions.RequestException as req_e:
        error_message = f"BigCommerce API Request failed: {req_e}"
        status_code = req_e.response.status_code if req_e.response is not None else 'N/A'
        response_text = req_e.response.text if req_e.response is not None else 'N/A'
        print(f"ERROR INGEST: {error_message}, Status: {status_code}, Response: {response_text[:500]}")
        return jsonify({"message": error_message, "status_code": status_code, "response_preview": response_text[:500]}), 500
    except sqlalchemy.exc.SQLAlchemyError as db_e:
        print(f"ERROR INGEST: Database error during ingestion: {db_e}")
        traceback.print_exc()
        return jsonify({"message": f"Database error during order ingestion: {db_e}", "error_type": type(db_e).__name__}), 500
    except Exception as e:
        print(f"ERROR INGEST: Unexpected error during ingestion: {e}")
        traceback.print_exc()
        return jsonify({"message": f"Unexpected error during order ingestion: {e}", "error_type": type(e).__name__}), 500

# === PROCESS ORDER ROUTE (MODIFIED FOR G1 ONSITE FULFILLMENT) ===
@app.route('/api/orders/<int:order_id>/process', methods=['POST'])
@verify_firebase_token
def process_order(order_id):
    print(f"DEBUG PROCESS_ORDER: Received request to process order ID: {order_id}")
    db_conn, transaction, processed_pos_info_for_response = None, None, [] 
    try:
        payload = request.get_json()
        if not payload or 'assignments' not in payload or not isinstance(payload['assignments'], list):
            return jsonify({"error": "Invalid or missing 'assignments' array in payload"}), 400
        assignments = payload['assignments']
        if not assignments: return jsonify({"error": "Assignments array cannot be empty."}), 400
        
        if engine is None: return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect(); transaction = db_conn.begin()
        
        order_record = db_conn.execute(text("SELECT * FROM orders WHERE id = :id"), {"id": order_id}).fetchone()
        if not order_record:
            if transaction.is_active: transaction.rollback()
            return jsonify({"error": f"Order with ID {order_id} not found"}), 404
        order_data_dict = convert_row_to_dict(order_record)
        
        order_status_from_db = order_data_dict.get('status')
        if order_status_from_db and order_status_from_db.lower() in ['processed', 'completed offline']:
            if transaction.is_active: transaction.rollback()
            return jsonify({"error": f"Order {order_id} status is '{order_status_from_db}' and cannot be reprocessed."}), 400
        
        local_order_line_items_records = db_conn.execute(text("SELECT id AS line_item_id, bigcommerce_line_item_id, sku AS original_sku, name AS line_item_name, quantity FROM order_line_items WHERE order_id = :order_id_param ORDER BY id"), {"order_id_param": order_id}).fetchall()
        local_order_line_items_list = [convert_row_to_dict(row) for row in local_order_line_items_records]
        all_original_order_line_item_db_ids = {item['line_item_id'] for item in local_order_line_items_list}
        processed_original_order_line_item_db_ids_this_batch = set() 
        
        current_utc_datetime = datetime.now(timezone.utc)
        ship_from_address = {'name': SHIP_FROM_NAME, 'contact_person': SHIP_FROM_CONTACT, 'street_1': SHIP_FROM_STREET1, 'street_2': SHIP_FROM_STREET2, 'city': SHIP_FROM_CITY, 'state': SHIP_FROM_STATE, 'zip': SHIP_FROM_ZIP, 'country': SHIP_FROM_COUNTRY, 'phone': SHIP_FROM_PHONE}
        
        actual_supplier_assignments = [a for a in assignments if a.get('supplier_id') != G1_ONSITE_FULFILLMENT_IDENTIFIER]
        is_multi_actual_supplier_po_scenario = len(actual_supplier_assignments) > 1

        next_sequence_num = None
        if actual_supplier_assignments: 
            starting_po_sequence = 200001
            max_po_query = text("SELECT MAX(CAST(numeric_po_number AS INTEGER)) FROM (SELECT po_number AS numeric_po_number FROM purchase_orders WHERE CAST(po_number AS TEXT) ~ '^[0-9]+$') AS numeric_pos")
            max_po_value_from_db = db_conn.execute(max_po_query).scalar_one_or_none()
            next_sequence_num = starting_po_sequence
            if max_po_value_from_db is not None:
                try: next_sequence_num = max(starting_po_sequence, int(max_po_value_from_db) + 1)
                except ValueError: print(f"WARN PROCESS_ORDER: Could not parse max PO number '{max_po_value_from_db}'. Defaulting PO sequence.")

        # --- Main processing loop for assignments ---
        for assignment_data in assignments:
            supplier_id_from_payload = assignment_data.get('supplier_id') 
            total_shipment_weight_lbs_str = assignment_data.get('total_shipment_weight_lbs')
            shipment_method_from_payload = assignment_data.get('shipment_method')
            payment_instructions_from_frontend = assignment_data.get('payment_instructions', "")
            po_line_items_input = assignment_data.get('po_line_items', []) 

            g1_ps_signed_url, g1_label_signed_url = None, None 
            po_pdf_signed_url, ps_signed_url_supplier, label_signed_url_supplier = None, None, None 

            if supplier_id_from_payload == G1_ONSITE_FULFILLMENT_IDENTIFIER:
                print(f"INFO PROCESS_ORDER: Handling G1 Onsite Fulfillment for order ID: {order_id}")
                g1_ps_blob_name_for_db, g1_label_blob_name_for_db = None, None 
                g1_tracking_number = None # Initialize for G1

                if not local_order_line_items_list:
                    print(f"WARN PROCESS_ORDER (G1 Onsite): Order {order_id} has no line items. Skipping packing slip and label generation.")
                else: 
                    if not total_shipment_weight_lbs_str or not shipment_method_from_payload:
                        raise ValueError("Shipment method and weight are required for G1 Onsite Fulfillment with items.")
                    try:
                        current_g1_weight = float(total_shipment_weight_lbs_str)
                        if current_g1_weight <= 0: raise ValueError("Shipment weight must be positive.")
                    except ValueError: raise ValueError("Invalid shipment weight format for G1 Onsite Fulfillment.")
                
                items_for_g1_packing_slip = []
                for item_detail in local_order_line_items_list:
                    ps_sku, ps_desc = item_detail.get('original_sku', 'N/A'), item_detail.get('line_item_name', 'N/A')
                    hpe_opt_pn, _, _ = get_hpe_mapping_with_fallback(ps_sku, db_conn)
                    if hpe_opt_pn:
                        ps_sku = hpe_opt_pn
                        mapped_ps_desc = db_conn.execute(text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn"), {"option_pn": hpe_opt_pn}).scalar_one_or_none()
                        if mapped_ps_desc: ps_desc = mapped_ps_desc
                    items_for_g1_packing_slip.append({'sku': ps_sku, 'name': ps_desc, 'quantity': item_detail.get('quantity')})
                    processed_original_order_line_item_db_ids_this_batch.add(item_detail['line_item_id']) 

                g1_packing_slip_pdf_bytes = None
                if document_generator and items_for_g1_packing_slip: 
                    ps_args = {"order_data": order_data_dict, "items_in_this_shipment": items_for_g1_packing_slip, "items_shipping_separately": [], "logo_gcs_uri": COMPANY_LOGO_GCS_URI, "is_g1_onsite_fulfillment": True}
                    g1_packing_slip_pdf_bytes = document_generator.generate_packing_slip_pdf(**ps_args)
                    if g1_packing_slip_pdf_bytes and storage_client and GCS_BUCKET_NAME:
                        ts_suffix = current_utc_datetime.strftime("%Y%m%d%H%M%S")
                        g1_ps_blob_name = f"processed_orders/order_{order_data_dict['bigcommerce_order_id']}_G1Onsite/ps_g1_{ts_suffix}.pdf"
                        g1_ps_blob_name_for_db = f"gs://{GCS_BUCKET_NAME}/{g1_ps_blob_name}"
                        g1_ps_blob = storage_client.bucket(GCS_BUCKET_NAME).blob(g1_ps_blob_name)
                        g1_ps_blob.upload_from_string(g1_packing_slip_pdf_bytes, content_type='application/pdf')
                        try: g1_ps_signed_url = g1_ps_blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
                        except Exception as e_sign_g1ps: print(f"ERROR G1_ONSITE generating signed URL for Packing Slip PDF: {e_sign_g1ps}")

                g1_label_pdf_bytes = None # Reset for this assignment
                if shipping_service and total_shipment_weight_lbs_str and shipment_method_from_payload and local_order_line_items_list:
                    if all([SHIP_FROM_STREET1, SHIP_FROM_CITY, SHIP_FROM_STATE, SHIP_FROM_ZIP, SHIP_FROM_PHONE]):
                        try:
                            g1_label_pdf_bytes, g1_tracking_number = shipping_service.generate_ups_label(order_data=order_data_dict, ship_from_address=ship_from_address, total_weight_lbs=float(total_shipment_weight_lbs_str), customer_shipping_method_name=shipment_method_from_payload)
                            if g1_label_pdf_bytes and g1_tracking_number and storage_client and GCS_BUCKET_NAME:
                                ts_suffix = current_utc_datetime.strftime("%Y%m%d%H%M%S")
                                g1_label_blob_name = f"processed_orders/order_{order_data_dict['bigcommerce_order_id']}_G1Onsite/label_g1_{g1_tracking_number}_{ts_suffix}.pdf"
                                g1_label_blob_name_for_db = f"gs://{GCS_BUCKET_NAME}/{g1_label_blob_name}"
                                g1_label_blob = storage_client.bucket(GCS_BUCKET_NAME).blob(g1_label_blob_name)
                                g1_label_blob.upload_from_string(g1_label_pdf_bytes, content_type='application/pdf')
                                try: g1_label_signed_url = g1_label_blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
                                except Exception as e_sign_g1lbl: print(f"ERROR G1_ONSITE generating signed URL for Label PDF: {e_sign_g1lbl}")
                                
                                insert_g1_shipment_sql = text("""
                                    INSERT INTO shipments (order_id, purchase_order_id, tracking_number, shipping_method_name, 
                                                           weight_lbs, label_gcs_path, packing_slip_gcs_path, created_at, updated_at) 
                                    VALUES (:order_id, NULL, :track_num, :method, :weight, :label_path, :ps_path, :now, :now)
                                """)
                                g1_shipment_params = {
                                    "order_id": order_id, "track_num": g1_tracking_number, "method": shipment_method_from_payload, 
                                    "weight": float(total_shipment_weight_lbs_str), 
                                    "label_path": g1_label_blob_name_for_db, 
                                    "ps_path": g1_ps_blob_name_for_db, 
                                    "now": current_utc_datetime
                                }
                                db_conn.execute(insert_g1_shipment_sql, g1_shipment_params)
                                print(f"INFO: G1 Onsite Shipment record for order {order_id} created with tracking {g1_tracking_number}.")
                        except Exception as label_e_g1: print(f"ERROR PROCESS_ORDER (G1 Onsite Label): {label_e_g1}")
                    else: print("WARN PROCESS_ORDER (G1 Onsite): Ship From address not fully configured. Label generation skipped.")
                
                if email_service: 
                    g1_email_attachments = [] # Use a consistent variable name
                    if g1_packing_slip_pdf_bytes: 
                        g1_email_attachments.append({
                            "Name": f"PackingSlip_Order_{order_data_dict['bigcommerce_order_id']}_G1.pdf", 
                            "Content": base64.b64encode(g1_packing_slip_pdf_bytes).decode('utf-8'), 
                            "ContentType": "application/pdf"
                        })
                    if g1_label_pdf_bytes: 
                        g1_email_attachments.append({
                            "Name": f"ShippingLabel_Order_{order_data_dict['bigcommerce_order_id']}_G1.pdf", 
                            "Content": base64.b64encode(g1_label_pdf_bytes).decode('utf-8'), 
                            "ContentType": "application/pdf"
                        })
                    
                    if g1_email_attachments: 
                        email_subject_g1 = f"G1 Onsite Fulfillment Processed: Order {order_data_dict['bigcommerce_order_id']}"
                        email_html_body_g1 = (f"<p>Order {order_data_dict['bigcommerce_order_id']} has been fulfilled from G1 stock. "
                                              f"Documents attached.</p><p>Tracking: {g1_tracking_number or 'N/A'}</p>")
                        email_text_body_g1 = (f"Order {order_data_dict['bigcommerce_order_id']} has been fulfilled from G1 stock. "
                                              f"Documents attached.\nTracking: {g1_tracking_number or 'N/A'}")
                        
                        # Ensure 'email_service.py' has a function named 'send_sales_notification_email'
                        # or adjust this call to the correct function name in your email_service.py
                        if hasattr(email_service, 'send_sales_notification_email'):
                            email_service.send_sales_notification_email( 
                                recipient_email="sales@globalonetechnology.com",
                                subject=email_subject_g1,
                                html_body=email_html_body_g1,
                                text_body=email_text_body_g1,
                                attachments=g1_email_attachments 
                            )
                        elif hasattr(email_service, 'send_generic_email'): # Fallback if you named it send_generic_email
                             email_service.send_generic_email( 
                                recipient_email="sales@globalonetechnology.com",
                                subject=email_subject_g1,
                                html_body=email_html_body_g1,
                                text_body=email_text_body_g1, # Ensure your generic function can take text_body
                                attachments=g1_email_attachments 
                            )
                        else:
                            print(f"ERROR PROCESS_ORDER (G1 Onsite Email): Suitable email function (like send_sales_notification_email or send_generic_email) not found in email_service.py.")

                bc_order_id_for_update = order_data_dict.get('bigcommerce_order_id')
                if shipping_service and bc_api_base_url_v2 and bc_order_id_for_update:
                    if g1_tracking_number and local_order_line_items_list:
                        bc_address_id = _get_bc_shipping_address_id(bc_order_id_for_update)
                        bc_items_for_g1_shipment = [{"order_product_id": item_d.get('bigcommerce_line_item_id'), "quantity": item_d.get('quantity')} for item_d in local_order_line_items_list if item_d.get('bigcommerce_line_item_id')]
                        if bc_address_id is not None and bc_items_for_g1_shipment:
                            shipping_service.create_bigcommerce_shipment(
                                bigcommerce_order_id=bc_order_id_for_update, tracking_number=g1_tracking_number,
                                shipping_method_name=shipment_method_from_payload, 
                                line_items_in_shipment=bc_items_for_g1_shipment, order_address_id=bc_address_id
                            )
                    if bc_shipped_status_id: 
                        shipping_service.set_bigcommerce_order_status(bc_order_id_for_update, int(bc_shipped_status_id))
                        print(f"INFO G1_ONSITE: BigCommerce order {bc_order_id_for_update} status set to Shipped (ID: {bc_shipped_status_id}).")
                    else: print("WARN G1_ONSITE: BC_SHIPPED_STATUS_ID not set. Cannot update BC status.")

                db_conn.execute(text("UPDATE orders SET status = 'Completed Offline', updated_at = :now WHERE id = :order_id"), {"now": current_utc_datetime, "order_id": order_id})
                
                processed_pos_info_for_response.append({
                    "po_number": "N/A (G1 Onsite)", "supplier_id": G1_ONSITE_FULFILLMENT_IDENTIFIER, "tracking_number": g1_tracking_number,
                    "po_pdf_gcs_uri": None, "packing_slip_gcs_uri": g1_ps_signed_url, "label_gcs_uri": g1_label_signed_url
                })

            else: # --- Existing Supplier PO Logic (Single or Multi-Supplier) ---
                print(f"INFO PROCESS_ORDER: Handling Supplier PO for order ID: {order_id}, Supplier ID: {supplier_id_from_payload}")
                if not po_line_items_input: 
                    raise ValueError(f"No line items provided for supplier PO to supplier ID {supplier_id_from_payload}.")

                supplier_record = db_conn.execute(text("SELECT * FROM suppliers WHERE id = :id"), {"id": supplier_id_from_payload}).fetchone()
                if not supplier_record: raise ValueError(f"Supplier with ID {supplier_id_from_payload} not found.")
                supplier_data_dict = convert_row_to_dict(supplier_record)

                if next_sequence_num is None: 
                    raise Exception("PO Number sequence not initialized for supplier PO.")
                generated_po_number = str(next_sequence_num); next_sequence_num += 1
                
                po_total_amount = sum(Decimal(str(item.get('quantity', 0))) * Decimal(str(item.get('unit_cost', '0'))) for item in po_line_items_input)

                insert_po_sql = text("INSERT INTO purchase_orders (po_number, order_id, supplier_id, po_date, payment_instructions, status, total_amount, created_at, updated_at) VALUES (:po_number, :order_id, :supplier_id, :po_date, :payment_instructions, :status, :total_amount, :now, :now) RETURNING id")
                po_params = {"po_number": generated_po_number, "order_id": order_id, "supplier_id": supplier_id_from_payload, "po_date": current_utc_datetime, "payment_instructions": payment_instructions_from_frontend, "status": "New", "total_amount": po_total_amount, "now": current_utc_datetime}
                new_purchase_order_id = db_conn.execute(insert_po_sql, po_params).scalar_one()

                insert_po_item_sql = text("INSERT INTO po_line_items (purchase_order_id, original_order_line_item_id, sku, description, quantity, unit_cost, condition, created_at, updated_at) VALUES (:po_id, :orig_id, :sku_for_db, :desc, :qty, :cost, :cond, :now, :now)")
                po_items_for_pdf, items_for_packing_slip_this_po_supplier, ids_in_this_po = [], [], set()

                for item_input in po_line_items_input:
                    original_oli_id = item_input.get("original_order_line_item_id")
                    if original_oli_id is None: raise ValueError(f"Missing 'original_order_line_item_id' for PO {generated_po_number}")
                    ids_in_this_po.add(original_oli_id)
                    processed_original_order_line_item_db_ids_this_batch.add(original_oli_id) 
                    po_items_for_pdf.append({"sku": item_input.get('sku'), "description": item_input.get('description'), "quantity": int(item_input.get("quantity",0)), "unit_cost": Decimal(str(item_input.get("unit_cost", '0'))), "condition": item_input.get("condition", "New")})
                    
                    original_line_item_detail = next((oli for oli in local_order_line_items_list if oli['line_item_id'] == original_oli_id), None)
                    if not original_line_item_detail: raise ValueError(f"Original line item details for ID {original_oli_id} not found (PO to supplier).")
                    
                    ps_sku, ps_desc = original_line_item_detail.get('original_sku', 'N/A'), original_line_item_detail.get('line_item_name', 'N/A')
                    hpe_opt_pn_ps, _, _ = get_hpe_mapping_with_fallback(ps_sku, db_conn) 
                    if hpe_opt_pn_ps:
                        ps_sku = hpe_opt_pn_ps
                        mapped_ps_desc = db_conn.execute(text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn"), {"option_pn": hpe_opt_pn_ps}).scalar_one_or_none()
                        if mapped_ps_desc: ps_desc = mapped_ps_desc
                    items_for_packing_slip_this_po_supplier.append({'sku': ps_sku, 'name': ps_desc, 'quantity': int(item_input.get('quantity',0))})
                    
                    po_item_db_params = {"po_id": new_purchase_order_id, "orig_id": original_oli_id, "sku_for_db": item_input.get('sku'), "desc": item_input.get('description'), "qty": int(item_input.get("quantity", 0)), "cost": Decimal(str(item_input.get("unit_cost", '0'))), "cond": item_input.get("condition", "New"), "now": current_utc_datetime}
                    db_conn.execute(insert_po_item_sql, po_item_db_params)
                
                po_pdf_bytes, ps_pdf_bytes_supplier, label_pdf_bytes_supplier, tracking_this_po = None, None, None, None
                
                if document_generator:
                    po_args = {"supplier_data": supplier_data_dict, "po_number": generated_po_number, "po_date": current_utc_datetime, "po_items": po_items_for_pdf, "payment_terms": supplier_data_dict.get('payment_terms'), "payment_instructions": payment_instructions_from_frontend, "order_data": order_data_dict, "logo_gcs_uri": COMPANY_LOGO_GCS_URI, "is_partial_fulfillment": is_multi_actual_supplier_po_scenario}
                    po_pdf_bytes = document_generator.generate_purchase_order_pdf(**po_args)
                    
                    items_shipping_separately_supplier = [] 
                    for orig_item_db in local_order_line_items_list:
                        if orig_item_db.get('line_item_id') not in ids_in_this_po: 
                            sep_sku_ps, sep_desc_ps = orig_item_db.get('original_sku', 'N/A'), orig_item_db.get('line_item_name', 'N/A')
                            hpe_opt_pn_sep_ps, _, _ = get_hpe_mapping_with_fallback(sep_sku_ps, db_conn)
                            if hpe_opt_pn_sep_ps:
                                sep_sku_ps = hpe_opt_pn_sep_ps
                                mapped_sep_desc_ps = db_conn.execute(text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn"), {"option_pn": hpe_opt_pn_sep_ps}).scalar_one_or_none()
                                if mapped_sep_desc_ps: sep_desc_ps = mapped_sep_desc_ps
                            items_shipping_separately_supplier.append({'sku': sep_sku_ps, 'name': sep_desc_ps, 'quantity': orig_item_db.get('quantity')})
                    
                    ps_args_supplier = {"order_data": order_data_dict, "items_in_this_shipment": items_for_packing_slip_this_po_supplier, "items_shipping_separately": items_shipping_separately_supplier, "logo_gcs_uri": COMPANY_LOGO_GCS_URI}
                    # Pass the new flag if you added it to generate_packing_slip_pdf definition
                    # ps_args_supplier["is_g1_onsite_fulfillment"] = False # Explicitly false for supplier POs
                    ps_pdf_bytes_supplier = document_generator.generate_packing_slip_pdf(**ps_args_supplier)

                if shipping_service and total_shipment_weight_lbs_str and shipment_method_from_payload:
                    try:
                        current_weight = float(total_shipment_weight_lbs_str)
                        if current_weight > 0 and all([SHIP_FROM_STREET1, SHIP_FROM_CITY, SHIP_FROM_STATE, SHIP_FROM_ZIP, SHIP_FROM_PHONE]):
                            label_pdf_bytes_supplier, tracking_this_po = shipping_service.generate_ups_label(order_data=order_data_dict, ship_from_address=ship_from_address, total_weight_lbs=current_weight, customer_shipping_method_name=shipment_method_from_payload)
                            if label_pdf_bytes_supplier and tracking_this_po:
                                insert_ship_sql = text("INSERT INTO shipments (purchase_order_id, tracking_number, shipping_method_name, weight_lbs, created_at, updated_at) VALUES (:po_id, :track, :method, :weight, :now, :now) RETURNING id")
                                ship_params = {"po_id": new_purchase_order_id, "track": tracking_this_po, "method": shipment_method_from_payload, "weight": current_weight, "now": current_utc_datetime}
                                db_conn.execute(insert_ship_sql, ship_params) 
                    except Exception as label_e_supplier: print(f"ERROR PROCESS_ORDER (Supplier PO Label): {label_e_supplier}")

                if storage_client and GCS_BUCKET_NAME:
                    ts_suffix = current_utc_datetime.strftime("%Y%m%d%H%M%S")
                    common_prefix_supplier = f"processed_orders/order_{order_data_dict['bigcommerce_order_id']}_PO_{generated_po_number}"
                    bucket = storage_client.bucket(GCS_BUCKET_NAME)
                    gs_po_pdf_path_supplier, gs_ps_path_supplier, gs_label_path_supplier = None, None, None # GCS paths for this supplier PO
                    if po_pdf_bytes:
                        po_blob_name = f"{common_prefix_supplier}/po_{generated_po_number}_{ts_suffix}.pdf"
                        gs_po_pdf_path_supplier = f"gs://{GCS_BUCKET_NAME}/{po_blob_name}"
                        po_blob = bucket.blob(po_blob_name)
                        po_blob.upload_from_string(po_pdf_bytes, content_type='application/pdf')
                        db_conn.execute(text("UPDATE purchase_orders SET po_pdf_gcs_path = :path WHERE id = :id"), {"path": gs_po_pdf_path_supplier, "id": new_purchase_order_id})
                        try: po_pdf_signed_url = po_blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
                        except Exception as e_sign_po: print(f"ERROR gen signed URL PO: {e_sign_po}")
                    if ps_pdf_bytes_supplier:
                        ps_blob_name = f"{common_prefix_supplier}/ps_{generated_po_number}_{ts_suffix}.pdf"
                        gs_ps_path_supplier = f"gs://{GCS_BUCKET_NAME}/{ps_blob_name}"
                        ps_blob = bucket.blob(ps_blob_name)
                        ps_blob.upload_from_string(ps_pdf_bytes_supplier, content_type='application/pdf')
                        db_conn.execute(text("UPDATE purchase_orders SET packing_slip_gcs_path = :path WHERE id = :id"), {"path": gs_ps_path_supplier, "id": new_purchase_order_id})
                        try: ps_signed_url_supplier = ps_blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
                        except Exception as e_sign_ps: print(f"ERROR gen signed URL PS: {e_sign_ps}")
                    if label_pdf_bytes_supplier and tracking_this_po:
                        label_blob_name = f"{common_prefix_supplier}/label_{tracking_this_po}_{ts_suffix}.pdf"
                        gs_label_path_supplier = f"gs://{GCS_BUCKET_NAME}/{label_blob_name}"
                        label_blob = bucket.blob(label_blob_name)
                        label_blob.upload_from_string(label_pdf_bytes_supplier, content_type='application/pdf')
                        db_conn.execute(text("UPDATE shipments SET label_gcs_path = :path WHERE purchase_order_id = :po_id AND tracking_number = :track"), {"path": gs_label_path_supplier, "po_id": new_purchase_order_id, "track": tracking_this_po})
                        try: label_signed_url_supplier = label_blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
                        except Exception as e_sign_label: print(f"ERROR gen signed URL Label: {e_sign_label}")
                
                attachments_to_supplier = []
                if po_pdf_bytes: attachments_to_supplier.append({"Name": f"PO_{generated_po_number}.pdf", "Content": base64.b64encode(po_pdf_bytes).decode('utf-8'), "ContentType": "application/pdf"})
                if ps_pdf_bytes_supplier: attachments_to_supplier.append({"Name": f"PackingSlip_{generated_po_number}.pdf", "Content": base64.b64encode(ps_pdf_bytes_supplier).decode('utf-8'), "ContentType": "application/pdf"})
                if label_pdf_bytes_supplier: attachments_to_supplier.append({"Name": f"ShippingLabel_{tracking_this_po}.pdf", "Content": base64.b64encode(label_pdf_bytes_supplier).decode('utf-8'), "ContentType": "application/pdf"})

                if email_service and supplier_data_dict.get('email') and attachments_to_supplier:
                    email_service.send_po_email(supplier_email=supplier_data_dict['email'], po_number=generated_po_number, attachments=attachments_to_supplier) 
                    db_conn.execute(text("UPDATE purchase_orders SET status = 'SENT_TO_SUPPLIER', updated_at = :now WHERE id = :po_id"), {"po_id": new_purchase_order_id, "now": current_utc_datetime})

                if shipping_service and bc_api_base_url_v2 and tracking_this_po:
                    bc_order_id_bc_update = order_data_dict.get('bigcommerce_order_id')
                    bc_address_id_ship = _get_bc_shipping_address_id(bc_order_id_bc_update)
                    bc_items_for_this_ship_api = []
                    for oli_detail in local_order_line_items_list:
                        if oli_detail.get('line_item_id') in ids_in_this_po: 
                            po_item_for_bc_qty = next((pi_input for pi_input in po_line_items_input if pi_input.get("original_order_line_item_id") == oli_detail.get('line_item_id')), None)
                            if po_item_for_bc_qty and oli_detail.get('bigcommerce_line_item_id'):
                                bc_items_for_this_ship_api.append({"order_product_id": oli_detail.get('bigcommerce_line_item_id'), "quantity": po_item_for_bc_qty.get('quantity')})
                    if bc_order_id_bc_update and bc_address_id_ship is not None and bc_items_for_this_ship_api:
                        shipping_service.create_bigcommerce_shipment(
                            bigcommerce_order_id=bc_order_id_bc_update, tracking_number=tracking_this_po,
                            shipping_method_name=shipment_method_from_payload or order_data_dict.get('customer_shipping_method'),
                            line_items_in_shipment=bc_items_for_this_ship_api, order_address_id=bc_address_id_ship
                        )
                processed_pos_info_for_response.append({
                    "po_number": generated_po_number, "supplier_id": supplier_id_from_payload, "tracking_number": tracking_this_po,
                    "po_pdf_gcs_uri": po_pdf_signed_url, "packing_slip_gcs_uri": ps_signed_url_supplier, "label_gcs_uri": label_signed_url_supplier
                })
        # --- End of loop through assignments ---

        is_only_g1_onsite_processed = all(a.get('supplier_id') == G1_ONSITE_FULFILLMENT_IDENTIFIER for a in assignments)
        
        if is_only_g1_onsite_processed:
            # Local status 'Completed Offline' and BC status 'Shipped' already handled in G1 block
            print(f"INFO PROCESS_ORDER: Order {order_id} exclusively processed via G1 Onsite Fulfillment.")
        else: 
            # This means at least one supplier PO was involved.
            # Update local order status to 'Processed'
            db_conn.execute(text("UPDATE orders SET status = 'Processed', updated_at = :now WHERE id = :order_id"), 
                            {"now": current_utc_datetime, "order_id": order_id})
            print(f"INFO PROCESS_ORDER: Order {order_id} involved supplier POs. Local status set to 'Processed'.")

            # If ALL original items are covered by the POs sent to suppliers in this batch
            if all_original_order_line_item_db_ids.issubset(processed_original_order_line_item_db_ids_this_batch):
                if shipping_service and bc_api_base_url_v2 and bc_shipped_status_id and order_data_dict.get('bigcommerce_order_id'):
                    shipping_service.set_bigcommerce_order_status(
                        bigcommerce_order_id=order_data_dict.get('bigcommerce_order_id'), 
                        status_id=int(bc_shipped_status_id)
                    )
                    print(f"INFO PROCESS_ORDER: All items for order {order_id} covered by supplier POs. BC Status set to Shipped.")
            # else: # Optional: Handle "Partially Shipped" for BC if some items by POs, but not all
                # BC_PARTIALLY_SHIPPED_STATUS_ID = os.getenv("BC_PARTIALLY_SHIPPED_STATUS_ID")
                # if BC_PARTIALLY_SHIPPED_STATUS_ID and processed_original_order_line_item_db_ids_this_batch: 
                #     shipping_service.set_bigcommerce_order_status(bigcommerce_order_id=order_data_dict.get('bigcommerce_order_id'), status_id=int(BC_PARTIALLY_SHIPPED_STATUS_ID))
                #     print(f"INFO PROCESS_ORDER: Order {order_id} partially processed by supplier POs. BC Status set to Partially Shipped.")
        
        transaction.commit()
        final_message = f"Order {order_id} processed successfully."
        if is_only_g1_onsite_processed:
            final_message = f"Order {order_id} processed via G1 Onsite Fulfillment."
        elif processed_pos_info_for_response: 
            num_supplier_pos = sum(1 for po_info in processed_pos_info_for_response if po_info.get("supplier_id") != G1_ONSITE_FULFILLMENT_IDENTIFIER)
            if num_supplier_pos > 0:
                final_message = f"Order {order_id} processed. Generated {num_supplier_pos} supplier PO(s)."
        
        return jsonify({
            "message": final_message, 
            "order_id": order_id, 
            "processed_purchase_orders": make_json_safe(processed_pos_info_for_response) 
        }), 201
    
    except ValueError as ve:
        if transaction and transaction.is_active: transaction.rollback()
        print(f"ERROR PROCESS_ORDER (ValueError): {ve}"); traceback.print_exc()
        return jsonify({"error": "Processing failed due to invalid data.", "details": str(ve)}), 400
    except Exception as e: 
        if transaction and transaction.is_active:
             try: transaction.rollback()
             except Exception as rb_e: print(f"ERROR PROCESS_ORDER: Error during transaction rollback: {rb_e}")
        print(f"ERROR PROCESS_ORDER (Exception): Unhandled Exception: {e}"); traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred during order processing.", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed: 
            db_conn.close()
            print(f"DEBUG PROCESS_ORDER: DB Connection closed for order {order_id}")

# === SUPPLIER CRUD ROUTES (Restored) ===
@app.route('/api/suppliers', methods=['POST'])
@verify_firebase_token
def create_supplier():
    try:
        print("Received request for POST /api/suppliers")
        if engine is None:
            print("CREATE_SUPPLIER Error: Database engine not initialized.")
            return jsonify({"message": "Database engine not initialized."}), 500
        conn, trans = None, None 
        supplier_data = request.json
        print(f"DEBUG CREATE_SUPPLIER: Received data: {supplier_data}")
        required_fields = ['name', 'email']
        for field in required_fields:
            if not supplier_data or field not in supplier_data or not supplier_data[field]:
                print(f"DEBUG CREATE_SUPPLIER: Missing required field: {field}")
                return jsonify({"message": f"Missing required field: {field}"}), 400 
        name, email, payment_terms, address_line1, address_line2, city, state, zip_code, country, phone, contact_person, actual_default_po_notes_value = supplier_data.get('name'), supplier_data.get('email'), supplier_data.get('payment_terms'), supplier_data.get('address_line1'), supplier_data.get('address_line2'), supplier_data.get('city'), supplier_data.get('state'), supplier_data.get('zip'), supplier_data.get('country'), supplier_data.get('phone'), supplier_data.get('contact_person'), supplier_data.get('defaultponotes') 
        conn = engine.connect(); trans = conn.begin() 
        insert_supplier_stmt = insert(sqlalchemy.table( 'suppliers', sqlalchemy.column('name'), sqlalchemy.column('email'), sqlalchemy.column('payment_terms'), sqlalchemy.column('address_line1'), sqlalchemy.column('address_line2'), sqlalchemy.column('city'), sqlalchemy.column('state'), sqlalchemy.column('zip'), sqlalchemy.column('country'), sqlalchemy.column('phone'), sqlalchemy.column('contact_person'), sqlalchemy.column('defaultponotes'), sqlalchemy.column('created_at'), sqlalchemy.column('updated_at') )).values( name = name, email = email, payment_terms = payment_terms, address_line1 = address_line1, address_line2 = address_line2, city = city, state = state, zip = zip_code, country = country, phone = phone, contact_person = contact_person, defaultponotes=actual_default_po_notes_value, created_at = datetime.now(timezone.utc), updated_at = datetime.now(timezone.utc) ) 
        result = conn.execute(insert_supplier_stmt.returning(sqlalchemy.column('id')))
        inserted_supplier_id = result.fetchone()[0] 
        trans.commit() 
        print(f"DEBUG CREATE_SUPPLIER: Successfully inserted supplier with ID: {inserted_supplier_id}")
        return jsonify({"message": "Supplier created successfully", "supplier_id": inserted_supplier_id}), 201 
    except sqlalchemy.exc.IntegrityError as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG CREATE_SUPPLIER: Integrity Error: {e}")
        return jsonify({"message": f"Supplier creation failed: Duplicate entry (name or email likely already exists).", "error_type": "IntegrityError"}), 409 
    except Exception as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG CREATE_SUPPLIER: Caught unexpected exception: {e}")
        return jsonify({"message": f"Supplier creation failed: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn and not conn.closed: conn.close(); print("DEBUG CREATE_SUPPLIER: Database connection closed.")
print("DEBUG APP_SETUP: Defined /api/suppliers POST route.")

@app.route('/api/suppliers', methods=['GET'])
@verify_firebase_token 
def list_suppliers():
    print("Received request for GET /api/suppliers")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn = None 
    try:
        conn = engine.connect()
        query = sqlalchemy.text("SELECT * FROM suppliers ORDER BY name")
        result = conn.execute(query)
        suppliers_list = [dict(row._mapping) for row in result]
        for supplier_dict in suppliers_list:
            for key, value in supplier_dict.items():
                 if isinstance(value, datetime): supplier_dict[key] = value.isoformat()
        print(f"DEBUG LIST_SUPPLIERS: Found {len(suppliers_list)} suppliers.")
        return jsonify(suppliers_list), 200 
    except Exception as e:
        print(f"DEBUG LIST_SUPPLIERS: Caught unexpected exception: {e}")
        return jsonify({"message": f"Error fetching suppliers: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn and not conn.closed: conn.close(); print("DEBUG LIST_SUPPLIERS: Database connection closed.")
print("DEBUG APP_SETUP: Defined /api/suppliers GET route.")

@app.route('/api/suppliers/<int:supplier_id>', methods=['GET'])
@verify_firebase_token 
def get_supplier(supplier_id):
    print(f"Received request for GET /api/suppliers/{supplier_id}")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
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
            if isinstance(value, datetime): supplier_dict[key] = value.isoformat()
            elif isinstance(value, Decimal): supplier_dict[key] = float(value) 
        print(f"DEBUG GET_SUPPLIER: Found supplier with ID: {supplier_id}.")
        return jsonify(supplier_dict), 200 
    except Exception as e:
        print(f"DEBUG GET_SUPPLIER: Caught unexpected exception: {e}")
        return jsonify({"message": f"Error fetching supplier: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG GET_SUPPLIER: Database connection closed for ID {supplier_id}.")
print("DEBUG APP_SETUP: Defined /api/suppliers/<id> GET route.")

@app.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
@verify_firebase_token 
def update_supplier(supplier_id):
    print(f"Received request for PUT /api/suppliers/{supplier_id}")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn, trans = None, None 
    try:
        supplier_data = request.json
        print(f"DEBUG UPDATE_SUPPLIER: Received data for ID {supplier_id}: {supplier_data}")
        if not supplier_data: return jsonify({"message": "No update data provided."}), 400 
        conn = engine.connect(); trans = conn.begin()
        existing_supplier = conn.execute(sqlalchemy.text("SELECT id FROM suppliers WHERE id = :supplier_id"), {"supplier_id": supplier_id}).fetchone()
        if not existing_supplier:
            trans.rollback(); print(f"DEBUG UPDATE_SUPPLIER: Supplier ID {supplier_id} not found.")
            return jsonify({"message": f"Supplier with ID {supplier_id} not found."}), 404 
        update_fields, update_params = [], {"supplier_id": supplier_id, "updated_at": datetime.now(timezone.utc)} 
        allowed_fields = ['name', 'email', 'payment_terms', 'address_line1', 'address_line2', 'city', 'state', 'zip', 'country', 'phone', 'contact_person', 'defaultponotes'] # Added defaultponotes
        for field in allowed_fields:
            if field in supplier_data: 
                update_fields.append(f"{field} = :{field}"); update_params[field] = supplier_data[field] 
        if not update_fields:
             trans.rollback(); print(f"DEBUG UPDATE_SUPPLIER: No valid fields for ID {supplier_id}.")
             return jsonify({"message": "No valid update fields provided."}), 400 
        update_query_text = f"UPDATE suppliers SET {', '.join(update_fields)}, updated_at = :updated_at WHERE id = :supplier_id"
        conn.execute(sqlalchemy.text(update_query_text), update_params)
        trans.commit(); print(f"DEBUG UPDATE_SUPPLIER: Updated supplier ID: {supplier_id}")
        return jsonify({"message": f"Supplier with ID {supplier_id} updated successfully"}), 200 
    except sqlalchemy.exc.IntegrityError as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG UPDATE_SUPPLIER: Integrity Error: {e}")
        return jsonify({"message": f"Supplier update failed: Duplicate entry.", "error_type": "IntegrityError"}), 409 
    except Exception as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG UPDATE_SUPPLIER: Caught unexpected exception: {e}")
        return jsonify({"message": f"Supplier update failed: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG UPDATE_SUPPLIER: DB conn closed for ID {supplier_id}.")
print("DEBUG APP_SETUP: Defined /api/suppliers/<id> PUT route.")

@app.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
@verify_firebase_token 
def delete_supplier(supplier_id):
    print(f"Received request for DELETE /api/suppliers/{supplier_id}")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn, trans = None, None 
    try:
        conn = engine.connect(); trans = conn.begin()
        # Check for associated purchase orders before deleting
        check_po_sql = text("SELECT 1 FROM purchase_orders WHERE supplier_id = :supplier_id LIMIT 1")
        existing_po = conn.execute(check_po_sql, {"supplier_id": supplier_id}).fetchone()
        if existing_po:
            trans.rollback()
            print(f"DEBUG DELETE_SUPPLIER: Cannot delete supplier {supplier_id}, POs exist.")
            return jsonify({"message": "Cannot delete supplier: They are associated with existing purchase orders."}), 409

        result = conn.execute(sqlalchemy.text("DELETE FROM suppliers WHERE id = :supplier_id"), {"supplier_id": supplier_id})
        if result.rowcount == 0:
            trans.rollback(); print(f"DEBUG DELETE_SUPPLIER: Supplier ID {supplier_id} not found.")
            return jsonify({"message": f"Supplier with ID {supplier_id} not found."}), 404 
        trans.commit(); print(f"DEBUG DELETE_SUPPLIER: Deleted supplier ID: {supplier_id}")
        return jsonify({"message": f"Supplier with ID {supplier_id} deleted successfully"}), 200 
    except Exception as e: 
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG DELETE_SUPPLIER: Exception during delete: {e}")
        # Catch specific foreign key violations if other tables reference suppliers directly
        # if "violates foreign key constraint" in str(e).lower():
        #      return jsonify({"message": f"Cannot delete supplier: Integrity constraint violation.", "error_type": "ForeignKeyViolation"}), 409
        return jsonify({"message": f"Supplier deletion failed: {e}", "error_type": type(e).__name__}), 500 
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG DELETE_SUPPLIER: DB conn closed for ID {supplier_id}.")
print("DEBUG APP_SETUP: Defined /api/suppliers/<id> DELETE route.")

# === PRODUCT MAPPING CRUD ROUTES ===
@app.route('/api/products', methods=['POST'])
@verify_firebase_token
def create_product_mapping():
    print("Received request for POST /api/products")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn, trans = None, None
    try:
        product_data = request.json
        print(f"DEBUG CREATE_PRODUCT: Received data: {product_data}")
        required_fields = ['sku', 'standard_description']
        for field in required_fields:
            if not product_data or field not in product_data or not product_data[field]:
                print(f"DEBUG CREATE_PRODUCT: Missing required field: {field}")
                return jsonify({"message": f"Missing required field: {field}"}), 400
        sku, standard_description = product_data.get('sku'), product_data.get('standard_description')
        conn = engine.connect(); trans = conn.begin()
        insert_product_stmt = insert(sqlalchemy.table('products', sqlalchemy.column('sku'), sqlalchemy.column('standard_description'), sqlalchemy.column('created_at'), sqlalchemy.column('updated_at'))).values(sku=sku, standard_description=standard_description, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
        result = conn.execute(insert_product_stmt.returning(sqlalchemy.column('id')))
        inserted_product_id = result.fetchone()[0]
        trans.commit(); print(f"DEBUG CREATE_PRODUCT: Inserted product mapping ID: {inserted_product_id}")
        return jsonify({"message": "Product mapping created successfully", "product_id": inserted_product_id}), 201
    except sqlalchemy.exc.IntegrityError as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG CREATE_PRODUCT: Integrity Error: {e}")
        return jsonify({"message": "Product mapping creation failed: Duplicate SKU.", "error_type": "IntegrityError"}), 409
    except Exception as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG CREATE_PRODUCT: Unexpected exception: {e}")
        return jsonify({"message": f"Product mapping creation failed: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print("DEBUG CREATE_PRODUCT: DB connection closed.")
print("DEBUG APP_SETUP: Defined /api/products POST route.")

@app.route('/api/products', methods=['GET'])
@verify_firebase_token
def list_product_mappings():
    print("Received request for GET /api/products")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn = None
    try:
        conn = engine.connect()
        query = sqlalchemy.text("SELECT * FROM products ORDER BY sku")
        result = conn.execute(query)
        product_mappings_list = [dict(row._mapping) for row in result]
        for product_dict in product_mappings_list:
            for key, value in product_dict.items():
                 if isinstance(value, datetime): product_dict[key] = value.isoformat()
        print(f"DEBUG LIST_PRODUCTS: Found {len(product_mappings_list)} product mappings.")
        return jsonify(product_mappings_list), 200
    except Exception as e:
        print(f"DEBUG LIST_PRODUCTS: Unexpected exception: {e}")
        return jsonify({"message": f"Error fetching product mappings: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print("DEBUG LIST_PRODUCTS: DB connection closed.")
print("DEBUG APP_SETUP: Defined /api/products GET route.")

@app.route('/api/products/<int:product_id>', methods=['GET'])
@verify_firebase_token
def get_product_mapping(product_id):
    print(f"Received request for GET /api/products/{product_id}")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn = None
    try:
        conn = engine.connect()
        query = sqlalchemy.text("SELECT * FROM products WHERE id = :product_id")
        result = conn.execute(query, {"product_id": product_id}).fetchone()
        if result is None:
            print(f"DEBUG GET_PRODUCT: Product mapping ID {product_id} not found.")
            return jsonify({"message": f"Product mapping with ID {product_id} not found."}), 404
        product_dict = dict(result._mapping)
        for key, value in product_dict.items():
            if isinstance(value, datetime): product_dict[key] = value.isoformat()
        print(f"DEBUG GET_PRODUCT: Found product mapping ID: {product_id}.")
        return jsonify(product_dict), 200
    except Exception as e:
        print(f"DEBUG GET_PRODUCT: Unexpected exception: {e}")
        return jsonify({"message": f"Error fetching product mapping: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG GET_PRODUCT: DB conn closed for ID {product_id}.")
print("DEBUG APP_SETUP: Defined /api/products/<id> GET route.")

@app.route('/api/products/<int:product_id>', methods=['PUT'])
@verify_firebase_token
def update_product_mapping(product_id):
    print(f"Received request for PUT /api/products/{product_id}")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn, trans = None, None
    try:
        product_data = request.json
        print(f"DEBUG UPDATE_PRODUCT: Data for product ID {product_id}: {product_data}")
        if not product_data: return jsonify({"message": "No update data provided."}), 400
        conn = engine.connect(); trans = conn.begin()
        existing_product = conn.execute(sqlalchemy.text("SELECT id FROM products WHERE id = :product_id"), {"product_id": product_id}).fetchone()
        if not existing_product:
            trans.rollback(); print(f"DEBUG UPDATE_PRODUCT: Product mapping ID {product_id} not found.")
            return jsonify({"message": f"Product mapping with ID {product_id} not found."}), 404
        update_fields, update_params = [], {"product_id": product_id, "updated_at": datetime.now(timezone.utc)}
        allowed_fields = ['sku', 'standard_description']
        for field in allowed_fields:
            if field in product_data: update_fields.append(f"{field} = :{field}"); update_params[field] = product_data[field]
        if not update_fields:
             trans.rollback(); print(f"DEBUG UPDATE_PRODUCT: No valid fields for product ID {product_id}.")
             return jsonify({"message": "No valid update fields provided."}), 400
        update_query_text = f"UPDATE products SET {', '.join(update_fields)}, updated_at = :updated_at WHERE id = :product_id"
        conn.execute(sqlalchemy.text(update_query_text), update_params)
        trans.commit(); print(f"DEBUG UPDATE_PRODUCT: Updated product mapping ID: {product_id}")
        return jsonify({"message": f"Product mapping with ID {product_id} updated successfully"}), 200
    except sqlalchemy.exc.IntegrityError as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG UPDATE_PRODUCT: Integrity Error: {e}")
        return jsonify({"message": f"Product mapping update failed: Duplicate SKU.", "error_type": "IntegrityError"}), 409
    except Exception as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG UPDATE_PRODUCT: Unexpected exception: {e}")
        return jsonify({"message": f"Product mapping update failed: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG UPDATE_PRODUCT: DB conn closed for ID {product_id}.")
print("DEBUG APP_SETUP: Defined /api/products/<id> PUT route.")

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@verify_firebase_token
def delete_product_mapping(product_id):
    print(f"Received request for DELETE /api/products/{product_id}")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn, trans = None, None
    try:
        conn = engine.connect(); trans = conn.begin()
        result = conn.execute(sqlalchemy.text("DELETE FROM products WHERE id = :product_id"), {"product_id": product_id})
        if result.rowcount == 0:
            trans.rollback(); print(f"DEBUG DELETE_PRODUCT: Product mapping ID {product_id} not found.")
            return jsonify({"message": f"Product mapping with ID {product_id} not found."}), 404
        trans.commit(); print(f"DEBUG DELETE_PRODUCT: Deleted product mapping ID: {product_id}")
        return jsonify({"message": f"Product mapping with ID {product_id} deleted successfully"}), 200
    except Exception as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG DELETE_PRODUCT: Unexpected exception: {e}")
        # Check for specific DB errors if needed, e.g., foreign key constraints
        return jsonify({"message": f"Product mapping deletion failed: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG DELETE_PRODUCT: DB conn closed for ID {product_id}.")
print("DEBUG APP_SETUP: Defined /api/products/<id> DELETE route.")

# === LOOKUP ROUTES ===
@app.route('/api/lookup/description/<path:sku_value>', methods=['GET'])
@verify_firebase_token 
def get_description_for_sku(sku_value):
    if not sku_value: return jsonify({"description": None}), 400 
    db_conn, description = None, None
    print(f"DEBUG LOOKUP_DESC: Received request for SKU: {sku_value}")
    try:
        if engine is None: return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()
        # First, try hpe_description_mappings based on the direct SKU (which might be an option_pn)
        desc_query_1 = text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :sku")
        result_1 = db_conn.execute(desc_query_1, {"sku": sku_value}).scalar_one_or_none()
        if result_1: 
            description = result_1
            print(f"DEBUG LOOKUP_DESC: Found description in hpe_description_mappings for '{sku_value}' as option_pn.")
        else:
            # Second, try the products table with the direct SKU
            desc_query_2 = text("SELECT standard_description FROM products WHERE sku = :sku")
            result_2 = db_conn.execute(desc_query_2, {"sku": sku_value}).scalar_one_or_none()
            if result_2: 
                description = result_2
                print(f"DEBUG LOOKUP_DESC: Found description in products table for SKU '{sku_value}'.")
            else:
                # Third, if SKU is not an option_pn directly, check if it maps to one in hpe_part_mappings
                part_map_query = text("SELECT option_pn FROM hpe_part_mappings WHERE sku = :sku")
                option_pn_from_map = db_conn.execute(part_map_query, {"sku": sku_value}).scalar_one_or_none()
                if option_pn_from_map:
                    print(f"DEBUG LOOKUP_DESC: Input SKU '{sku_value}' mapped to OptionPN '{option_pn_from_map}'. Looking up description for OptionPN...")
                    desc_query_3 = text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn")
                    result_3 = db_conn.execute(desc_query_3, {"option_pn": option_pn_from_map}).scalar_one_or_none()
                    if result_3: 
                        description = result_3
                        print(f"DEBUG LOOKUP_DESC: Found description in hpe_description_mappings for mapped OptionPN '{option_pn_from_map}'.")
                    # else: print(f"DEBUG LOOKUP_DESC: No description in hpe_description_mappings for mapped OptionPN '{option_pn_from_map}'.")
                # else: print(f"DEBUG LOOKUP_DESC: SKU '{sku_value}' not found in hpe_part_mappings either.")
        
        if description is None:
            print(f"DEBUG LOOKUP_DESC: No description found for SKU '{sku_value}' after all checks.")
            return jsonify({"description": None}), 200 # Return 200 with None if not found, not 404 unless SKU itself is invalid.
        
        print(f"DEBUG LOOKUP_DESC: Final description for '{sku_value}': {description}")
        return jsonify({"description": description}), 200
    except Exception as e:
        print(f"ERROR LOOKUP_DESC: Error looking up description for SKU {sku_value}: {e}")
        traceback.print_exc() # Add traceback for better debugging
        return jsonify({"error": "Failed to lookup description", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed: 
            db_conn.close()
            print(f"DEBUG LOOKUP_DESC: DB connection closed for SKU {sku_value}.")
print("DEBUG APP_SETUP: Defined /api/lookup/description/<sku> GET route.")


# === TASK AND REPORT ROUTES ===
@app.route('/api/tasks/scheduler/trigger-iif-for-today', methods=['POST'])
def scheduler_trigger_iif_for_today():
    print("INFO APP (SCHEDULER_IIF_TODAY): Received request to trigger IIF for today from scheduler.")
    # Example of header check for Cloud Scheduler (optional, but recommended)
    # expected_header = os.getenv("CLOUD_SCHEDULER_HEADER_VALUE")
    # if request.headers.get("X-CloudScheduler-JobName") and expected_header: # Or a custom header
    #    if request.headers.get("Your-Custom-Header") != expected_header:
    #        print("WARN APP (SCHEDULER_IIF_TODAY): Invalid or missing custom header for scheduler.")
    #        return jsonify({"error": "Forbidden"}), 403
    # else: # If not called by Cloud Scheduler with expected headers (e.g. local test)
    #    print("WARN APP (SCHEDULER_IIF_TODAY): Potentially insecure call (missing scheduler headers).")

    if iif_generator is None:
        print("ERROR APP (SCHEDULER_IIF_TODAY): iif_generator module not loaded.")
        return jsonify({"error": "IIF generation module not available."}), 500
    if engine is None:
        print("ERROR APP (SCHEDULER_IIF_TODAY): Database engine not initialized.")
        return jsonify({"error": "Database engine not available."}), 500
    try:
        print("INFO APP (SCHEDULER_IIF_TODAY): Calling iif_generator.create_and_email_iif_for_today...")
        success, message = iif_generator.create_and_email_iif_for_today(engine)
        if success:
            print(f"INFO APP (SCHEDULER_IIF_TODAY): IIF for today task completed. Message: {message}")
            return jsonify({"message": message or "IIF generation task for today's POs triggered."}), 200
        else:
            print(f"ERROR APP (SCHEDULER_IIF_TODAY): IIF generation for today failed. Message: {message}")
            return jsonify({"error": message or "IIF generation for today failed in generator script."}), 500 
    except Exception as e:
        print(f"ERROR APP (SCHEDULER_IIF_TODAY): Error: {e}")
        traceback.print_exc()
        return jsonify({"error": "An error occurred during scheduled IIF generation.", "details": str(e)}), 500

# This user-triggered version should be distinct if the scheduler one has different auth.
# If both use Firebase token, one endpoint is fine. If scheduler is different, ensure paths are distinct.
# Assuming your original had two distinct POST endpoints for /api/tasks/trigger-iif-for-today, one for scheduler (no token) and one for user (with token).
# The one below is for user, with @verify_firebase_token.
@app.route('/api/tasks/trigger-iif-for-today-user', methods=['POST']) # Changed path to make it distinct
@verify_firebase_token
def user_trigger_iif_for_today(): # Renamed function
    print("INFO APP (USER_IIF_TODAY): Received request to trigger IIF for today by user.")
    if iif_generator is None: 
        return jsonify({"error": "IIF generation module not available."}), 500
    if engine is None:
        return jsonify({"error": "Database engine not available."}), 500
    try:
        success, message = iif_generator.create_and_email_iif_for_today(engine) 
        if success:
            return jsonify({"message": message or "IIF generation task for today's POs triggered and email sent (if configured)."}), 200
        else:
            return jsonify({"error": message or "IIF generation for today failed. Check logs."}), 500
    except Exception as e:
        print(f"ERROR APP (USER_IIF_TODAY): Error during IIF generation task for today: {e}")
        return jsonify({"error": "An error occurred during user-triggered IIF generation.", "details": str(e)}), 500
print("DEBUG APP_SETUP: Defined IIF trigger routes.")


@app.route('/api/reports/daily-revenue', methods=['GET'])
@verify_firebase_token 
def get_daily_revenue_report():
    print("DEBUG DAILY_REVENUE: Received request for daily revenue report.")
    db_conn = None
    try:
        if engine is None:
            print("ERROR DAILY_REVENUE: Database engine not available.")
            return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()
        print("DEBUG DAILY_REVENUE: DB connection established.")
        today_utc = datetime.now(timezone.utc).date()
        start_date_utc = today_utc - timedelta(days=13) 
        sql_query = text("""
            SELECT DATE(order_date AT TIME ZONE 'UTC') AS sale_date, SUM(total_sale_price) AS daily_revenue
            FROM orders WHERE DATE(order_date AT TIME ZONE 'UTC') >= :start_date
            GROUP BY sale_date ORDER BY sale_date DESC LIMIT 14;
        """)
        records = db_conn.execute(sql_query, {"start_date": start_date_utc}).fetchall()
        daily_revenue_data = []
        for row in records:
            row_dict = convert_row_to_dict(row) 
            if row_dict and row_dict.get('sale_date') is not None:
                daily_revenue_data.append({
                    "sale_date": row_dict['sale_date'].strftime('%Y-%m-%d'), 
                    "daily_revenue": float(row_dict.get('daily_revenue', 0.0)) 
                })
        revenue_map = {item['sale_date']: item['daily_revenue'] for item in daily_revenue_data}
        complete_daily_revenue = []
        for i in range(14): 
            current_date = today_utc - timedelta(days=i)
            current_date_str = current_date.strftime('%Y-%m-%d')
            complete_daily_revenue.append({
                "sale_date": current_date_str,
                "daily_revenue": revenue_map.get(current_date_str, 0.0)
            })
        print(f"DEBUG DAILY_REVENUE: Fetched daily revenue for last 14 days. Count: {len(complete_daily_revenue)}")
        return jsonify(make_json_safe(complete_daily_revenue)), 200
    except Exception as e:
        print(f"ERROR DAILY_REVENUE: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to fetch daily revenue report", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print("DEBUG DAILY_REVENUE: DB connection closed.")
print("DEBUG APP_SETUP: Defined /api/reports/daily-revenue GET route.")


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