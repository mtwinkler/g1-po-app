# app.py - COMPLETE FILE

import os
from flask import Flask, jsonify, request
import sqlalchemy
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector
# import bigcommerce # --- Using requests instead ---
import requests # --- NEW: Import the requests library ---
from datetime import datetime, timezone # Import datetime and timezone
from sqlalchemy.dialects.postgresql import insert # Import insert for upsert logic


# Load environment variables from .env file during local development
load_dotenv()

app = Flask(__name__)

# Database connection configuration from environment variables
db_connection_name = os.getenv("DB_CONNECTION_NAME")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
is_local = os.getenv("IS_LOCAL") == "True"

# BigCommerce API Credentials
bc_store_hash = os.getenv("BIGCOMMERCE_STORE_HASH")
bc_client_id = os.getenv("BIGCOMMERCE_CLIENT_ID")
bc_access_token = os.getenv("BIGCOMMERCE_ACCESS_TOKEN")
domestic_country_code = os.getenv("DOMESTIC_COUNTRY_CODE", "US") # Default to US

# --- NEW: BigCommerce API Base URL and Headers (Defined using requests approach) ---
if not bc_store_hash or not bc_access_token:
    print("WARNING: BigCommerce credentials not fully set in .env. API calls will fail.")
    bc_api_base_url_v2 = None # Indicate that API is not configured
    bc_headers = None
else:
    # --- Using V2 API base URL ---
    bc_api_base_url_v2 = f"https://api.bigcommerce.com/stores/{bc_store_hash}/v2/"
    bc_headers = {
        "X-Auth-Token": bc_access_token,
        "Content-Type": "application/json", # Standard practice, though 'Accept' is key for response format
        "X-Auth-Client": bc_client_id, # Include Client ID just in case
        "Accept": "application/json" # --- NEW: Request JSON Response ---
    }
    print(f"BigCommerce V2 API base URL: {bc_api_base_url_v2}")
    print("BigCommerce API headers configured.")


# --- BigCommerce Status ID for the target status (e.g., Awaiting Payment) ---
# We still need this ID from the .env file to filter the API request
bc_processing_status_id = os.getenv("BC_PROCESSING_STATUS_ID")
if not bc_processing_status_id:
    print("WARNING: BC_PROCESSING_STATUS_ID not set in .env. Cannot filter orders.")
    # Note: The ingestion endpoint will now check this before making the request


# --- Database Connection Logic ---
print(f"Attempting to connect to DB instance: {db_connection_name}")

def getconn():
    """Helper function to return a database connection using the connector."""
    with Connector() as connector:
        conn = connector.connect(
            db_connection_name,
            "pg8000",  # Database driver
            user=db_user,
            password=db_password,
            db=db_name
        )
        return conn

try:
    # Use the creator function with SQLAlchemy engine
    engine = sqlalchemy.create_engine(
        "postgresql+pg8000://",
        creator=getconn,
        pool_size=5,
        max_overflow=2,
        pool_timeout=30,
        pool_recycle=1800
    )
    print("SQLAlchemy engine created.")
except Exception as e:
    print(f"Failed to create SQLAlchemy engine: {e}")
    engine = None # Set engine to None if creation fails


# --- Basic Root Route ---
@app.route('/')
def hello_world():
    print("Received request for /")
    return 'Order Processing App Backend!'


# --- Database Connection Test Route ---
@app.route('/test_db')
def test_db_connection():
    print("Received request for /test_db")
    if engine is None:
         return jsonify({"message": "Database engine not initialized."}), 500

    try:
        with engine.connect() as conn:
            # Execute a simple query
            result = conn.execute(sqlalchemy.text("SELECT 1")).fetchone()
            if result and result[0] == 1:
                print("SELECT 1 query successful.")
                return jsonify({"message": "Database connection successful!"}), 200
            else:
                 print("SELECT 1 query returned unexpected result.")
                 return jsonify({"message": "Database query failed unexpectedly."}), 500
    except Exception as e:
        print(f"Database connection or query failed: {e}")
        return jsonify({"message": f"Database connection or query failed: {e}"}), 500


