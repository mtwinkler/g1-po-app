# app.py - UPDATED VERSION

import os
from flask import Flask, jsonify, request
import sqlalchemy
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector
import requests
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from decimal import Decimal

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
                # Ensure the try block is immediately followed by except/finally
                try: # This try block is for executing the insert statement
                     # --- Try to insert the order ---
                     # Use inserted_primary_key to get the ID instead of fetchone()
                     result = conn.execute(insert_order_stmt) # <-- Execution happens here

                     # --- NEW DEBUG PRINTS ---
                     print(f"DEBUG INGEST: Result object after execute: {result}")
                     print(f"DEBUG INGEST: Type of result object: {type(result)}")
                     # Check if inserted_primary_key attribute exists and print its value and type
                     if hasattr(result, 'inserted_primary_key'):
                          print(f"DEBUG INGEST: result.inserted_primary_key attribute exists.")
                          print(f"DEBUG INGEST: Value of result.inserted_primary_key: {result.inserted_primary_key}")
                          print(f"DEBUG INGEST: Type of result.inserted_primary_key: {type(result.inserted_primary_key)}")
                          # Check if it's a sequence (like tuple/list) and print its length
                          if isinstance(result.inserted_primary_key, (list, tuple)):
                               print(f"DEBUG INGEST: Length of result.inserted_primary_key: {len(result.inserted_primary_key)}")
                          # Attempt to print the first element safely
                          try:
                               print(f"DEBUG INGEST: First element (index 0) of inserted_primary_key: {result.inserted_primary_key[0]}")
                               print(f"DEBUG INGEST: Type of first element: {type(result.inserted_primary_key[0])}")
                          except IndexError:
                               print("DEBUG INGEST: inserted_primary_key is a sequence but is empty (IndexError).")
                          except Exception as access_err:
                               print(f"DEBUG INGEST: Error accessing index 0 of inserted_primary_key: {access_err}")
                     else:
                          print("DEBUG INGEST: result object DOES NOT HAVE 'inserted_primary_key' attribute.")
                     # --- END NEW DEBUG PRINTS ---


                     # Access the first element (the 'id') of the inserted_primary_key tuple
                     # This line will only be reached if inserted_primary_key exists and has index 0
                     inserted_order_id = result.inserted_primary_key[0] # <-- This line attempts access

                     print(f"DEBUG INGEST: Inserted new Order {order_id} with app ID {inserted_order_id}, status: {target_app_status}")
                     inserted_count_this_run += 1 # Count actual insertions
                except Exception as db_insert_error:
                      # Handle potential database insert errors (e.g., unique constraint violation if already exists)
                      print(f"DEBUG INGEST: !!! Error inserting Order {order_id} into DB: {db_insert_error}. Skipping line items and moving to next order.")
                      # No need to rollback yet, transaction is per batch. Just skip this order's remaining processing.
                      # Optionally log the order ID that failed to insert.
                      continue # Skip line item insertion and move to next order

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


# --- Entry point for running the Flask app ---
# This block ensures app.run() is only called when the script is executed directly
if __name__ == '__main__':
    print(f"Starting Flask development development server...")
    # Ensure debug=True is off in production for security
    app.run(debug=True, host='127.0.0.1', port=8080)