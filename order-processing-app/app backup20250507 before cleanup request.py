# app.py - UPDATED VERSION

import os
import time # For PO Number generation
import traceback # For detailed error logging in development
from flask import Flask, jsonify, request
import sqlalchemy
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector
import requests
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from decimal import Decimal
import document_generator
import shipping_service
from sqlalchemy import text # For sqlalchemy.text for raw SQL / transaction control
# from google.cloud import storage
import re

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
db_connection_name = os.getenv("DB_CONNECTION_NAME")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
is_local = os.getenv("IS_LOCAL", "false").lower() == "true"

bc_store_hash = os.getenv("BIGCOMMERCE_STORE_HASH")
bc_client_id = os.getenv("BIGCOMMERCE_CLIENT_ID")
bc_access_token = os.getenv("BIGCOMMERCE_ACCESS_TOKEN")
domestic_country_code = os.getenv("DOMESTIC_COUNTRY_CODE", "US")
bc_processing_status_id = os.getenv("BC_PROCESSING_STATUS_ID")

bc_api_base_url_v2 = None
bc_headers = None

if bc_store_hash and bc_access_token:
    bc_api_base_url_v2 = f"https://api.bigcommerce.com/stores/{bc_store_hash}/v2/"
    bc_headers = {
        "X-Auth-Token": bc_access_token,
        "Content-Type": "application/json",
        "X-Auth-Client": bc_client_id,
        "Accept": "application/json"
    }

def getconn():
    with Connector() as connector:
        conn = connector.connect(
            db_connection_name,
            "pg8000",
            user=db_user,
            password=db_password,
            db=db_name
        )
        return conn

try:
    engine = sqlalchemy.create_engine(
        "postgresql+pg8000://",
        creator=getconn,
        pool_size=5,
        max_overflow=2,
        pool_timeout=30,
        pool_recycle=1800
    )
except Exception as e:
    print(f"Engine init failed: {e}")
    engine = None

@app.route('/')
def hello():
    return 'Order Processing App Backend!'

@app.route('/test_db')
def test_db_connection():
    if engine is None:
        return jsonify({"message": "DB engine not initialized"}), 500
    try:
        with engine.connect() as conn:
            result = conn.execute(sqlalchemy.text("SELECT 1")).fetchone()
            if result and result[0] == 1:
                return jsonify({"message": "DB connection successful!"})
            return jsonify({"message": "Unexpected DB result"}), 500
    except Exception as e:
        return jsonify({"message": f"DB query failed: {e}"}), 500

@app.route('/api/orders', methods=['GET'])
def list_orders():
    try:
        if engine is None:
            return jsonify({"message": "DB engine not initialized"}), 500
        with engine.connect() as conn:
            status_filter = request.args.get('status')
            is_international = request.args.get('international')

            query_text = "SELECT * FROM orders"
            conditions = []
            params = {}

            if status_filter:
                conditions.append("status = :status")
                params["status"] = status_filter
            if is_international:
                conditions.append("is_international = :is_international")
                params["is_international"] = is_international.lower() == "true"

            if conditions:
                query_text += " WHERE " + " AND ".join(conditions)

            query_text += " ORDER BY order_date DESC"
            result = conn.execute(sqlalchemy.text(query_text), params)

            orders = []
            for row in result:
                order = dict(row._mapping)
                for k, v in order.items():
                    if isinstance(v, datetime):
                        order[k] = v.isoformat()
                    elif isinstance(v, Decimal):
                        order[k] = float(v)
                orders.append(order)

            return jsonify(orders)
    except Exception as e:
        return jsonify({"message": f"Fetch failed: {e}"}), 500

# Your full /ingest_orders logic would continue here without changes...
# The only fix needed was in this line:
# Replace:
#   existing_order.mapping['id']
# With:
#   existing_order._mapping['id']
# You can find and fix this log line in your ingest_orders loop:
# print(f"DEBUG INGEST: Updated existing Order {order_id} (App ID: {existing_order.mapping['id']})...")