# --- API Route to List Orders from our Database ---
@app.route('/api/orders', methods=['GET'])
def list_orders():
    print(f"Received request for /api/orders with args: {request.args}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500

    try:
        with engine.connect() as conn:
            # Query to fetch orders from our database
            # Filters by our app's 'status' and 'is_international' flag based on request args

            status_filter = request.args.get('status') # Allow filtering by our internal status
            is_international_filter = request.args.get('international') # 'true', 'false', or None

            query_text = "SELECT * FROM orders"
            conditions = []
            params = {}

            if status_filter is not None:
                 conditions.append("status = :status")
                 params["status"] = status_filter

            if is_international_filter is not None:
                 conditions.append("is_international = :is_international")
                 # Convert 'true'/'false' strings from request args to boolean
                 params["is_international"] = is_international_filter.lower() == 'true'

            if conditions:
                 query_text += " WHERE " + " AND ".join(conditions)

            # Always order by BigCommerce order date for consistency, newest first
            query = sqlalchemy.text(query_text + " ORDER BY order_date DESC")

            print(f"DEBUG LIST_ORDERS: Executing query: {query_text} with params: {params}")
            result = conn.execute(query, params).fetchall()
            print(f"DEBUG LIST_ORDERS: Found {len(result)} orders.")

            # Convert results to a list of dictionaries for JSON response
            orders_list = []
            for row in result:
                order_dict = dict(row._mapping) # Access columns by name
                # Convert types for JSON serialization
                for key, value in order_dict.items():
                    if isinstance(value, datetime):
                        order_dict[key] = value.isoformat()
                    elif isinstance(value, sqlalchemy.types.Decimal):
                         order_dict[key] = str(value) # Or float(value) if preferred

                orders_list.append(order_dict)

            return jsonify(orders_list), 200

    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({"message": f"Error fetching orders: {e}"}), 500


# --- Route to Ingest Orders from BigCommerce using requests (Final Refinement) ---
@app.route('/ingest_orders', methods=['POST'])
def ingest_orders():
    print("Received request for /ingest_orders")
    # Check if API is configured
    if not bc_api_base_url_v2 or not bc_headers: # Check V2 base URL
        print("Ingestion Error: BigCommerce API credentials not fully configured.")
        return jsonify({"message": "BigCommerce API credentials not fully configured."}), 500

    # Check if target status ID is set and valid
    try:
        target_status_id = int(bc_processing_status_id)
        print(f"DEBUG INGEST: Target BigCommerce status ID for ingestion is '{target_status_id}'.")
    except (ValueError, TypeError):
        print(f"Ingestion Error: BC_PROCESSING_STATUS_ID '{bc_processing_status_id}' is not a valid integer in .env.")
        return jsonify({"message": f"BC_PROCESSING_STATUS_ID '{bc_processing_status_id}' is not a valid integer in .env."}), 500

    if engine is None:
        print("Ingestion Error: Database engine not initialized.")
        return jsonify({"message": "Database engine not initialized."}), 500

    conn = None # Initialize connection variable to None
    trans = None # Initialize transaction variable to None

    try:
        # --- Make API call using requests to V2 endpoint (list) ---
        orders_endpoint = f"{bc_api_base_url_v2}orders" # --- Use V2 base URL ---
        # Parameters for the API call
        api_params = {
            'status_id': target_status_id, # Filter directly by Status ID using the correct ID
            'sort': 'date_created:asc',
            'limit': 250 # Fetch a reasonable limit
            # Consider adding a date filter here
        }

        print(f"DEBUG INGEST: Making requests GET call to {orders_endpoint} (V2 list) with params: {api_params}")
        response = requests.get(orders_endpoint, headers=bc_headers, params=api_params)

        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        # --- DEBUG PRINTS for response inspection ---
        print(f"DEBUG INGEST: requests response status code: {response.status_code}")
        print(f"DEBUG INGEST: requests response headers: {response.headers}")
        # print(f"DEBUG INGEST: requests raw response text (preview): {response.text[:500]}...") # Comment out raw text print for cleaner output
        # --- END DEBUG PRINTS ---

        # Parse the JSON response (expecting list for V2)
        orders_list = response.json()

        # BigCommerce API V2 returns a list directly
        if not isinstance(orders_list, list): # Check if the top level is a list
            print(f"DEBUG INGEST: BigCommerce API response was not a list as expected for V2 list call. Received type: {type(orders_list)}. Response keys: {orders_list.keys() if isinstance(orders_list, dict) else 'Not a dict'}. Full response: {response.text[:500]}...")
            return jsonify({"message": "Ingestion failed: Unexpected API response format (expected list for V2 list)."}), 500

        # --- START DEBUG PRINTS ---
        print(f"DEBUG INGEST: requests V2 list API call successful. Received {len(orders_list)} orders.")
        # Preview the first few items as dictionaries
        print(f"DEBUG INGEST: orders_list (first 5 items): {str(orders_list[:5])[:1000] + '...' if len(str(orders_list[:5])) > 1000 else str(orders_list[:5])}")


        if len(orders_list) == 0:
             print("DEBUG INGEST: orders_list is empty (no matching orders for this status).")
             return jsonify({"message": f"Successfully ingested 0 orders with BigCommerce status ID '{target_status_id}' (API returned no matching orders)."}), 200

        # --- END DEBUG PRINTS ---


        ingested_count = 0 # Count items processed and attempted insertion/update
        inserted_count_this_run = 0 # Count new items inserted this run


        # Open connection and start transaction *after* successful API call and data check
        conn = engine.connect()
        trans = conn.begin() # Start transaction


        # --- Loop through the list of order dictionaries ---
        for i, bc_order_summary in enumerate(orders_list): # Iterate directly over the list of dictionaries (calling them summary now)
            print(f"\nDEBUG INGEST LOOP: --- Processing item {i} (Order ID: {bc_order_summary.get('id', 'N/A')}) ---")
            print(f"DEBUG INGEST LOOP: Type: {type(bc_order_summary)}")

            # --- Data Extraction from the summary dictionary (from V2 list call) ---
            if not isinstance(bc_order_summary, dict):
                 print(f"DEBUG INGEST LOOP: Item {i} is NOT a dictionary as expected from V2 list. Content: {str(bc_order_summary)[:200]}... Skipping this item.")
                 continue # Should not happen if API response format is correct

            order_id = bc_order_summary.get('id')
            if order_id is None:
                 print(f"DEBUG INGEST LOOP: Skipping item {i} because order ID is missing in summary.")
                 continue

            order_status_id = bc_order_summary.get('status_id')
            order_status_name = bc_order_summary.get('status')
            print(f"DEBUG INGEST LOOP: Summary Order ID: {order_id}, Status ID: {order_status_id}, Status Name: {order_status_name}")


            # Check if order already exists using bigcommerce_order_id
            existing_order = conn.execute(
                sqlalchemy.text("SELECT id, status, is_international FROM orders WHERE bigcommerce_order_id = :bc_order_id"),
                {"bc_order_id": order_id}
            ).fetchone()


            # --- Fetch FULL details from V2 /orders/{id} and SUB-RESOURCES ---
            customer_shipping_address = {} # Initialize address dict for data extraction
            shipping_method_name = 'N/A' # Default value for shipping method

            try:
                print(f"DEBUG INGEST LOOP: Fetching full V2 details and sub-resources for Order {order_id}...")

                # Fetch base V2 order details (might not include everything, but good check)
                # full_bc_order_v2_response = requests.get(f"{bc_api_base_url_v2}orders/{order_id}", headers=bc_headers)
                # full_bc_order_v2_response.raise_for_status()
                # full_order_data = full_bc_order_v2_response.json()
                # print(f"DEBUG INGEST: Fetched base details for Order {order_id} from V2.")

                # Fetch Shipping Addresses (V2 Sub-resource)
                shipping_addresses_v2_response = requests.get(f"{bc_api_base_url_v2}orders/{order_id}/shippingaddresses", headers=bc_headers)
                shipping_addresses_v2_response.raise_for_status()
                shipping_addresses_list = shipping_addresses_v2_response.json() # Expecting a list of address dicts

                print(f"DEBUG INGEST: Fetched {len(shipping_addresses_list)} shipping addresses for Order {order_id} from V2 sub-resource.")

                if shipping_addresses_list and isinstance(shipping_addresses_list, list) and len(shipping_addresses_list) > 0 and isinstance(shipping_addresses_list[0], dict):
                     customer_shipping_address = shipping_addresses_list[0] # Get the first shipping address
                     shipping_country_code = customer_shipping_address.get('country_code')
                     print(f"DEBUG INGEST: V2 Shipping Address found. First address type: {type(customer_shipping_address)}. Country: {shipping_country_code}")

                     if shipping_country_code and shipping_country_code != domestic_country_code:
                          is_international = True
                     else:
                          is_international = False
                else:
                    print(f"DEBUG INGEST: V2 Shipping Address sub-resource for Order {order_id} returned no addresses or unexpected format. Marking domestic for now.")
                    is_international = False # Assume domestic if address data isn't clear
                    # If no shipping address is present or valid, we probably cannot process this order for shipping
                    continue # Skip insertion if no valid shipping address found


                # Fetch Products (Line Items) (V2 Sub-resource)
                products_v2_response = requests.get(f"{bc_api_base_url_v2}orders/{order_id}/products", headers=bc_headers)
                products_v2_response.raise_for_status()
                products_list = products_v2_response.json() # Expecting a list of product dicts

                print(f"DEBUG INGEST: Fetched {len(products_list)} products for Order {order_id} from V2 sub-resource.")

                # Determine Shipping Method Name (Often in the main order object or shipping address)
                # In V2 /orders list, 'shipping_cost_inc_tax', etc are present.
                # Shipping method *name* might be in the main /orders/{id} response or a separate endpoint.
                # Let's try to get it from the main order object fetched earlier (bc_order_summary) if present
                shipping_method_name = bc_order_summary.get('shipping_method', 'N/A')
                print(f"DEBUG INGEST: Determined shipping_method_name (from summary): {shipping_method_name}")


            except requests.exceptions.RequestException as get_error:
                print(f"DEBUG INGEST LOOP: !!! Could not fetch V2 details or sub-resources for Order {order_id}: {get_error}. Skipping insertion of this order.")
                continue # Skip this order if fetching full details fails


            # --- End Fetching FULL details ---


            # Determine the target status in OUR app based on whether it's international
            target_app_status = 'international_manual' if is_international else 'new'


            if existing_order:
                 # --- Handle existing orders that match the target status ---
                 print(f"DEBUG INGEST LOOP: Order {order_id} already exists in our DB (App ID: {existing_order['id']}). Checking for updates.")

                 # Check if an update is needed based on international status OR if the internal status doesn't match the target status
                 needs_update = False
                 update_params = {"id": existing_order['id']}

                 if existing_order['is_international'] != is_international or existing_order['status'] != target_app_status:
                     needs_update = True
                     update_params['is_international'] = is_international
                     update_params['status'] = target_app_status

                 if needs_update:
                     update_params['updated_at'] = datetime.now(timezone.utc) # Use timezone aware datetime for consistency
                     update_stmt = sqlalchemy.text(
                          f"UPDATE orders SET is_international = :is_international, status = :status, updated_at = :updated_at WHERE id = :id"
                     )
                     conn.execute(update_stmt, update_params)
                     print(f"DEBUG INGEST: Updated existing Order {order_id} (App ID: {existing_order['id']}) to status='{update_params['status']}', is_international={update_params['is_international']}.")
                 else:
                      print(f"DEBUG INGEST: Order {order_id} already in DB with correct status/flag for processing (no update needed).")

                 # No need to fetch full details or insert line items again for existing orders in this loop.
                 ingested_count += 1 # Count as processed/checked
                 continue # Skip to the next order in the loop


            else:
                # Order does not exist, INSERT it
                # --- Use data from the V2 sub-resource fetches for insertion ---
                print(f"DEBUG INGEST LOOP: Order {order_id} does not exist in our DB. Inserting from V2 data...")

                # We already fetched shipping addresses and products lists above
                # customer_shipping_address and products_list are available


                # --- START of INSERT statement for 'orders' table using V2 data ---
                insert_order_stmt = insert(sqlalchemy.table(
                    'orders', # Table name string
                    ( # <-- OPENING PARENTHESIS FOR TUPLE OF COLUMNS
                        sqlalchemy.column('bigcommerce_order_id'),
                        sqlalchemy.column('customer_name'),
                        sqlalchemy.column('customer_shipping_address_line1'),
                        sqlalchemy.column('customer_shipping_address_line2'),
                        sqlalchemy.column('customer_shipping_city'),
                        sqlalchemy.column('customer_shipping_state'),
                        sqlalchemy.column('customer_shipping_zip'),
                        sqlalchemy.column('customer_shipping_country'),
                        sqlalchemy.column('customer_phone'),
                        sqlalchemy.column('customer_email'), # Email from main order object (V2 list or V2 detail)
                        sqlalchemy.column('customer_shipping_method'), # Method name from main order object or address
                        sqlalchemy.column('customer_notes'), # Notes from main order object
                        sqlalchemy.column('order_date'), # From main order object
                        sqlalchemy.column('total_sale_price'), # From main order object
                        sqlalchemy.column('status'), # Our app status
                        sqlalchemy.column('is_international'), # Our flag
                        sqlalchemy.column('created_at'),
                        sqlalchemy.column('updated_at')
                    ) # <-- CLOSING PARENTHESIS FOR TUPLE OF COLUMNS
                )).values( # <-- CLOSING PARENTHESIS for sqlalchemy.table(), OPENING PARENTHESIS for .values()
                    # --- Start of list of value assignments (key=value, separated by commas) ---
                    bigcommerce_order_id = order_id, # Use the extracted order_id from summary

                    # Extract data from the customer_shipping_address dictionary (from V2 sub-resource)
                    customer_name = customer_shipping_address.get('first_name', '') + ' ' + customer_shipping_address.get('last_name', ''),
                    customer_shipping_address_line1 = customer_shipping_address.get('street_1', 'N/A'),
                    customer_shipping_address_line2 = customer_shipping_address.get('street_2', None),
                    customer_shipping_city = customer_shipping_address.get('city', 'N/A'),
                    customer_shipping_state = customer_shipping_address.get('state', 'N/A'),
                    customer_shipping_zip = customer_shipping_address.get('zip', 'N/A'),
                    customer_shipping_country = customer_shipping_address.get('country_code', 'N/A'),
                    customer_phone = customer_shipping_address.get('phone', None), # Get phone from shipping address (if present)


                    customer_email = bc_order_summary.get('customer_email', None), # Email from V2 list summary
                    customer_shipping_method = shipping_method_name, # <--- Use the variable defined BEFORE this block

                    customer_notes = bc_order_summary.get('customer_message', None), # Notes from V2 list summary
                    order_date = datetime.strptime(bc_order_summary['date_created'], '%a, %d %b %Y %H:%M:%S %z').replace(tzinfo=timezone.utc) if bc_order_summary.get('date_created') else datetime.now(timezone.utc), # Safely parse V2 date format
                    total_sale_price = bc_order_summary.get('total_inc_tax', 0.00), # From V2 list summary
                    status = target_app_status, # Use the target status ('new' or 'international_manual')
                    is_international = is_international, # Use the flag determined from V2 shipping address fetch
                    created_at = datetime.now(timezone.utc),
                    updated_at = datetime.now(timezone.utc)
                    # --- End of list of value assignments ---
                ) # <--- CLOSING PARENTHESIS FOR .values()
                # --- END of corrected INSERT statement for 'orders' table ---


                # Execute the insert statement for the order and get its primary key
                try:
                     inserted_order_id = conn.execute(insert_order_stmt).fetchone()[0]
                     print(f"DEBUG INGEST: Inserted new Order {order_id} with app ID {inserted_order_id}, status: {target_app_status}")
                     inserted_count_this_run += 1 # Count actual insertions
                except Exception as db_insert_error:
                      print(f"DEBUG INGEST: !!! Error inserting Order {order_id} into DB: {db_insert_error}. Skipping line items and moving to next order.")
                      continue # Skip line item insertion and move to next order


                # --- Insert line items from the V2 sub-resource fetch ---
                if products_list and isinstance(products_list, list): # Check if products list from V2 sub-resource is non-empty
                    print(f"DEBUG INGEST LOOP: Found products list from V2 sub-resource for Order {order_id}. Attempting to insert line items...")
                    for item in products_list:
                         # Use insert(table).values(...) syntax
                         insert_item_stmt = insert(sqlalchemy.table(
                            'order_line_items',
                            sqlalchemy.column('order_id'),
                            sqlalchemy.column('bigcommerce_line_item_id'),
                            sqlalchemy.column('sku'),
                            sqlalchemy.column('name'),
                            sqlalchemy.column('quantity'),
                            sqlalchemy.column('sale_price'),
                            sqlalchemy.column('created_at'),
                            sqlalchemy.column('updated_at')
                         )).values(
                            order_id = inserted_order_id, # Use the ID of the newly inserted order
                            bigcommerce_line_item_id = item.get('id'), # Use item.get('id')
                            sku = item.get('sku', 'N/A'), # SKU should be available in V2 product item
                            name = item.get('name', 'N/A'), # Name should be available
                            quantity = item.get('quantity', 0),
                            sale_price = item.get('price', 0.00), # Use item.get('price') - confirm price field in V2 product item
                            created_at = datetime.now(timezone.utc),
                            updated_at = datetime.now(timezone.utc)
                         )
                         try:
                             conn.execute(insert_item_stmt)
                         except Exception as item_insert_error:
                             print(f"DEBUG INGEST: !!! Error inserting line item for Order {order_id}: {item_insert_error}. Skipping this line item.")
                             # Continue with the next line item or order

                    print(f"DEBUG INGEST: Attempted inserting line items from V2 sub-resource for Order {order_id}.")
                else:
                    print(f"DEBUG INGEST LOOP: No valid products list found in V2 sub-resource for Order {order_id} or it's empty.")


                ingested_count += 1 # Count as processed/attempted insertion

        # --- Successful Completion Returns Here ---
        trans.commit() # Commit the transaction if all orders processed without error
        print(f"DEBUG INGEST: Transaction committed.")
        return jsonify({"message": f"Successfully processed {ingested_count} items from API response and inserted {inserted_count_this_run} new orders with BigCommerce status ID '{target_status_id}'."}), 200


    except requests.exceptions.RequestException as req_e:
         # Handle errors specifically from the requests library (e.g., connection errors, bad status codes)
         print(f"DEBUG INGEST: Caught requests exception: {req_e}")
         error_message = f"BigCommerce API Request failed: {req_e}"
         status_code = req_e.response.status_code if req_e.response is not None else 'N/A'
         response_text = req_e.response.text if req_e.response is not None else 'N/A'
         print(f"DEBUG INGEST: Status Code: {status_code}, Response Body: {response_text[:500]}...")

         # Rollback the transaction if it was started
         if conn and trans:
            try:
                trans.rollback()
                print("DEBUG INGEST: Transaction rolled back due to requests error.")
            except Exception as rollback_err:
                print(f"DEBUG INGEST: Error attempting transaction rollback after requests error: {rollback_err}")

         return jsonify({
             "message": error_message,
             "error_type": type(req_e).__name__,
             "status_code": status_code,
             "response_body_preview": response_text[:500]
         }), 500 # Use a status code reflective of the API failure, 500 is fine for now


    except Exception as e:
        # Handle any other unexpected errors (database, logic errors, etc.)
        print(f"DEBUG INGEST: Caught unexpected exception during processing: {e}")
        # Check if connection and transaction objects exist and try rollback
        if conn and trans:
            try:
                trans.rollback() # Attempt to roll back
                print("DEBUG INGEST: Transaction rolled back due to unexpected error.")
            except Exception as rollback_err:
                print(f"DEBUG INGEST: Error attempting transaction rollback after unexpected error: {rollback_err}")

        print(f"Error during order ingestion: {e}")
        return jsonify({"message": f"Error during order ingestion: {e}", "error_type": type(e).__name__}), 500
    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print("DEBUG INGEST: Database connection closed.")


# --- Entry point for running the Flask app ---
# This block ensures app.run() is only called when the script is executed directly
if __name__ == '__main__':
    print("Starting Flask development server...")
    # Ensure debug=True is off in production for security
    app.run(debug=True, host='127.0.0.1', port=8080)