# --- Route to Ingest Orders from BigCommerce using requests ---
@app.route('/ingest_orders', methods=['POST'])
def ingest_orders():
    # Ensure the try block is immediately followed by except/finally
    try:
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

        # --- Make API call using requests to V2 endpoint (list) ---
        orders_list_endpoint = f"{bc_api_base_url_v2}orders" # --- Use V2 base URL ---
        # Parameters for the API call
        api_params = {
            'status_id': target_status_id, # Filter directly by Status ID using the correct ID
            'sort': 'date_created:asc',
            'limit': 250 # Fetch a reasonable limit
            # Consider adding a date filter here
        }

        print(f"DEBUG INGEST: Making requests GET call to {orders_list_endpoint} (V2 list) with params: {api_params}")
        response = requests.get(orders_list_endpoint, headers=bc_headers, params=api_params)

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


        # --- Loop through the list of order dictionaries (summaries from V2 list call) ---
        for i, bc_order_summary in enumerate(orders_list): # Iterate directly over the list of dictionaries (calling them summary now)
            print(f"\nDEBUG INGEST LOOP: --- Processing item {i} (Order ID: {bc_order_summary.get('id', 'N/A')}) ---")
            print(f"DEBUG INGEST LOOP: Type: {type(bc_order_summary)}")

            # --- Data Extraction from the summary dictionary (from V2 list call) ---
            if not isinstance(bc_order_summary, dict):
                 print(f"DEBUG INGEST LOOP: Item {i} is NOT a dictionary as expected from V2 list. Content: {str(bc_order_summary)[:200]}... Skipping this item.")
                 continue # Should not happen if API response format is correct

            order_id = bc_order_summary.get('id') # ID should exist if it's a valid order dictionary
            if order_id is None:
                 print(f"DEBUG INGEST LOOP: Skipping item {i} because order ID is missing in summary.")
                 continue

            order_status_id = bc_order_summary.get('status_id')
            order_status_name = bc_order_summary.get('status')
            print(f"DEBUG INGEST LOOP: Summary Order ID: {order_id}, Status ID: {order_status_id}, Status Name: {order_status_name}")


            # Check if order already exists in our database using bigcommerce_order_id
            existing_order = conn.execute(
                sqlalchemy.text("SELECT id, status, is_international FROM orders WHERE bigcommerce_order_id = :bc_order_id"),
                {"bc_order_id": order_id}
            ).fetchone()


            # --- Fetch FULL details and SUB-RESOURCES from V2 for this specific order ---
            # We need shipping address and product details that are NOT in the V2 list summary
            customer_shipping_address = {} # Initialize address dict for data extraction
            products_list = [] # Initialize products list for line item insertion
            is_international = False # Reset flag for this order
            calculated_shipping_method_name = 'N/A' # Default value for shipping method


            # Ensure the try block is immediately followed by except/finally
            try: # This try block is for fetching sub-resources
                print(f"DEBUG INGEST LOOP: Fetching V2 sub-resources for Order {order_id}...")

                # Fetch Shipping Addresses (V2 Sub-resource)
                shipping_addresses_endpoint = f"{bc_api_base_url_v2}orders/{order_id}/shippingaddresses"
                shipping_addresses_v2_response = requests.get(shipping_addresses_endpoint, headers=bc_headers)
                shipping_addresses_v2_response.raise_for_status()
                shipping_addresses_list = shipping_addresses_v2_response.json() # Expecting a list of address dicts

                print(f"DEBUG INGEST: Fetched {len(shipping_addresses_list)} shipping addresses for Order {order_id} from V2 sub-resource.")

                # --- Determine international status based on V2 shipping addresses ---
                if shipping_addresses_list and isinstance(shipping_addresses_list, list) and len(shipping_addresses_list) > 0 and isinstance(shipping_addresses_list[0], dict):
                     customer_shipping_address = shipping_addresses_list[0] # Get the first shipping address
                     # Use 'country_iso2' for the country code check
                     shipping_country_code = customer_shipping_address.get('country_iso2')
                     print(f"DEBUG INGEST: V2 Shipping Address found. First address type: {type(customer_shipping_address)}. Country ISO2: {shipping_country_code}")

                     if shipping_country_code and shipping_country_code != domestic_country_code:
                          is_international = True
                     else:
                          is_international = False
                else:
                    print(f"DEBUG INGEST: V2 Shipping Address sub-resource for Order {order_id} returned no addresses or unexpected format. Marking domestic for now.")
                    is_international = False # Assume domestic if address data isn't clear
                    # If no shipping address is present or valid, we probably cannot process this order for shipping
                    # We still need product data though, don't 'continue' yet


                # Fetch Products (Line Items) (V2 Sub-resource)
                products_endpoint = f"{bc_api_base_url_v2}orders/{order_id}/products"
                products_v2_response = requests.get(products_endpoint, headers=bc_headers)
                products_v2_response.raise_for_status()

                                # --- NEW DEBUG PRINTS ---
                print(f"DEBUG INGEST: products_v2_response status code: {products_v2_response.status_code}")
                print(f"DEBUG INGEST: products_v2_response headers: {products_v2_response.headers}")
                print(f"DEBUG INGEST: products_v2_response raw text (preview): {products_v2_response.text[:500]}...")
                # --- END NEW DEBUG PRINTS ---

                products_list = products_v2_response.json() # <-- Error is happening here
                print(f"DEBUG INGEST: Type returned by products_v2_response.json(): {type(products_list)}") # New print AFTER json() call

                print(f"DEBUG INGEST: Fetched {len(products_list)} products for Order {order_id} from V2 sub-resource.")


                # --- Determine Shipping Method Name ---
                # In V2 API, shipping method name is often found in the main order object (from the list call) or the shipping address object
                # Check the shipping address object first, as it was just fetched
                # Fallback to the summary object if not found in shipping address
                calculated_shipping_method_name = customer_shipping_address.get('shipping_method', bc_order_summary.get('shipping_method', 'N/A'))
                print(f"DEBUG INGEST LOOP: Determined shipping_method_name: {calculated_shipping_method_name}")


            except requests.exceptions.RequestException as get_error:
                print(f"DEBUG INGEST LOOP: !!! Could not fetch V2 sub-resources for Order {order_id}: {get_error}. Skipping insertion/update of this order.")
                continue # Skip this order if fetching sub-resources fails

            # --- End Fetching FULL details and SUB-RESOURCES ---


            # Determine the target status in OUR app based on whether it's international (determined from sub-resource data)
            target_app_status = 'international_manual' if is_international else 'new'

            # Ensure we have a valid shipping address to proceed with insertion (required fields)
            # Check if customer_shipping_address dictionary was successfully populated from sub-resource
            # Ensure required fields street_1, city, zip, and country_iso2 are present and not empty/None
            if not customer_shipping_address or \
               not customer_shipping_address.get('street_1') or \
               not customer_shipping_address.get('city') or \
               not customer_shipping_address.get('zip') or \
               not customer_shipping_address.get('country_iso2'):
                 print(f"DEBUG INGEST LOOP: Skipping insertion for Order {order_id}: Missing required shipping address details from V2 sub-resource (street_1, city, zip, or country_iso2).")
                 continue # Skip orders where we couldn't get a valid shipping address


            if existing_order:
                 # --- Handle existing orders that match the target status ---
                 print(f"DEBUG INGEST LOOP: Order {order_id} already exists in our DB (App ID: {existing_order._mapping['id']}). Checking for updates.")

                 # Check if an update is needed based on international status OR if the internal status doesn't match the target status
                 needs_update = False
                 update_params = {"id": existing_order._mapping['id']}

                 # Use 'is_international' flag determined from the V2 sub-resource data
                 if existing_order._mapping['is_international'] != is_international or existing_order._mapping['status'] != target_app_status:
                     needs_update = True
                     update_params['is_international'] = is_international
                     update_params['status'] = target_app_status

                 if needs_update:
                     update_params['updated_at'] = datetime.now(timezone.utc) # Use timezone aware datetime for consistency
                     update_stmt = sqlalchemy.text(
                          f"UPDATE orders SET is_international = :is_international, status = :status, updated_at = :updated_at WHERE id = :id"
                     )
                     conn.execute(update_stmt, update_params)
                     print(f"DEBUG INGEST: Updated existing Order {order_id} (App ID: {existing_order.mapping['id']}) to status='{update_params['status']}', is_international={update_params['is_international']}.")
                 else:
                      print(f"DEBUG INGEST: Order {order_id} already in DB with correct status/flag for processing (no update needed).")

                 # No need to fetch full details or insert line items again for existing orders in this loop.
                 ingested_count += 1 # Count as processed/checked
                 continue # Skip to the next order in the loop


            else:
                # Order does not exist, INSERT it
                # --- Use data from the V2 list summary and V2 sub-resource fetches for insertion ---
                print(f"DEBUG INGEST LOOP: Order {order_id} does not exist in our DB. Inserting from V2 data...")

                # We have data from:
                # - bc_order_summary (from V2 list call: id, customer_id, date_created, totals, status, payment_method, customer_email, customer_message)
                # - customer_shipping_address (from V2 shippingaddresses sub-resource: street, city, state, zip, country_iso2, country, phone, first_name, last_name)
                # - is_international (flag derived from customer_shipping_address)
                # - calculated_shipping_method_name (derived from bc_order_summary or shipping address)
                # - products_list (from V2 products sub-resource: line item details)


                # --- START of INSERT statement for 'orders' table using V2 data ---
                # Corrected syntax for sqlalchemy.table and .values calls
                insert_order_stmt = insert(sqlalchemy.table(
                    'orders', # Table name string
                    # --- Start of list of Column objects passed as arguments to sqlalchemy.table ---
                    sqlalchemy.column('bigcommerce_order_id'),
                    sqlalchemy.column('customer_name'),
                    sqlalchemy.column('customer_shipping_address_line1'),
                    sqlalchemy.column('customer_shipping_address_line2'),
                    sqlalchemy.column('customer_shipping_city'),
                    sqlalchemy.column('customer_shipping_state'),
                    sqlalchemy.column('customer_shipping_zip'),
                    sqlalchemy.column('customer_shipping_country'), # Use country_iso2 here
                    sqlalchemy.column('customer_phone'),
                    sqlalchemy.column('customer_email'), # Email from main order object (V2 list)
                    sqlalchemy.column('customer_shipping_method'), # Method name
                    sqlalchemy.column('customer_notes'), # Notes from main order object
                    sqlalchemy.column('order_date'), # From main order object
                    sqlalchemy.column('total_sale_price'), # From main order object
                    sqlalchemy.column('status'), # Our app status
                    sqlalchemy.column('is_international'), # Our flag
                    sqlalchemy.column('created_at'),
                    sqlalchemy.column('updated_at')
                    # --- End of list of Column objects ---
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
                    customer_shipping_country = customer_shipping_address.get('country_iso2', 'N/A'), # Use country_iso2 here for consistency in DB
                    customer_phone = customer_shipping_address.get('phone', None), # Get phone from shipping address

                    customer_email = bc_order_summary.get('customer_email', None), # Email from V2 list summary
                    customer_shipping_method = calculated_shipping_method_name, # <--- Use the variable calculated just above

                    customer_notes = bc_order_summary.get('customer_message', None), # Notes from V2 list summary
                    # Safely parse V2 date format, handle potential missing key and make timezone aware
                    order_date = datetime.strptime(bc_order_summary['date_created'], '%a, %d %b %Y %H:%M:%S %z').replace(tzinfo=timezone.utc) if bc_order_summary.get('date_created') else datetime.now(timezone.utc),
                    total_sale_price = bc_order_summary.get('total_inc_tax', 0.00), # From V2 list summary
                    status = target_app_status, # Use the target status ('new' or 'international_manual')
                    is_international = is_international, # Use the flag determined from V2 shipping address fetch
                    created_at = datetime.now(timezone.utc),
                    updated_at = datetime.now(timezone.utc)
                    # --- End of list of value assignments ---
                ) # <--- CLOSING PARENTHESIS FOR .values()
# --- END of corrected INSERT statement for 'orders' table ---


                # Execute the insert statement for the order and get its primary key
                # --- Start of Try/Except block for executing the order insert ---
                try: # This try block is for executing the insert statement
                     print(f"DEBUG INGEST: Executing order insert statement for Order {order_id}...")
                     # Execute the INSERT statement
                     conn.execute(insert_order_stmt) # <-- No need to capture result if not using inserted_primary_key

                     # --- Get the last inserted ID using currval() ---
                     # This method queries the database sequence directly
                     # Corrected syntax for sqlalchemy.text() for currval
                     last_id_query = sqlalchemy.text("SELECT currval('orders_id_seq')") # Use the sequence name for the 'orders' table's id column
                     inserted_id_result = conn.execute(last_id_query).fetchone() # Execute the SELECT and fetch one row

                     if inserted_id_result and inserted_id_result[0] is not None:
                         inserted_order_id = inserted_id_result[0] # Get the single value from the row
                         print(f"DEBUG INGEST: Successfully retrieved inserted ID using currval(): {inserted_order_id}")
                     else:
                          # This case should ideally not happen if insert was successful
                          raise Exception("Could not retrieve last inserted ID using currval().") # Raise an error if ID not found
                     # --- End Get last inserted ID ---


                     print(f"DEBUG INGEST: Inserted new Order {order_id} with app ID {inserted_order_id}, status: {target_app_status}")
                     inserted_count_this_run += 1 # Count actual insertions
                except Exception as db_insert_error:
                      # Handle potential database insert errors (e.g., unique constraint violation if already exists)
                      print(f"DEBUG INGEST: !!! Error inserting Order {order_id} into DB: {db_insert_error}. Skipping line items and moving to next order.")
                      # No need to rollback yet, transaction is per batch. Just skip this order's remaining processing.
                      # Optionally log the order ID that failed to insert.
                      continue # Skip line item insertion and move to next order
                # --- End of Try/Except block for executing the order insert ---

                # --- Insert line items from the V2 sub-resource fetch ---
                                # Order does not exist, INSERT it
                # ... (code for inserting order into 'orders' table above) ...

                # --- Debugging: Inspect products_list type and content from V2 sub-resource fetch ---
                print(f"DEBUG INGEST: products_list Type AFTER fetch: {type(products_list)}")
                # Try printing content preview directly from the list
                try:
                     print(f"DEBUG INGEST: products_list content preview AFTER fetch: {str(products_list)[:500]}...")
                except Exception as e:
                     print(f"DEBUG INGEST: Could not print products_list content preview: {e}")
                # --- End Debugging ---


                # --- Insert line items from the V2 sub-resource fetch ---
                # The data from the V2 /orders/{id}/products endpoint should be in the 'products_list' variable
                # We need to ensure 'products_list' was populated from the V2 sub-resource fetch
                print(f"DEBUG INGEST LOOP: Attempting to insert line items for Order {order_id}. products_list type: {type(products_list)}, length: {len(products_list) if isinstance(products_list, list) else 'N/A'}.") # <-- Add debug print

                if products_list and isinstance(products_list, list): # Check if products list from V2 sub-resource is non-empty
                    print(f"DEBUG INGEST LOOP: Found products list from V2 sub-resource for Order {order_id}. Attempting to insert line items...")
                    # Ensure the inner loop correctly iterates over the list of product dictionaries
                    for item in products_list: # This iterates over each item in the products_list
                         # Use insert(table).values(...) syntax
                         insert_item_stmt = insert(sqlalchemy.table(
                            'order_line_items', # Table name string
                            # --- Start list of Column objects passed as arguments ---
                            sqlalchemy.column('order_id'),
                            sqlalchemy.column('bigcommerce_line_item_id'),
                            sqlalchemy.column('sku'), # SKU should be available in the sub-resource item
                            sqlalchemy.column('name'),
                            sqlalchemy.column('quantity'),
                            sqlalchemy.column('sale_price'),
                            sqlalchemy.column('created_at'),
                            sqlalchemy.column('updated_at')
                            # --- End list of Column objects ---
                         )).values( # <-- CLOSING PARENTHESIS for sqlalchemy.table(), OPENING PARENTHESIS for .values()
                            # --- Start list of value assignments ---
                            order_id = inserted_order_id, # Use the ID of the newly inserted order
                            bigcommerce_line_item_id = item.get('id'), # Use item.get('id') for BC item ID
                            sku = item.get('sku', 'N/A'), # SKU should be available
                            name = item.get('name', 'N/A'), # Name should be available
                            quantity = item.get('quantity', 0), # Quantity should be available
                            sale_price = item.get('price_inc_tax', 0.00), # Use item.get('price') - confirm price field in V2 product item
                            created_at = datetime.now(timezone.utc),
                            updated_at = datetime.now(timezone.utc)
                            # --- End list of value assignments ---
                         ) # <-- CLOSING PARENTHESIS FOR .values()

                         # Ensure the try block is immediately followed by except/finally
                         try: # This try block is for executing the line item insert
                             conn.execute(insert_item_stmt)
                             print(f"DEBUG INGEST: Successfully inserted line item for Order {order_id}, Item ID {item.get('id')}.") # <-- Add success print
                         except Exception as item_insert_error:
                             print(f"DEBUG INGEST: !!! Error inserting line item for Order {order_id}, Item ID {item.get('id')}: {item_insert_error}. Skipping this line item.")
                             # Continue with the next line item or order

                    print(f"DEBUG INGEST: Attempted inserting line items from V2 sub-resource for Order {order_id}.") # <-- This print should execute if the loop runs
                else:
                    print(f"DEBUG INGEST LOOP: products_list is not a non-empty list for Order {order_id} (Type: {type(products_list)}, Length: {len(products_list) if isinstance(products_list, list) else 'N/A'}). Skipping line item insertion.") # <-- Update print if skipped
                
                
                # Simplify check and loop for debugging

                print(f"DEBUG INGEST LOOP START: Checking if products_list is a list before loop...") # <-- New print BEFORE the check

                # Check if products_list is a list and non-empty
                # Using a simple if statement to enter the block
                if isinstance(products_list, list) and len(products_list) > 0: # <-- Simplified and robust check
                    print(f"DEBUG INGEST LOOP START: products_list is a non-empty list ({len(products_list)} items). Attempting to enter loop...") # <-- New print AFTER the successful check

                                    # --- Debugging: Inspect products_list type and content from V2 sub-resource fetch ---
                print(f"DEBUG INGEST: products_list Type AFTER fetch: {type(products_list)}")
                # Try printing content preview directly from the list
                try:
                     print(f"DEBUG INGEST: products_list content preview AFTER fetch: {str(products_list)[:500]}...")
                except Exception as e:
                     print(f"DEBUG INGEST: Could not print products_list content preview: {e}")
                # --- End Debugging ---

                # Check if products_list is a list and non-empty
                if isinstance(products_list, list) and len(products_list) > 0:
                    print(f"DEBUG INGEST LOOP START: products_list is a non-empty list ({len(products_list)} items). Attempting index-based iteration and print item types...")

                    # --- START DEBUGGING LOOP ONLY (Index-based) ---
                    num_items = len(products_list) # Get the length
                    for i in range(num_items): # <-- Iterate using index
                        item = products_list[i] # <-- Get item by index

                        print(f"DEBUG INGEST LOOP ITEM: Processing item {i} for Order {order_id}. Type: {type(item)}. Content preview: {str(item)[:200]}...")
                        if isinstance(item, dict):
                             print(f"DEBUG INGEST LOOP ITEM: Item {i} keys (first 5): {list(item.keys())[:5]}")
                        else:
                             print(f"DEBUG INGEST LOOP ITEM: Item {i} is NOT a dictionary as expected!")

                        # TEMPORARILY COMMENTING OUT ACTUAL INSERTION LOGIC FOR DEBUGGING
                        # insert_item_stmt = insert(...).values(...)
                        # try:
                        #    conn.execute(insert_item_stmt)
                        # except Exception as item_insert_error:
                        #    ... error handling ...
                    # --- END DEBUGGING LOOP ONLY ---
                    print(f"DEBUG INGEST: Finished iterating products_list (in debug mode).")

                elif isinstance(products_list, list) and len(products_list) == 0:
                     print(f"DEBUG INGEST LOOP START: products_list is an empty list. No line items to insert.")
                else:
                     print(f"DEBUG INGEST LOOP START: products_list is NOT a list or is None. Type: {type(products_list)}")

                # ingested_count += 1 # Count as processed/attempted insertion

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
                trans.rollback()
                print("DEBUG INGEST: Transaction rolled back due to unexpected error.")
            except Exception as rollback_err:
                print(f"DEBUG INGEST: Error attempting transaction rollback after unexpected error: {rollback_err}")

        print(f"Error during order ingestion: {e}")
        return jsonify({"message": f"Error during order ingestion: {e}", "error_type": type(e).__name__}), 500
    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print(f"DEBUG INGEST: Database connection closed.")

# app.py (add this code block after the list_orders function)

# --- API Route to Create Supplier ---
@app.route('/api/suppliers', methods=['POST'])
def create_supplier():
    # Ensure the try block is immediately followed by except/finally
    try:
        print("Received request for POST /api/suppliers")
        if engine is None:
            print("CREATE_SUPPLIER Error: Database engine not initialized.")
            return jsonify({"message": "Database engine not initialized."}), 500

        conn = None # Initialize connection variable
        trans = None # Initialize transaction variable

        # Get JSON data from the request body
        supplier_data = request.json
        print(f"DEBUG CREATE_SUPPLIER: Received data: {supplier_data}")

        # Basic validation: Ensure required fields are present
        # At minimum, a supplier needs a name and an email for our workflow
        required_fields = ['name', 'email']
        for field in required_fields:
            if not supplier_data or field not in supplier_data or not supplier_data[field]:
                print(f"DEBUG CREATE_SUPPLIER: Missing required field: {field}")
                return jsonify({"message": f"Missing required field: {field}"}), 400 # Bad Request

        # Optional: Add validation for other fields like payment_terms format

        # Prepare data for insertion, extracting from the request JSON
        name = supplier_data.get('name')
        email = supplier_data.get('email')
        payment_terms = supplier_data.get('payment_terms') # Allow None if not provided
        address_line1 = supplier_data.get('address_line1')
        address_line2 = supplier_data.get('address_line2')
        city = supplier_data.get('city')
        state = supplier_data.get('state')
        zip_code = supplier_data.get('zip') # Use zip_code to avoid conflict with zip() built-in
        country = supplier_data.get('country')
        phone = supplier_data.get('phone')
        contact_person = supplier_data.get('contact_person')

        # --- Database Insertion ---
        conn = engine.connect()
        trans = conn.begin() # Start transaction

        # Construct the insert statement for the 'suppliers' table
        # Corrected syntax for sqlalchemy.table and .values calls
        insert_supplier_stmt = insert(sqlalchemy.table(
            'suppliers', # Table name string
            # --- Start of list of Column objects passed as arguments to sqlalchemy.table ---
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
            sqlalchemy.column('created_at'),
            sqlalchemy.column('updated_at')
            # --- End of list of Column objects ---
        )).values( # <-- CLOSING PARENTHESIS for sqlalchemy.table(), OPENING PARENTHESIS for .values()
            # --- Start of list of value assignments (key=value, separated by commas) ---
            name = name,
            email = email,
            payment_terms = payment_terms,
            address_line1 = address_line1,
            address_line2 = address_line2,
            city = city,
            state = state,
            zip = zip_code, # Use the 'zip_code' variable value for the 'zip' column
            country = country,
            phone = phone,
            contact_person = contact_person,
            created_at = datetime.now(timezone.utc), # Use timezone aware datetime
            updated_at = datetime.now(timezone.utc) # Use timezone aware datetime
            # --- End of list of value assignments ---
        ) # <--- CLOSING PARENTHESIS FOR .values()


        # Execute the insert statement
        # Use returning() to get the ID of the newly inserted row
        # Use result.fetchone()[0] to get the single value from the single row
        result = conn.execute(insert_supplier_stmt.returning(sqlalchemy.column('id')))

        # Get the inserted primary key
        inserted_supplier_id = result.fetchone()[0] # fetchone() should work with returning()

        trans.commit() # Commit the transaction

        print(f"DEBUG CREATE_SUPPLIER: Successfully inserted supplier with ID: {inserted_supplier_id}")
        return jsonify({
            "message": "Supplier created successfully",
            "supplier_id": inserted_supplier_id
        }), 201 # Created status code

    # Ensure the try block is immediately followed by except/finally
    except sqlalchemy.exc.IntegrityError as e:
        # Handle specific database errors, e.g., unique constraint violation for supplier name/email
        # Check if connection and transaction objects exist before attempting rollback
        if conn and trans: # Corrected transaction check
             try:
                trans.rollback()
                print("DEBUG CREATE_SUPPLIER: Transaction rolled back due to Integrity Error.")
             except Exception as rollback_err:
                print(f"DEBUG CREATE_SUPPLIER: Error attempting Integrity Error rollback: {rollback_err}")

        print(f"DEBUG CREATE_SUPPLIER: Integrity Error: {e}")
        # Check error message for specific constraint violation if needed for more user-friendly message
        return jsonify({"message": f"Supplier creation failed: Duplicate entry (name or email likely already exists).", "error_type": "IntegrityError"}), 409 # Conflict status code

    except Exception as e:
        # Handle other potential errors
        # Check if connection and transaction objects exist before attempting rollback
        if conn and trans: # Corrected transaction check
             try:
                trans.rollback()
                print("DEBUG CREATE_SUPPLIER: Transaction rolled back due to unexpected error.")
             except Exception as rollback_err:
                print(f"DEBUG CREATE_SUPPLIER: Error attempting unexpected exception rollback: {rollback_err}")

        print(f"DEBUG CREATE_SUPPLIER: Caught unexpected exception: {e}")
        return jsonify({"message": f"Supplier creation failed: {e}", "error_type": type(e).__name__}), 500 # Internal Server Error

    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print("DEBUG CREATE_SUPPLIER: Database connection closed.")

# --- API Route to List Suppliers ---
@app.route('/api/suppliers', methods=['GET'])
def list_suppliers():
    print("Received request for GET /api/suppliers")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500

    conn = None # Initialize connection variable

    try:
        # Database Query
        conn = engine.connect()

        # Select all rows from the suppliers table
        # Use order by name for consistent listing
        query = sqlalchemy.text("SELECT * FROM suppliers ORDER BY name")
        result = conn.execute(query)

        # Fetch all results
        suppliers_list = []
        # Access columns by name using row._mapping
        for row in result:
            supplier_dict = dict(row._mapping)
            # Convert types for JSON serialization if needed (e.g., datetime)
            for key, value in supplier_dict.items():
                 if isinstance(value, datetime):
                     supplier_dict[key] = value.isoformat()
            suppliers_list.append(supplier_dict)

        print(f"DEBUG LIST_SUPPLIERS: Found {len(suppliers_list)} suppliers.")
        return jsonify(suppliers_list), 200 # OK status code

    except Exception as e:
        # Handle potential errors during fetching
        print(f"DEBUG LIST_SUPPLIERS: Caught unexpected exception: {e}")
        return jsonify({"message": f"Error fetching suppliers: {e}", "error_type": type(e).__name__}), 500 # Internal Server Error

    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print("DEBUG LIST_SUPPLIERS: Database connection closed.")

# --- API Route to Update Supplier ---
@app.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
def update_supplier(supplier_id):
    print(f"Received request for PUT /api/suppliers/{supplier_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500

    conn = None # Initialize connection variable
    trans = None # Initialize transaction variable

    try:
        # Get JSON data from the request body
        supplier_data = request.json
        print(f"DEBUG UPDATE_SUPPLIER: Received data for supplier ID {supplier_id}: {supplier_data}")

        if not supplier_data:
            return jsonify({"message": "No update data provided."}), 400 # Bad Request

        # Start transaction
        conn = engine.connect()
        trans = conn.begin()

        # Check if the supplier exists first
        existing_supplier = conn.execute(
            sqlalchemy.text("SELECT id FROM suppliers WHERE id = :supplier_id"),
            {"supplier_id": supplier_id}
        ).fetchone()

        if not existing_supplier:
            trans.rollback() # Rollback the transaction
            print(f"DEBUG UPDATE_SUPPLIER: Supplier with ID {supplier_id} not found.")
            return jsonify({"message": f"Supplier with ID {supplier_id} not found."}), 404 # Not Found

        # Construct the update statement dynamically based on provided fields
        update_fields = []
        update_params = {"supplier_id": supplier_id, "updated_at": datetime.now(timezone.utc)} # Include updated_at and ID in params

        # List of allowed fields to update
        allowed_fields = [
            'name', 'email', 'payment_terms', 'address_line1', 'address_line2',
            'city', 'state', 'zip', 'country', 'phone', 'contact_person'
        ]

        # Iterate through allowed fields and add to update statement if present in request data
        for field in allowed_fields:
            # Use .get() to safely check if the key exists in the received data
            if field in supplier_data: # Check if the key is present (allows updating to None/empty string)
                update_fields.append(f"{field} = :{field}")
                # Use the field name as the parameter key
                update_params[field] = supplier_data[field] # Use the value from received data

        # If no allowed fields were provided in the update data
        if not update_fields:
             trans.rollback() # Rollback the transaction
             print(f"DEBUG UPDATE_SUPPLIER: No valid update fields provided for supplier ID {supplier_id}.")
             return jsonify({"message": "No valid update fields provided."}), 400 # Bad Request


        # Build the final update query text
        update_query_text = f"UPDATE suppliers SET {', '.join(update_fields)}, updated_at = :updated_at WHERE id = :supplier_id"
        update_query = sqlalchemy.text(update_query_text)

        # Execute the update statement
        conn.execute(update_query, update_params)

        trans.commit() # Commit the transaction

        print(f"DEBUG UPDATE_SUPPLIER: Successfully updated supplier with ID: {supplier_id}")
        return jsonify({"message": f"Supplier with ID {supplier_id} updated successfully"}), 200 # OK status code

    except sqlalchemy.exc.IntegrityError as e:
        # Handle database errors, e.g., unique constraint violation for supplier name/email
        if conn and trans and trans.in_transaction():
             trans.rollback()
        print(f"DEBUG UPDATE_SUPPLIER: Integrity Error: {e}")
        return jsonify({"message": f"Supplier update failed: Duplicate entry (name or email likely already exists).", "error_type": "IntegrityError"}), 409 # Conflict status code

    except Exception as e:
        # Handle other potential errors
        if conn and trans and trans.in_transaction():
             trans.rollback()
        print(f"DEBUG UPDATE_SUPPLIER: Caught unexpected exception: {e}")
        return jsonify({"message": f"Supplier update failed: {e}", "error_type": type(e).__name__}), 500 # Internal Server Error

    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print(f"DEBUG UPDATE_SUPPLIER: Database connection closed for ID {supplier_id}.")


# --- API Route to Delete Supplier ---
@app.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
def delete_supplier(supplier_id):
    print(f"Received request for DELETE /api/suppliers/{supplier_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500

    conn = None # Initialize connection variable
    trans = None # Initialize transaction variable

    try:
        # Start transaction
        conn = engine.connect()
        trans = conn.begin()

        # Construct the delete statement
        delete_supplier_stmt = sqlalchemy.text("DELETE FROM suppliers WHERE id = :supplier_id")

        # Execute the delete statement
        result = conn.execute(delete_supplier_stmt, {"supplier_id": supplier_id})

        # Check if a row was actually deleted
        if result.rowcount == 0:
            trans.rollback() # Rollback the transaction
            print(f"DEBUG DELETE_SUPPLIER: Supplier with ID {supplier_id} not found for deletion.")
            return jsonify({"message": f"Supplier with ID {supplier_id} not found."}), 404 # Not Found

        trans.commit() # Commit the transaction

        print(f"DEBUG DELETE_SUPPLIER: Successfully deleted supplier with ID: {supplier_id}")
        return jsonify({"message": f"Supplier with ID {supplier_id} deleted successfully"}), 200 # OK status code (or 204 No Content is also common for successful deletion)

    except Exception as e:
        # Handle potential errors
        if conn and trans and trans.in_transaction():
             trans.rollback()
        print(f"DEBUG DELETE_SUPPLIER: Caught unexpected exception: {e}")
        return jsonify({"message": f"Supplier deletion failed: {e}", "error_type": type(e).__name__}), 500 # Internal Server Error

    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print(f"DEBUG DELETE_SUPPLIER: Database connection closed for ID {supplier_id}.")

# --- API Route to Create Product Mapping ---
@app.route('/api/products', methods=['POST'])
def create_product_mapping():
    print("Received request for POST /api/products")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500

    conn = None # Initialize connection variable
    trans = None # Initialize transaction variable

    try:
        # Get JSON data from the request body
        product_data = request.json
        print(f"DEBUG CREATE_PRODUCT: Received data: {product_data}")

        # Basic validation: Ensure required fields are present (SKU and standard_description)
        required_fields = ['sku', 'standard_description']
        for field in required_fields:
            if not product_data or field not in product_data or not product_data[field]:
                print(f"DEBUG CREATE_PRODUCT: Missing required field: {field}")
                return jsonify({"message": f"Missing required field: {field}"}), 400 # Bad Request

        # Prepare data for insertion
        sku = product_data.get('sku')
        standard_description = product_data.get('standard_description')

        # --- Database Insertion ---
        conn = engine.connect()
        trans = conn.begin() # Start transaction

        # Construct the insert statement for the 'products' table
        # Corrected syntax for sqlalchemy.table and .values calls
        insert_product_stmt = insert(sqlalchemy.table(
            'products', # Table name string
            # --- Start of list of Column objects passed as arguments to sqlalchemy.table ---
            sqlalchemy.column('sku'),
            sqlalchemy.column('standard_description'),
            sqlalchemy.column('created_at'),
            sqlalchemy.column('updated_at')
            # --- End of list of Column objects ---
        )).values( # <-- CLOSING PARENTHESIS for sqlalchemy.table(), OPENING PARENTHESIS for .values()
            # --- Start of list of value assignments (key=value, separated by commas) ---
            sku = sku,
            standard_description = standard_description,
            created_at = datetime.now(timezone.utc), # Use timezone aware datetime
            updated_at = datetime.now(timezone.utc) # Use timezone aware datetime
            # --- End of list of value assignments ---
        ) # <--- CLOSING PARENTHESIS FOR .values()


        # Execute the insert statement, using returning() to get the ID
        result = conn.execute(insert_product_stmt.returning(sqlalchemy.column('id')))

        # Get the inserted primary key
        inserted_product_id = result.fetchone()[0] # fetchone() should work with returning()

        trans.commit() # Commit the transaction

        print(f"DEBUG CREATE_PRODUCT: Successfully inserted product mapping with ID: {inserted_product_id}")
        return jsonify({
            "message": "Product mapping created successfully",
            "product_id": inserted_product_id
        }), 201 # Created status code

    except sqlalchemy.exc.IntegrityError as e:
        # Handle specific database errors, e.g., unique constraint violation for SKU
        if conn and trans: # Check if connection and transaction objects exist
             try:
                trans.rollback()
                print("DEBUG CREATE_PRODUCT: Transaction rolled back due to Integrity Error.")
             except Exception as rollback_err:
                print(f"DEBUG CREATE_PRODUCT: Error attempting Integrity Error rollback: {rollback_err}")

        print(f"DEBUG CREATE_PRODUCT: Integrity Error: {e}")
        return jsonify({"message": f"Product mapping creation failed: Duplicate SKU already exists.", "error_type": "IntegrityError"}), 409 # Conflict status code

    except Exception as e:
        # Handle other potential errors
        if conn and trans: # Check if connection and transaction objects exist
             try:
                trans.rollback()
                print("DEBUG CREATE_PRODUCT: Transaction rolled back due to unexpected error.")
             except Exception as rollback_err:
                print(f"DEBUG CREATE_PRODUCT: Error attempting unexpected exception rollback: {rollback_err}")

        print(f"DEBUG CREATE_PRODUCT: Caught unexpected exception: {e}")
        return jsonify({"message": f"Product mapping creation failed: {e}", "error_type": type(e).__name__}), 500 # Internal Server Error

    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print("DEBUG CREATE_PRODUCT: Database connection closed.")

    # --- API Route to List Product Mappings ---
# Note: This route shares the /api/products path but uses the GET method
@app.route('/api/products', methods=['GET'])
def list_product_mappings():
    print("Received request for GET /api/products")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500

    conn = None # Initialize connection variable

    try:
        # Database Query
        conn = engine.connect()

        # Select all rows from the products table
        # Order by SKU for consistent listing
        query = sqlalchemy.text("SELECT * FROM products ORDER BY sku")
        result = conn.execute(query)

        # Fetch all results
        product_mappings_list = []
        # Access columns by name using row._mapping
        for row in result:
            product_dict = dict(row._mapping)
            # Convert types for JSON serialization if needed (e.g., datetime)
            for key, value in product_dict.items():
                 if isinstance(value, datetime):
                     product_dict[key] = value.isoformat()
            product_mappings_list.append(product_dict)

        print(f"DEBUG LIST_PRODUCTS: Found {len(product_mappings_list)} product mappings.")
        return jsonify(product_mappings_list), 200 # OK status code

    except Exception as e:
        # Handle potential errors during fetching
        print(f"DEBUG LIST_PRODUCTS: Caught unexpected exception: {e}")
        return jsonify({"message": f"Error fetching product mappings: {e}", "error_type": type(e).__name__}), 500 # Internal Server Error

    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print("DEBUG LIST_PRODUCTS: Database connection closed.")         

# --- API Route to Update Product Mapping ---
@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product_mapping(product_id):
    print(f"Received request for PUT /api/products/{product_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500

    conn = None # Initialize connection variable
    trans = None # Initialize transaction variable

    try:
        # Get JSON data from the request body
        product_data = request.json
        print(f"DEBUG UPDATE_PRODUCT: Received data for product ID {product_id}: {product_data}")

        if not product_data:
            return jsonify({"message": "No update data provided."}), 400 # Bad Request

        # Start transaction
        conn = engine.connect()
        trans = conn.begin()

        # Check if the product mapping exists first
        existing_product = conn.execute(
            sqlalchemy.text("SELECT id FROM products WHERE id = :product_id"),
            {"product_id": product_id}
        ).fetchone()

        if not existing_product:
            trans.rollback() # Rollback the transaction
            print(f"DEBUG UPDATE_PRODUCT: Product mapping with ID {product_id} not found.")
            return jsonify({"message": f"Product mapping with ID {product_id} not found."}), 404 # Not Found

        # Construct the update statement dynamically based on provided fields
        update_fields = []
        update_params = {"product_id": product_id, "updated_at": datetime.now(timezone.utc)} # Include updated_at and ID in params

        # List of allowed fields to update for a product mapping
        allowed_fields = ['sku', 'standard_description']

        # Iterate through allowed fields and add to update statement if present in request data
        for field in allowed_fields:
            if field in product_data: # Check if the key is present (allows updating to None/empty string)
                update_fields.append(f"{field} = :{field}")
                update_params[field] = product_data[field]

        # If no allowed fields were provided in the update data
        if not update_fields:
             trans.rollback() # Rollback the transaction
             print(f"DEBUG UPDATE_PRODUCT: No valid update fields provided for product ID {product_id}.")
             return jsonify({"message": "No valid update fields provided."}), 400 # Bad Request


        # Build the final update query text
        update_query_text = f"UPDATE products SET {', '.join(update_fields)}, updated_at = :updated_at WHERE id = :product_id"
        update_query = sqlalchemy.text(update_query_text)

        # Execute the update statement
        conn.execute(update_query, update_params)

        trans.commit() # Commit the transaction

        print(f"DEBUG UPDATE_PRODUCT: Successfully updated product mapping with ID: {product_id}")
        return jsonify({"message": f"Product mapping with ID {product_id} updated successfully"}), 200 # OK status code

    except sqlalchemy.exc.IntegrityError as e:
        # Handle database errors, e.g., unique constraint violation for SKU
        if conn and trans:
             try:
                trans.rollback()
                print("DEBUG UPDATE_PRODUCT: Transaction rolled back due to Integrity Error.")
             except Exception as rollback_err:
                print(f"DEBUG UPDATE_PRODUCT: Error attempting Integrity Error rollback: {rollback_err}")

        print(f"DEBUG UPDATE_PRODUCT: Integrity Error: {e}")
        return jsonify({"message": f"Product mapping update failed: Duplicate SKU already exists.", "error_type": "IntegrityError"}), 409 # Conflict status code

    except Exception as e:
        # Handle other potential errors
        if conn and trans:
             try:
                trans.rollback()
                print(f"DEBUG UPDATE_PRODUCT: Transaction rolled back due to unexpected error: {e}")
             except Exception as rollback_err:
                print(f"DEBUG UPDATE_PRODUCT: Error attempting unexpected exception rollback: {rollback_err}")

        print(f"DEBUG UPDATE_PRODUCT: Caught unexpected exception: {e}")
        return jsonify({"message": f"Product mapping update failed: {e}", "error_type": type(e).__name__}), 500 # Internal Server Error

    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print(f"DEBUG UPDATE_PRODUCT: Database connection closed for ID {product_id}.")


# --- API Route to Delete Product Mapping ---
@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product_mapping(product_id):
    print(f"Received request for DELETE /api/products/{product_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500

    conn = None # Initialize connection variable
    trans = None # Initialize transaction variable

    try:
        # Start transaction
        conn = engine.connect()
        trans = conn.begin()

        # Construct the delete statement
        delete_product_stmt = sqlalchemy.text("DELETE FROM products WHERE id = :product_id")

        # Execute the delete statement
        result = conn.execute(delete_product_stmt, {"product_id": product_id})

        # Check if a row was actually deleted
        if result.rowcount == 0:
            trans.rollback() # Rollback the transaction
            print(f"DEBUG DELETE_PRODUCT: Product mapping with ID {product_id} not found for deletion.")
            return jsonify({"message": f"Product mapping with ID {product_id} not found."}), 404 # Not Found

        trans.commit() # Commit the transaction

        print(f"DEBUG DELETE_PRODUCT: Successfully deleted product mapping with ID: {product_id}")
        return jsonify({"message": f"Product mapping with ID {product_id} deleted successfully"}), 200 # OK status code (or 204 No Content)

    except Exception as e:
        # Handle potential errors
        if conn and trans:
             try:
                trans.rollback()
                print(f"DEBUG DELETE_PRODUCT: Transaction rolled back due to unexpected error: {e}")
             except Exception as rollback_err:
                print(f"DEBUG DELETE_PRODUCT: Error attempting unexpected exception rollback: {rollback_err}")

        print(f"DEBUG DELETE_PRODUCT: Caught unexpected exception: {e}")
        return jsonify({"message": f"Product mapping deletion failed: {e}", "error_type": type(e).__name__}), 500 # Internal Server Error

    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print(f"DEBUG DELETE_PRODUCT: Database connection closed for ID {product_id}.")

# --- API Route to Get Single Supplier by ID ---
@app.route('/api/suppliers/<int:supplier_id>', methods=['GET'])
def get_supplier(supplier_id):
    print(f"Received request for GET /api/suppliers/{supplier_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500

    conn = None # Initialize connection variable

    try:
        # Database Query
        conn = engine.connect()

        # Select the supplier with the matching ID
        query = sqlalchemy.text("SELECT * FROM suppliers WHERE id = :supplier_id")
        result = conn.execute(query, {"supplier_id": supplier_id}).fetchone() # Use fetchone() for a single row

        # Check if a supplier was found
        if result is None:
            print(f"DEBUG GET_SUPPLIER: Supplier with ID {supplier_id} not found.")
            return jsonify({"message": f"Supplier with ID {supplier_id} not found."}), 404 # Not Found status code

        # Convert the row to a dictionary
        supplier_dict = dict(result._mapping) # Access columns by name

        # Convert types for JSON serialization (datetime, Decimal)
        for key, value in supplier_dict.items():
            if isinstance(value, datetime):
                supplier_dict[key] = value.isoformat()
            # Assuming Decimal values should be converted to float for frontend display
            # You could also keep them as strings if preferred
            elif isinstance(value, Decimal):
                 supplier_dict[key] = float(value)

        print(f"DEBUG GET_SUPPLIER: Found supplier with ID: {supplier_id}.")
        return jsonify(supplier_dict), 200 # OK status code

    except Exception as e:
        # Handle potential errors during fetching
        print(f"DEBUG GET_SUPPLIER: Caught unexpected exception: {e}")
        return jsonify({"message": f"Error fetching supplier: {e}", "error_type": type(e).__name__}), 500 # Internal Server Error

    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print(f"DEBUG GET_SUPPLIER: Database connection closed for ID {supplier_id}.")

@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product_mapping(product_id):
    print(f"Received request for GET /api/products/{product_id}")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500

    conn = None # Initialize connection variable

    try:
        # Database Query
        conn = engine.connect()

        # Select the product mapping with the matching ID
        query = sqlalchemy.text("SELECT * FROM products WHERE id = :product_id")
        result = conn.execute(query, {"product_id": product_id}).fetchone() # Use fetchone() for a single row

        # Check if a product mapping was found
        if result is None:
            print(f"DEBUG GET_PRODUCT: Product mapping with ID {product_id} not found.")
            return jsonify({"message": f"Product mapping with ID {product_id} not found."}), 404 # Not Found status code

        # Convert the row to a dictionary
        product_dict = dict(result._mapping) # Access columns by name

        # Convert types for JSON serialization (datetime)
        for key, value in product_dict.items():
            if isinstance(value, datetime):
                product_dict[key] = value.isoformat()

        print(f"DEBUG GET_PRODUCT: Found product mapping with ID: {product_id}.")
        return jsonify(product_dict), 200 # OK status code

    except Exception as e:
        # Handle potential errors during fetching
        print(f"DEBUG GET_PRODUCT: Caught unexpected exception: {e}")
        return jsonify({"message": f"Error fetching product mapping: {e}", "error_type": type(e).__name__}), 500 # Internal Server Error

    finally:
        # Ensure connection is closed
        if conn:
             conn.close()
             print(f"DEBUG GET_PRODUCT: Database connection closed for ID {product_id}.")

# --- API Route to Get Single Order by App ID ---
@app.route('/api/orders/<int:order_id>', methods=['GET'])
def get_order_details(order_id):
    """Fetches details for a single order and its line items from the local DB."""
    print(f"DEBUG GET_ORDER: Received request for order ID: {order_id}")
    db_conn = None

    try:
        # 1. Database Connection
        if engine is None:
            print("ERROR GET_ORDER: Database engine is not initialized.")
            return jsonify({"error": "Database connection error, engine not available."}), 500

        print("DEBUG GET_ORDER: Attempting to connect to database via engine...")
        db_conn = engine.connect() # Get a connection from the pool
        print(f"DEBUG GET_ORDER: DB connection established: {type(db_conn)}")

        # --- No transaction needed for read-only operation ---
        # transaction = db_conn.begin()

        # 2. Fetch Main Order Data
        order_query = text("SELECT * FROM orders WHERE id = :order_id")
        order_record = db_conn.execute(order_query, {"order_id": order_id}).fetchone()

        if not order_record:
            # No transaction to rollback as it's read-only
            return jsonify({"error": f"Order with ID {order_id} not found"}), 404

        # Convert Row object to dictionary
        # Ensure keys match your actual 'orders' table columns
        order_data_dict = dict(order_record._mapping)
        # Convert Decimal types to strings for JSON serialization if necessary
        for key, value in order_data_dict.items():
             if isinstance(value, Decimal):
                 order_data_dict[key] = str(value)

        # 3. Fetch Order Line Items
        order_line_items_query = text("SELECT * FROM order_line_items WHERE order_id = :order_id ORDER BY id")
        local_order_line_items_records = db_conn.execute(order_line_items_query, {"order_id": order_id}).fetchall()

        # Convert list of Row objects to list of dictionaries
        line_items_list = []
        for row in local_order_line_items_records:
            item_dict = dict(row._mapping)
            # Convert Decimal types to strings for JSON serialization
            for key, value in item_dict.items():
                if isinstance(value, Decimal):
                    item_dict[key] = str(value)
            line_items_list.append(item_dict)

        print(f"DEBUG GET_ORDER: Found order with ID: {order_id} and {len(line_items_list)} line items.")

        # 4. Combine data and return JSON response
        response_data = {
            "order": order_data_dict,
            "line_items": line_items_list
        }

        return jsonify(response_data), 200

    except Exception as e:
        # Log the error and return an error response
        original_error_traceback = traceback.format_exc()
        print(f"ERROR GET_ORDER: Error fetching order {order_id}: {e}")
        print("--- ORIGINAL ERROR TRACEBACK ---")
        print(original_error_traceback)
        print("--- END ORIGINAL ERROR TRACEBACK ---")

        return jsonify({
            "error": "An unexpected error occurred while fetching order details.",
            "details": str(e)
        }), 500

    finally:
        # Ensure the connection is closed
        if db_conn:
            if not db_conn.closed:
                print(f"DEBUG GET_ORDER: Attempting to close database connection for ID {order_id}")
                db_conn.close()
                print(f"DEBUG GET_ORDER: Database connection closed for ID {order_id}.")
            else:
                print(f"DEBUG GET_ORDER: Database connection was already closed for ID {order_id}.")
        else:
             print(f"DEBUG GET_ORDER: No valid database connection object to close for ID {order_id}.")

# --- Orchestrate the Drop Shipment Process ---
@app.route('/api/orders/<int:order_id>/process', methods=['POST'])
def process_order(order_id):
    print(f"DEBUG PROCESS_ORDER: Received request to process order ID: {order_id}")
    db_conn = None
    transaction = None
    po_pdf_bytes = None # Initialize PDF byte variables
    packing_slip_pdf_bytes = None

    try:
        # 1. Receive Input Data from Frontend
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid or missing JSON payload"}), 400

        supplier_id = data.get('supplier_id')
        po_line_items_input = data.get('po_line_items') # List of dicts
        total_shipment_weight_lbs = data.get('total_shipment_weight_lbs')
        payment_instructions = data.get('payment_instructions', "") # Default to empty string if not provided

        # Basic validation of input presence
        if not all([supplier_id, po_line_items_input, total_shipment_weight_lbs is not None]):
            missing_fields = []
            if not supplier_id: missing_fields.append("supplier_id")
            if not po_line_items_input: missing_fields.append("po_line_items")
            if total_shipment_weight_lbs is None: missing_fields.append("total_shipment_weight_lbs")
            return jsonify({"error": f"Missing required fields in payload: {', '.join(missing_fields)}"}), 400
        
        if not isinstance(po_line_items_input, list) or not po_line_items_input:
            return jsonify({"error": "'po_line_items' must be a non-empty list"}), 400
        for item in po_line_items_input:
            if not all(k in item for k in ("sku", "quantity", "unit_cost")): # Add 'original_order_line_item_id' if mandatory
                return jsonify({"error": "Each item in 'po_line_items' must contain 'sku', 'quantity', and 'unit_cost'"}), 400

        print(f"DEBUG PROCESS_ORDER: Input data: Supplier ID: {supplier_id}, Weight: {total_shipment_weight_lbs} lbs")

        # 2. Database Connection & Transaction
        if engine is None: # 'engine' should be your globally defined SQLAlchemy engine
            print("ERROR PROCESS_ORDER: Database engine is not initialized.")
            return jsonify({"error": "Database connection error, engine not available."}), 500

        print("DEBUG PROCESS_ORDER: Attempting to connect to database via engine...")
        db_conn = engine.connect()
        print(f"DEBUG PROCESS_ORDER: DB connection established: {type(db_conn)}")
        
        transaction = db_conn.begin()
        print(f"DEBUG PROCESS_ORDER: Transaction started: {type(transaction)}")

        # 3. Fetch Data from Your Database (Order, Line Items, Supplier)
        order_query = text("SELECT * FROM orders WHERE id = :order_id")
        order_record = db_conn.execute(order_query, {"order_id": order_id}).fetchone()

        if not order_record:
            if transaction: transaction.rollback()
            return jsonify({"error": f"Order with ID {order_id} not found in local database"}), 404
        order_data_dict = dict(order_record._mapping)
        print(f"DEBUG PROCESS_ORDER: Fetched local order data: ID={order_data_dict.get('id')}, Status={order_data_dict.get('status')}")

        order_line_items_query = text("SELECT * FROM order_line_items WHERE order_id = :order_id ORDER BY id")
        local_order_line_items_records = db_conn.execute(order_line_items_query, {"order_id": order_id}).fetchall()
        local_order_line_items_list = [dict(row._mapping) for row in local_order_line_items_records]
        print(f"DEBUG PROCESS_ORDER: Fetched {len(local_order_line_items_list)} local order line items.")

        supplier_query = text("SELECT * FROM suppliers WHERE id = :supplier_id")
        supplier_record = db_conn.execute(supplier_query, {"supplier_id": supplier_id}).fetchone()

        if not supplier_record:
            if transaction: transaction.rollback()
            return jsonify({"error": f"Supplier with ID {supplier_id} not found"}), 404
        supplier_data_dict = dict(supplier_record._mapping)
        print(f"DEBUG PROCESS_ORDER: Fetched supplier data for: {supplier_data_dict.get('name')}")

        # 4. Input Validation (Example: check if order is domestic)
        if order_data_dict.get('is_international'):
             if transaction: transaction.rollback()
             return jsonify({"message": f"Order {order_id} is international. Manual processing required as per MVP scope."}), 400

        # 5. Generate PO Number (Numeric, Sequential)
        generated_po_number = None
        starting_po_sequence = 200001

        last_po_query_sql = text("SELECT MAX(po_number) FROM purchase_orders")
        print(f"DEBUG PROCESS_ORDER: About to execute query for MAX(po_number).")
        max_po_value_from_db = db_conn.execute(last_po_query_sql).scalar_one_or_none()
        print(f"DEBUG PROCESS_ORDER: MAX(po_number) from DB: {max_po_value_from_db} (type: {type(max_po_value_from_db)})")

        if max_po_value_from_db is None:
            next_sequence_num = starting_po_sequence
        else:
            try:
                current_max_po = int(max_po_value_from_db)
                if current_max_po < starting_po_sequence:
                    next_sequence_num = starting_po_sequence
                else:
                    next_sequence_num = current_max_po + 1
            except (ValueError, TypeError) as e_conv:
                print(f"ERROR PROCESS_ORDER: Could not convert max_po_value_from_db '{max_po_value_from_db}' to int for PO sequence: {e_conv}")
                next_sequence_num = starting_po_sequence # Fallback

        generated_po_number = next_sequence_num
        print(f"DEBUG PROCESS_ORDER: Generated PO Number: {generated_po_number}")
        
        # 6. Database Writes: INSERT into purchase_orders
        current_utc_datetime = datetime.now(timezone.utc)
        po_total_amount = sum(
            Decimal(item.get('quantity', 0)) * Decimal(item.get('unit_cost', 0))
            for item in po_line_items_input
        ) # Ensure Decimal for currency

        insert_po_sql = text("""
            INSERT INTO purchase_orders 
            (po_number, order_id, supplier_id, po_date, payment_instructions, status, total_amount)
            VALUES (:po_number, :order_id, :supplier_id, :po_date, :payment_instructions, :status, :total_amount)
            RETURNING id
        """)

        po_params = {
            "po_number": generated_po_number,
            "order_id": order_id,
            "supplier_id": supplier_id,
            "po_date": current_utc_datetime,
            "payment_instructions": payment_instructions,
            "status": "New", # Initial PO status
            "total_amount": po_total_amount
        }

        print(f"DEBUG PROCESS_ORDER: Attempting to insert into purchase_orders with params: {po_params}")
        result_po_insert = db_conn.execute(insert_po_sql, po_params)
        new_purchase_order_id = result_po_insert.scalar_one_or_none()

        if new_purchase_order_id is None:
            raise Exception("Failed to retrieve new purchase_order_id after inserting into purchase_orders.")
        print(f"DEBUG PROCESS_ORDER: Successfully inserted into purchase_orders. New PO ID (internal): {new_purchase_order_id}")

        # 7. Database Writes: INSERT into po_line_items
        insert_po_item_sql = text("""
            INSERT INTO po_line_items
            (purchase_order_id, original_order_line_item_id, sku, description, quantity, unit_cost, condition)
            VALUES (:purchase_order_id, :original_order_line_item_id, :sku, :description, :quantity, :unit_cost, :condition)
        """)

        for item_input in po_line_items_input:
            item_description = f"Sourced item: {item_input.get('sku')}" # Placeholder, enhance as needed
            # Example: find matching original item to get its name/description for PO if appropriate
            # original_item_detail = next((oli for oli in local_order_line_items_list if oli.get('id') == item_input.get('original_order_line_item_id')), None)
            # if original_item_detail:
            #     item_description = original_item_detail.get('name', item_description) # Or a standard description from a product table

            po_item_params = {
                "purchase_order_id": new_purchase_order_id,
                "original_order_line_item_id": item_input.get("original_order_line_item_id"),
                "sku": item_input.get("sku"),
                "description": item_description,
                "quantity": item_input.get("quantity"),
                "unit_cost": Decimal(item_input.get("unit_cost")), # Ensure Decimal for currency
                "condition": item_input.get("condition", "New") # Default condition if not provided
            }
            print(f"DEBUG PROCESS_ORDER: Attempting to insert into po_line_items with params: {po_item_params}")
            db_conn.execute(insert_po_item_sql, po_item_params)
        
        print(f"DEBUG PROCESS_ORDER: Successfully inserted {len(po_line_items_input)} items into po_line_items for PO ID: {new_purchase_order_id}")
        
        # --- TODO: Placeholder for next steps ---        # --- >>> START: Step 8 - Generate Documents <<< ---
        print("DEBUG PROCESS_ORDER: Generating Purchase Order and Packing Slip PDFs...")

        # Prepare data for Purchase Order PDF (ensure keys match document_generator function needs)
        po_pdf_data = {
            "purchase_order_number": str(generated_po_number),
            "po_date": current_utc_datetime.strftime("%Y-%m-%d"),
            "supplier": supplier_data_dict,
            "shipping_address": { # Extract relevant shipping info from the original order
                "name": order_data_dict.get('customer_name'),
                "street_1": order_data_dict.get('customer_shipping_address_line1'),
                "street_2": order_data_dict.get('customer_shipping_address_line2'),
                "city": order_data_dict.get('customer_shipping_city'),
                "state": order_data_dict.get('customer_shipping_state'),
                "zip": order_data_dict.get('customer_shipping_zip'),
                "country": order_data_dict.get('customer_shipping_country')
            },
            "items": po_line_items_input, # Use input items with negotiated cost
            "total_amount": po_total_amount,
            "payment_instructions": payment_instructions,
            "payment_terms": supplier_data_dict.get('payment_terms')
            # Add/adjust fields as needed by your specific PO template
        }

        try:
            # Call the function from your document_generator module
            po_pdf_bytes = document_generator.generate_purchase_order_pdf(po_pdf_data)
            if not po_pdf_bytes or not isinstance(po_pdf_bytes, bytes):
                 raise ValueError("generate_purchase_order_pdf did not return valid bytes.")
            print(f"DEBUG PROCESS_ORDER: Purchase Order PDF generated ({len(po_pdf_bytes)} bytes).")
        except Exception as pdf_po_e:
            print(f"ERROR PROCESS_ORDER: Failed to generate Purchase Order PDF: {pdf_po_e}")
            raise Exception(f"PO PDF generation failed: {pdf_po_e}") from pdf_po_e # Re-raise to trigger rollback

        # Prepare data for Packing Slip PDF (ensure keys match document_generator function needs)
        packing_slip_data = {
            "purchase_order_number": str(generated_po_number),
            "order_id": order_data_dict.get('bigcommerce_order_id'),
            "order_date": order_data_dict.get('date_created'),
             "shipping_address": { # Same shipping address
                "name": order_data_dict.get('customer_name'),
                "street_1": order_data_dict.get('customer_shipping_address_line1'),
                "street_2": order_data_dict.get('customer_shipping_address_line2'),
                "city": order_data_dict.get('customer_shipping_city'),
                "state": order_data_dict.get('customer_shipping_state'),
                "zip": order_data_dict.get('customer_shipping_zip'),
                "country": order_data_dict.get('customer_shipping_country')
            },
            "items": local_order_line_items_list # Use original items from local DB
            # Adjust fields as needed by your specific packing slip template
        }

        try:
             # Call the function from your document_generator module
            packing_slip_pdf_bytes = document_generator.generate_packing_slip_pdf(packing_slip_data)
            if not packing_slip_pdf_bytes or not isinstance(packing_slip_pdf_bytes, bytes):
                 raise ValueError("generate_packing_slip_pdf did not return valid bytes.")
            print(f"DEBUG PROCESS_ORDER: Packing Slip PDF generated ({len(packing_slip_pdf_bytes)} bytes).")
        except Exception as pdf_ps_e:
            print(f"ERROR PROCESS_ORDER: Failed to generate Packing Slip PDF: {pdf_ps_e}")
            raise Exception(f"Packing Slip PDF generation failed: {pdf_ps_e}") from pdf_ps_e # Re-raise
        # --- >>> END: Step 8 - Generate Documents <<< ---


        # --- TODO: Placeholder for next steps ---        # --- >>> START: Step 8 - Generate Documents <<< ---
        print("DEBUG PROCESS_ORDER: Generating Purchase Order and Packing Slip PDFs...")

        # Prepare data for Purchase Order PDF (ensure keys match document_generator function needs)
        po_pdf_data = {
            "purchase_order_number": str(generated_po_number),
            "po_date": current_utc_datetime.strftime("%Y-%m-%d"),
            "supplier": supplier_data_dict,
            "shipping_address": { # Extract relevant shipping info from the original order
                "name": order_data_dict.get('customer_name'),
                "street_1": order_data_dict.get('customer_shipping_address_line1'),
                "street_2": order_data_dict.get('customer_shipping_address_line2'),
                "city": order_data_dict.get('customer_shipping_city'),
                "state": order_data_dict.get('customer_shipping_state'),
                "zip": order_data_dict.get('customer_shipping_zip'),
                "country": order_data_dict.get('customer_shipping_country')
            },
            "items": po_line_items_input, # Use input items with negotiated cost
            "total_amount": po_total_amount,
            "payment_instructions": payment_instructions,
            "payment_terms": supplier_data_dict.get('payment_terms')
            # Add/adjust fields as needed by your specific PO template
        }

        try:
            # Call the function from your document_generator module
            po_pdf_bytes = document_generator.generate_purchase_order_pdf(po_pdf_data)
            if not po_pdf_bytes or not isinstance(po_pdf_bytes, bytes):
                 raise ValueError("generate_purchase_order_pdf did not return valid bytes.")
            print(f"DEBUG PROCESS_ORDER: Purchase Order PDF generated ({len(po_pdf_bytes)} bytes).")
        except Exception as pdf_po_e:
            print(f"ERROR PROCESS_ORDER: Failed to generate Purchase Order PDF: {pdf_po_e}")
            raise Exception(f"PO PDF generation failed: {pdf_po_e}") from pdf_po_e # Re-raise to trigger rollback

        # Prepare data for Packing Slip PDF (ensure keys match document_generator function needs)
        packing_slip_data = {
            "purchase_order_number": str(generated_po_number),
            "order_id": order_data_dict.get('bigcommerce_order_id'),
            "order_date": order_data_dict.get('date_created'),
             "shipping_address": { # Same shipping address
                "name": order_data_dict.get('customer_name'),
                "street_1": order_data_dict.get('customer_shipping_address_line1'),
                "street_2": order_data_dict.get('customer_shipping_address_line2'),
                "city": order_data_dict.get('customer_shipping_city'),
                "state": order_data_dict.get('customer_shipping_state'),
                "zip": order_data_dict.get('customer_shipping_zip'),
                "country": order_data_dict.get('customer_shipping_country')
            },
            "items": local_order_line_items_list # Use original items from local DB
            # Adjust fields as needed by your specific packing slip template
        }

        try:
             # Call the function from your document_generator module
            packing_slip_pdf_bytes = document_generator.generate_packing_slip_pdf(packing_slip_data)
            if not packing_slip_pdf_bytes or not isinstance(packing_slip_pdf_bytes, bytes):
                 raise ValueError("generate_packing_slip_pdf did not return valid bytes.")
            print(f"DEBUG PROCESS_ORDER: Packing Slip PDF generated ({len(packing_slip_pdf_bytes)} bytes).")
        except Exception as pdf_ps_e:
            print(f"ERROR PROCESS_ORDER: Failed to generate Packing Slip PDF: {pdf_ps_e}")
            raise Exception(f"Packing Slip PDF generation failed: {pdf_ps_e}") from pdf_ps_e # Re-raise
        # --- >>> END: Step 8 - Generate Documents <<< ---


        # --- TODO: Placeholder for next steps ---        # --- >>> START: Step 8 - Generate Documents <<< ---
        print("DEBUG PROCESS_ORDER: Generating Purchase Order and Packing Slip PDFs...")

        # Prepare data for Purchase Order PDF (ensure keys match document_generator function needs)
        po_pdf_data = {
            "purchase_order_number": str(generated_po_number),
            "po_date": current_utc_datetime.strftime("%Y-%m-%d"),
            "supplier": supplier_data_dict,
            "shipping_address": { # Extract relevant shipping info from the original order
                "name": order_data_dict.get('customer_name'),
                "street_1": order_data_dict.get('customer_shipping_address_line1'),
                "street_2": order_data_dict.get('customer_shipping_address_line2'),
                "city": order_data_dict.get('customer_shipping_city'),
                "state": order_data_dict.get('customer_shipping_state'),
                "zip": order_data_dict.get('customer_shipping_zip'),
                "country": order_data_dict.get('customer_shipping_country')
            },
            "items": po_line_items_input, # Use input items with negotiated cost
            "total_amount": po_total_amount,
            "payment_instructions": payment_instructions,
            "payment_terms": supplier_data_dict.get('payment_terms')
            # Add/adjust fields as needed by your specific PO template
        }

        try:
            # Call the function from your document_generator module
            po_pdf_bytes = document_generator.generate_purchase_order_pdf(po_pdf_data)
            if not po_pdf_bytes or not isinstance(po_pdf_bytes, bytes):
                 raise ValueError("generate_purchase_order_pdf did not return valid bytes.")
            print(f"DEBUG PROCESS_ORDER: Purchase Order PDF generated ({len(po_pdf_bytes)} bytes).")
        except Exception as pdf_po_e:
            print(f"ERROR PROCESS_ORDER: Failed to generate Purchase Order PDF: {pdf_po_e}")
            raise Exception(f"PO PDF generation failed: {pdf_po_e}") from pdf_po_e # Re-raise to trigger rollback

        # Prepare data for Packing Slip PDF (ensure keys match document_generator function needs)
        packing_slip_data = {
            "purchase_order_number": str(generated_po_number),
            "order_id": order_data_dict.get('bigcommerce_order_id'),
            "order_date": order_data_dict.get('date_created'),
             "shipping_address": { # Same shipping address
                "name": order_data_dict.get('customer_name'),
                "street_1": order_data_dict.get('customer_shipping_address_line1'),
                "street_2": order_data_dict.get('customer_shipping_address_line2'),
                "city": order_data_dict.get('customer_shipping_city'),
                "state": order_data_dict.get('customer_shipping_state'),
                "zip": order_data_dict.get('customer_shipping_zip'),
                "country": order_data_dict.get('customer_shipping_country')
            },
            "items": local_order_line_items_list # Use original items from local DB
            # Adjust fields as needed by your specific packing slip template
        }

        try:
             # Call the function from your document_generator module
            packing_slip_pdf_bytes = document_generator.generate_packing_slip_pdf(packing_slip_data)
            if not packing_slip_pdf_bytes or not isinstance(packing_slip_pdf_bytes, bytes):
                 raise ValueError("generate_packing_slip_pdf did not return valid bytes.")
            print(f"DEBUG PROCESS_ORDER: Packing Slip PDF generated ({len(packing_slip_pdf_bytes)} bytes).")
        except Exception as pdf_ps_e:
            print(f"ERROR PROCESS_ORDER: Failed to generate Packing Slip PDF: {pdf_ps_e}")
            raise Exception(f"Packing Slip PDF generation failed: {pdf_ps_e}") from pdf_ps_e # Re-raise
        # --- >>> END: Step 8 - Generate Documents <<< ---


        # --- TODO: Placeholder for next steps ---        # --- >>> START: Step 8 - Generate Documents <<< ---
        print("DEBUG PROCESS_ORDER: Generating Purchase Order and Packing Slip PDFs...")

        # Prepare data for Purchase Order PDF (ensure keys match document_generator function needs)
        po_pdf_data = {
            "purchase_order_number": str(generated_po_number),
            "po_date": current_utc_datetime.strftime("%Y-%m-%d"),
            "supplier": supplier_data_dict,
            "shipping_address": { # Extract relevant shipping info from the original order
                "name": order_data_dict.get('customer_name'),
                "street_1": order_data_dict.get('customer_shipping_address_line1'),
                "street_2": order_data_dict.get('customer_shipping_address_line2'),
                "city": order_data_dict.get('customer_shipping_city'),
                "state": order_data_dict.get('customer_shipping_state'),
                "zip": order_data_dict.get('customer_shipping_zip'),
                "country": order_data_dict.get('customer_shipping_country')
            },
            "items": po_line_items_input, # Use input items with negotiated cost
            "total_amount": po_total_amount,
            "payment_instructions": payment_instructions,
            "payment_terms": supplier_data_dict.get('payment_terms')
            # Add/adjust fields as needed by your specific PO template
        }

        try:
            # Call the function from your document_generator module
            po_pdf_bytes = document_generator.generate_purchase_order_pdf(po_pdf_data)
            if not po_pdf_bytes or not isinstance(po_pdf_bytes, bytes):
                 raise ValueError("generate_purchase_order_pdf did not return valid bytes.")
            print(f"DEBUG PROCESS_ORDER: Purchase Order PDF generated ({len(po_pdf_bytes)} bytes).")
        except Exception as pdf_po_e:
            print(f"ERROR PROCESS_ORDER: Failed to generate Purchase Order PDF: {pdf_po_e}")
            raise Exception(f"PO PDF generation failed: {pdf_po_e}") from pdf_po_e # Re-raise to trigger rollback

        # Prepare data for Packing Slip PDF (ensure keys match document_generator function needs)
        packing_slip_data = {
            "purchase_order_number": str(generated_po_number),
            "order_id": order_data_dict.get('bigcommerce_order_id'),
            "order_date": order_data_dict.get('date_created'),
             "shipping_address": { # Same shipping address
                "name": order_data_dict.get('customer_name'),
                "street_1": order_data_dict.get('customer_shipping_address_line1'),
                "street_2": order_data_dict.get('customer_shipping_address_line2'),
                "city": order_data_dict.get('customer_shipping_city'),
                "state": order_data_dict.get('customer_shipping_state'),
                "zip": order_data_dict.get('customer_shipping_zip'),
                "country": order_data_dict.get('customer_shipping_country')
            },
            "items": local_order_line_items_list # Use original items from local DB
            # Adjust fields as needed by your specific packing slip template
        }

        try:
             # Call the function from your document_generator module
            packing_slip_pdf_bytes = document_generator.generate_packing_slip_pdf(packing_slip_data)
            if not packing_slip_pdf_bytes or not isinstance(packing_slip_pdf_bytes, bytes):
                 raise ValueError("generate_packing_slip_pdf did not return valid bytes.")
            print(f"DEBUG PROCESS_ORDER: Packing Slip PDF generated ({len(packing_slip_pdf_bytes)} bytes).")
        except Exception as pdf_ps_e:
            print(f"ERROR PROCESS_ORDER: Failed to generate Packing Slip PDF: {pdf_ps_e}")
            raise Exception(f"Packing Slip PDF generation failed: {pdf_ps_e}") from pdf_ps_e # Re-raise
        # --- >>> END: Step 8 - Generate Documents <<< ---


        # --- >>> START: Step 8 - Generate Documents <<< ---
        print("DEBUG PROCESS_ORDER: Generating Purchase Order and Packing Slip PDFs...")

        # Prepare data for Purchase Order PDF (ensure keys match document_generator function needs)
        po_pdf_data = {
            "purchase_order_number": str(generated_po_number),
            "po_date": current_utc_datetime.strftime("%Y-%m-%d"),
            "supplier": supplier_data_dict,
            "shipping_address": { # Extract relevant shipping info from the original order
                "name": order_data_dict.get('customer_name'),
                "street_1": order_data_dict.get('customer_shipping_address_line1'),
                "street_2": order_data_dict.get('customer_shipping_address_line2'),
                "city": order_data_dict.get('customer_shipping_city'),
                "state": order_data_dict.get('customer_shipping_state'),
                "zip": order_data_dict.get('customer_shipping_zip'),
                "country": order_data_dict.get('customer_shipping_country')
            },
            "items": po_line_items_input, # Use input items with negotiated cost
            "total_amount": po_total_amount,
            "payment_instructions": payment_instructions,
            "payment_terms": supplier_data_dict.get('payment_terms')
            # Add/adjust fields as needed by your specific PO template
        }

        try:
            # Call the function from your document_generator module
            po_pdf_bytes = document_generator.generate_purchase_order_pdf(po_pdf_data)
            if not po_pdf_bytes or not isinstance(po_pdf_bytes, bytes):
                 raise ValueError("generate_purchase_order_pdf did not return valid bytes.")
            print(f"DEBUG PROCESS_ORDER: Purchase Order PDF generated ({len(po_pdf_bytes)} bytes).")
        except Exception as pdf_po_e:
            print(f"ERROR PROCESS_ORDER: Failed to generate Purchase Order PDF: {pdf_po_e}")
            raise Exception(f"PO PDF generation failed: {pdf_po_e}") from pdf_po_e # Re-raise to trigger rollback

        # Prepare data for Packing Slip PDF (ensure keys match document_generator function needs)
        packing_slip_data = {
            "purchase_order_number": str(generated_po_number),
            "order_id": order_data_dict.get('bigcommerce_order_id'),
            "order_date": order_data_dict.get('date_created'),
             "shipping_address": { # Same shipping address
                "name": order_data_dict.get('customer_name'),
                "street_1": order_data_dict.get('customer_shipping_address_line1'),
                "street_2": order_data_dict.get('customer_shipping_address_line2'),
                "city": order_data_dict.get('customer_shipping_city'),
                "state": order_data_dict.get('customer_shipping_state'),
                "zip": order_data_dict.get('customer_shipping_zip'),
                "country": order_data_dict.get('customer_shipping_country')
            },
            "items": local_order_line_items_list # Use original items from local DB
            # Adjust fields as needed by your specific packing slip template
        }

        try:
             # Call the function from your document_generator module
            packing_slip_pdf_bytes = document_generator.generate_packing_slip_pdf(packing_slip_data)
            if not packing_slip_pdf_bytes or not isinstance(packing_slip_pdf_bytes, bytes):
                 raise ValueError("generate_packing_slip_pdf did not return valid bytes.")
            print(f"DEBUG PROCESS_ORDER: Packing Slip PDF generated ({len(packing_slip_pdf_bytes)} bytes).")
        except Exception as pdf_ps_e:
            print(f"ERROR PROCESS_ORDER: Failed to generate Packing Slip PDF: {pdf_ps_e}")
            raise Exception(f"Packing Slip PDF generation failed: {pdf_ps_e}") from pdf_ps_e # Re-raise
        # --- >>> END: Step 8 - Generate Documents <<< ---


        # --- TODO: Placeholder for next steps ---
        # 8. Generate Documents (PO PDF, Packing Slip PDF) using new_purchase_order_id, order_data_dict, supplier_data_dict, po_line_items_input etc.
        # 9. UPS Label Generation (call shipping_service.generate_ups_label) using order_data_dict, supplier_data_dict (for ship_from if applicable), total_shipment_weight_lbs. Store tracking_num, label_pdf_bytes.
        # 10. Database Writes (INSERT into shipments table with tracking_num, new_purchase_order_id, label GCS path etc.)
        # 11. Google Cloud Storage (Save PO PDF, Packing Slip PDF, Label PDF). Store GCS paths in DB.
        # 12. Email Documents to Supplier (call shipping_service.send_po_email with supplier_data_dict.get('email'), PO PDF, Packing Slip PDF).
        # 13. Update BigCommerce (call shipping_service.update_bigcommerce_order using order_data_dict.get('bigcommerce_order_id'), tracking_num).
        # 14. Update Local Order Status (in your 'orders' table to 'Processed' or 'Shipped').
        # --- END OF TODO ---
        print("DEBUG PROCESS_ORDER: Placeholder for UPS label generation and further processing...")

        # If all steps so far were successful:
        transaction.commit()
        print(f"DEBUG PROCESS_ORDER: Transaction committed for order {order_id} (PO created, Docs generated).")
        
        # Optionally save PDFs locally for testing:
        # try:
        #     with open(f"temp_po_{generated_po_number}.pdf", "wb") as f: f.write(po_pdf_bytes)
        #     with open(f"temp_ps_{generated_po_number}.pdf", "wb") as f: f.write(packing_slip_pdf_bytes)
        #     print("DEBUG PROCESS_ORDER: Temp PDF files saved locally.")
        # except Exception as save_e:
        #     print(f"WARN PROCESS_ORDER: Could not save temp PDF files locally: {save_e}")

        return jsonify({
            "message": f"Purchase Order {generated_po_number} created and documents generated successfully for order {order_id}.",
            "order_id": order_data_dict.get('id'),
            "purchase_order_db_id": new_purchase_order_id,
            "purchase_order_number": generated_po_number,
            "po_pdf_size": len(po_pdf_bytes) if po_pdf_bytes else 0,
            "packing_slip_pdf_size": len(packing_slip_pdf_bytes) if packing_slip_pdf_bytes else 0
        }), 201

    except Exception as e:
        if transaction and db_conn and not db_conn.closed:
             try:
                 print(f"DEBUG PROCESS_ORDER: Rolling back transaction due to error: {e}")
                 transaction.rollback()
             except Exception as rb_e:
                 print(f"ERROR PROCESS_ORDER: Error during transaction rollback: {rb_e}")
        else:
             print(f"DEBUG PROCESS_ORDER: Cannot rollback transaction (or not needed). Error: {e}")

        original_error_traceback = traceback.format_exc()
        print("--- ORIGINAL ERROR TRACEBACK ---")
        print(original_error_traceback)
        print("--- END ORIGINAL ERROR TRACEBACK ---")
        
        return jsonify({
            "error": "An unexpected error occurred during PO creation.", 
            "details": str(e),
        }), 500

    finally:
        if db_conn:
            if not db_conn.closed:
                print(f"DEBUG PROCESS_ORDER: Attempting to close database connection for order {order_id}")
                db_conn.close()
                print(f"DEBUG PROCESS_ORDER: Database connection closed for order {order_id}.")
            else:
                print(f"DEBUG PROCESS_ORDER: Database connection was already closed for order {order_id}.")
        else:
            print(f"DEBUG PROCESS_ORDER: No valid database connection object to close for order {order_id}.")

# --- Entry point for running the Flask app ---
# This block ensures app.run() is only called when the script is executed directly
if __name__ == '__main__':
    print(f"Starting Flask development development server...")
    # Ensure debug=True is off in production for security
    app.run(debug=True, host='127.0.0.1', port=8080)