# order-processing-app/blueprints/orders.py

import traceback
from flask import Blueprint, jsonify, request, g, current_app
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timezone, timedelta
from decimal import Decimal # Ensure Decimal is imported
import base64
import sys
import re
import html
import json

from app import (
    engine, storage_client, verify_firebase_token,
    convert_row_to_dict, make_json_safe,
    _get_bc_shipping_address_id, get_hpe_mapping_with_fallback,
    bc_api_base_url_v2, bc_headers, bc_processing_status_id, bc_shipped_status_id, domestic_country_code,
    G1_ONSITE_FULFILLMENT_IDENTIFIER,
    SHIP_FROM_NAME, SHIP_FROM_CONTACT, SHIP_FROM_STREET1, SHIP_FROM_STREET2,
    SHIP_FROM_CITY, SHIP_FROM_STATE, SHIP_FROM_ZIP, SHIP_FROM_COUNTRY, SHIP_FROM_PHONE,
    COMPANY_LOGO_GCS_URI, GCS_BUCKET_NAME
)

import document_generator
import shipping_service
import email_service

import requests

orders_bp = Blueprint('orders_bp', __name__)

@orders_bp.route('/orders', methods=['GET'])
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

@orders_bp.route('/orders/<int:order_id>', methods=['GET'])
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
        # Ensure compliance_info is selected
        order_query = text("SELECT *, compliance_info FROM orders WHERE id = :order_id") 
        order_record = db_conn.execute(order_query, {"order_id": order_id}).fetchone()
        if not order_record:
            print(f"WARN GET_ORDER: Order with ID {order_id} not found.")
            return jsonify({"error": f"Order with ID {order_id} not found"}), 404
        
        order_data_dict = convert_row_to_dict(order_record)
        
        # Ensure compliance_info (JSONB from DB) is handled correctly if it's a string
        if 'compliance_info' in order_data_dict and isinstance(order_data_dict['compliance_info'], str):
            try:
                order_data_dict['compliance_info'] = json.loads(order_data_dict['compliance_info'])
            except json.JSONDecodeError:
                print(f"WARN GET_ORDER: Could not parse compliance_info JSON string for order {order_id}. Setting to empty dict.")
                order_data_dict['compliance_info'] = {} # Or None, depending on how frontend expects it
        elif 'compliance_info' not in order_data_dict or order_data_dict['compliance_info'] is None:
             order_data_dict['compliance_info'] = {} # Ensure it's at least an empty dict if null/missing

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

        if order_data_dict.get('status') == 'Processed':
            print(f"DEBUG GET_ORDER: Order {order_id} is 'Processed'. Fetching actual cost of goods sold.")
            cost_query = text("""
                SELECT SUM(poli.quantity * poli.unit_cost)
                FROM po_line_items poli
                JOIN purchase_orders po ON poli.purchase_order_id = po.id
                WHERE po.order_id = :order_id_param
            """)
            total_actual_cost = db_conn.execute(cost_query, {"order_id_param": order_id}).scalar_one_or_none()
            
            if total_actual_cost is not None:
                order_data_dict['actual_cost_of_goods_sold'] = total_actual_cost
            else:
                order_data_dict['actual_cost_of_goods_sold'] = Decimal('0.00') 
        
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


@orders_bp.route('/orders/status-counts', methods=['GET'])
@verify_firebase_token
def get_order_status_counts():
    # ... (This function remains unchanged) ...
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

@orders_bp.route('/orders/<int:order_id>/status', methods=['POST'])
@verify_firebase_token
def update_order_status(order_id):
    # ... (This function remains unchanged) ...
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


@orders_bp.route('/ingest_orders', methods=['POST'])
@verify_firebase_token
def ingest_orders_route():
    try:
        print("INFO INGEST: Received request for /api/ingest_orders", flush=True)
        if not bc_api_base_url_v2 or not bc_headers:
            print("ERROR INGEST: BigCommerce API credentials not fully configured.", flush=True)
            return jsonify({"message": "BigCommerce API credentials not fully configured."}), 500
        try:
            target_status_id = int(bc_processing_status_id)
        except (ValueError, TypeError):
            print(f"ERROR INGEST: BC_PROCESSING_STATUS_ID '{bc_processing_status_id}' is invalid.", flush=True)
            return jsonify({"message": f"BC_PROCESSING_STATUS_ID '{bc_processing_status_id}' is invalid."}), 500

        if engine is None:
            print("ERROR INGEST: Database engine not initialized.", flush=True)
            return jsonify({"message": "Database engine not initialized."}), 500

        orders_list_endpoint = f"{bc_api_base_url_v2}orders"
        api_params = {'status_id': target_status_id, 'sort': 'date_created:asc', 'limit': 250}
        print(f"DEBUG INGEST: Fetching orders with status ID {target_status_id} from {orders_list_endpoint}", flush=True)

        response = requests.get(orders_list_endpoint, headers=bc_headers, params=api_params)
        response.raise_for_status() 

        orders_list_from_bc = []
        if response.text and response.text.strip(): 
            try:
                orders_list_from_bc = response.json()
            except json.JSONDecodeError as json_err:
                print(f"ERROR INGEST: Failed to decode JSON from BigCommerce. Error: {json_err}. Response text: {response.text[:500]}", flush=True)
                return jsonify({"message": "Ingestion failed: Could not parse response from BigCommerce."}), 500
        else:
            print("INFO INGEST: BigCommerce API returned an empty response. No orders to process for this status.", flush=True)
        
        if not isinstance(orders_list_from_bc, list):
            print(f"ERROR INGEST: Unexpected API response format after JSON parse. Expected list, got {type(orders_list_from_bc)}", flush=True)
            return jsonify({"message": "Ingestion failed: Unexpected API response format."}), 500

        if not orders_list_from_bc:
            print(f"INFO INGEST: Successfully ingested 0 orders with BC status ID '{target_status_id}'.", flush=True)
            return jsonify({"message": f"Successfully ingested 0 orders with BC status ID '{target_status_id}'."}), 200

        ingested_count, inserted_count_this_run, updated_count_this_run = 0, 0, 0
        with engine.connect() as conn:
            with conn.begin():
                print(f"DEBUG INGEST: Processing {len(orders_list_from_bc)} orders from BigCommerce.", flush=True)
                for bc_order_summary in orders_list_from_bc:
                    order_id_from_bc = bc_order_summary.get('id')
                    print(f"--- DEBUG INGEST FOR BC ORDER ID: {order_id_from_bc} ---")
                    bc_billing_address = bc_order_summary.get('billing_address', {})
                    if order_id_from_bc is None:
                        print("WARN INGEST: Skipping order summary with missing 'id'.", flush=True)
                        continue

                    shipping_addresses_list, products_list = [], []
                    is_international = False
                    calculated_shipping_method_name = 'N/A'
                    customer_shipping_address = {}

                    try:
                        shipping_addr_url = f"{bc_api_base_url_v2}orders/{order_id_from_bc}/shippingaddresses"
                        shipping_res = requests.get(shipping_addr_url, headers=bc_headers)
                        shipping_res.raise_for_status()
                        shipping_addresses_list = shipping_res.json()
                        if shipping_addresses_list and isinstance(shipping_addresses_list, list) and shipping_addresses_list[0]:
                            customer_shipping_address = shipping_addresses_list[0]
                            shipping_country_code = customer_shipping_address.get('country_iso2')
                            is_international = bool(shipping_country_code and shipping_country_code.upper() != domestic_country_code.upper())
                            calculated_shipping_method_name = customer_shipping_address.get('shipping_method', bc_order_summary.get('shipping_method', 'N/A'))
                        else:
                            print(f"WARN INGEST: No valid shipping address found for BC Order {order_id_from_bc}.", flush=True)

                        products_url = f"{bc_api_base_url_v2}orders/{order_id_from_bc}/products"
                        products_res = requests.get(products_url, headers=bc_headers)
                        products_res.raise_for_status()
                        products_list = products_res.json()
                        if not isinstance(products_list, list):
                            print(f"WARN INGEST: Products list for BC Order {order_id_from_bc} is not a list. Treating as empty.", flush=True)
                            products_list = []
                    except requests.exceptions.RequestException as sub_req_e:
                        print(f"ERROR INGEST: Could not fetch sub-resources for BC Order {order_id_from_bc}: {sub_req_e}. Skipping this order.", flush=True)
                        continue
                    
                    # --- START: REFINED COMMENT PARSING LOGIC ---
                    raw_customer_message = bc_order_summary.get('customer_message', '').strip()
                    
                    compliance_ids_data = {} 
                    message_for_freight_and_user_notes = raw_customer_message 
                    compliance_block_raw = None

                    compliance_separator_literal = " ||| "
                    # Regex to find the compliance block at the end, optionally preceded by the separator.
                    # Group 1: Everything before the potential compliance block (includes user notes and freight)
                    # Group 2: (Optional) The separator " ||| "
                    # Group 3: (Optional) The compliance block itself "[...];"
                    match = re.search(r'^(.*?)(?:\s*' + re.escape(compliance_separator_literal) + r'\s*(\[.*?\];))?$', raw_customer_message, re.DOTALL)

                    if match:
                        # If group 3 (compliance block) exists, it was preceded by the separator (group 2 might be None if no separator but block at end)
                        # or it was the only thing.
                        potential_compliance_block = match.group(3)
                        text_before_compliance_block = match.group(1).strip()

                        if potential_compliance_block and potential_compliance_block.startswith("[") and potential_compliance_block.endswith("];"):
                            compliance_block_raw = potential_compliance_block
                            message_for_freight_and_user_notes = text_before_compliance_block
                        else:
                            # No valid compliance block found with the separator, so the whole thing is for freight/user notes
                            message_for_freight_and_user_notes = raw_customer_message
                    
                    # Handle case where the *entire message* is just the compliance block without a separator
                    if not compliance_block_raw and raw_customer_message.startswith("[") and raw_customer_message.endswith("];"):
                         # Check if this block looks like our compliance format to avoid misinterpreting other bracketed notes
                        if re.match(r'^\[([A-Za-z0-9\s\(\)\-\.\/]+:\s*[^;]+;\s*)+\];$', raw_customer_message):
                            compliance_block_raw = raw_customer_message
                            message_for_freight_and_user_notes = ""


                    if compliance_block_raw: # This check is now implicitly done by the regex logic correctly setting it or not
                        # The check compliance_block_raw.startswith("[") and compliance_block_raw.endswith("];") is important
                        compliance_content = compliance_block_raw[1:-2] # Remove [ and ];
                        id_pairs = compliance_content.split(';')
                        for pair in id_pairs:
                            pair = pair.strip() 
                            if pair and ':' in pair: 
                                label, value = pair.split(':', 1)
                                compliance_ids_data[label.strip()] = value.strip()
                    # message_for_freight_and_user_notes now contains text excluding the compliance block

                    parsed_customer_carrier, parsed_customer_selected_ups_service, parsed_customer_ups_account_num = None, None, None
                    is_bill_to_customer_ups_acct = False
                    parsed_customer_selected_fedex_service, parsed_customer_fedex_account_num = None, None
                    is_bill_to_customer_fedex_acct = False
                    customer_ups_account_zipcode = None
                    # Initialize customer_notes_for_db with the potentially cleaned message
                    customer_notes_for_db = message_for_freight_and_user_notes.strip() 

                    freight_delimiter_pattern = " || " 
                    if freight_delimiter_pattern + "Carrier:" in message_for_freight_and_user_notes and \
                       (freight_delimiter_pattern + "Account#:" in message_for_freight_and_user_notes or "account#:" in message_for_freight_and_user_notes.lower()): # More flexible account check
                        
                        freight_parts = message_for_freight_and_user_notes.split(freight_delimiter_pattern)
                        temp_carrier, temp_service, temp_account, temp_zip = None, None, None, None
                        
                        customer_notes_for_db = freight_parts[0].strip() # This is the user's actual notes
                        
                        for i in range(1, len(freight_parts)): 
                            part_content = freight_parts[i]
                            content_lower = part_content.lower()
                            if content_lower.startswith("carrier:"): temp_carrier = part_content.split(":", 1)[1].strip()
                            elif content_lower.startswith("service:"): temp_service = part_content.split(":", 1)[1].strip()
                            elif content_lower.startswith("account#:"): temp_account = part_content.split(":", 1)[1].strip()
                            elif content_lower.startswith("zip:"): temp_zip = part_content.split(":",1)[1].strip()

                        if temp_carrier and temp_account:
                            parsed_customer_carrier = temp_carrier
                            if "UPS" in temp_carrier.upper():
                                parsed_customer_selected_ups_service = temp_service
                                parsed_customer_ups_account_num = temp_account
                                customer_ups_account_zipcode = temp_zip
                                is_bill_to_customer_ups_acct = True
                            elif "FEDEX" in temp_carrier.upper() or "FED EX" in temp_carrier.upper():
                                parsed_customer_selected_fedex_service = temp_service
                                parsed_customer_fedex_account_num = temp_account
                                is_bill_to_customer_fedex_acct = True
                    # else: customer_notes_for_db was already set from message_for_freight_and_user_notes
                    
                    if customer_notes_for_db: 
                        sensitive_pattern = re.compile(r'\*{10}.*?\*{10}', re.DOTALL)
                        customer_notes_for_db = sensitive_pattern.sub('', customer_notes_for_db).strip()
                    # --- END: REFINED COMMENT PARSING LOGIC ---

                    if compliance_ids_data:
                        print(f"DEBUG INGEST: Parsed Compliance IDs for BC Order {order_id_from_bc}: {compliance_ids_data}", flush=True)
                    else:
                        print(f"DEBUG INGEST: No Compliance IDs parsed for BC Order {order_id_from_bc}. Raw message: '{raw_customer_message}' -> Freight/User Notes part: '{message_for_freight_and_user_notes}'", flush=True)

                    db_compliance_info = json.dumps(compliance_ids_data) if compliance_ids_data else None

                    existing_order_row = conn.execute(
                        text("""SELECT id, status, is_international, payment_method,
                                      bigcommerce_order_tax, customer_notes, compliance_info,
                                      customer_selected_freight_service, customer_ups_account_number, customer_ups_account_zipcode,
                                      is_bill_to_customer_account,
                                      customer_selected_fedex_service, customer_fedex_account_number,
                                      is_bill_to_customer_fedex_account,
                                      bc_shipping_cost_ex_tax,
                                      customer_billing_first_name, customer_billing_last_name, customer_billing_company,
                                      customer_billing_street_1, customer_billing_street_2, customer_billing_city,
                                      customer_billing_state, customer_billing_zip, customer_billing_country,
                                      customer_billing_country_iso2, customer_billing_phone
                              FROM orders WHERE bigcommerce_order_id = :bc_order_id"""),
                        {"bc_order_id": order_id_from_bc}
                    ).fetchone()

                    bc_total_tax = Decimal(bc_order_summary.get('total_tax', '0.00'))
                    bc_total_inc_tax = Decimal(bc_order_summary.get('total_inc_tax', '0.00'))
                    bc_shipping_cost_from_api = Decimal(bc_order_summary.get('shipping_cost_ex_tax', '0.00'))
                    current_time_utc = datetime.now(timezone.utc)

                    if existing_order_row:
                        db_status = existing_order_row.status
                        finalized_or_manual_statuses = ['Processed', 'Completed Offline', 'pending', 'RFQ Sent', 'international_manual']
                        if db_status in finalized_or_manual_statuses:
                            ingested_count += 1; continue

                        update_fields = {}
                        if existing_order_row.is_international != is_international: update_fields['is_international'] = is_international
                        if existing_order_row.payment_method != bc_order_summary.get('payment_method'): update_fields['payment_method'] = bc_order_summary.get('payment_method')
                        if existing_order_row.bigcommerce_order_tax != bc_total_tax: update_fields['bigcommerce_order_tax'] = bc_total_tax
                        
                        if existing_order_row.customer_notes != customer_notes_for_db: 
                            update_fields['customer_notes'] = customer_notes_for_db
                        
                        existing_compliance_info_from_db = existing_order_row.compliance_info
                        
                        parsed_existing_compliance_dict = {}
                        if isinstance(existing_compliance_info_from_db, str):
                            try: parsed_existing_compliance_dict = json.loads(existing_compliance_info_from_db) if existing_compliance_info_from_db else {}
                            except json.JSONDecodeError:  parsed_existing_compliance_dict = {}
                        elif isinstance(existing_compliance_info_from_db, dict): 
                            parsed_existing_compliance_dict = existing_compliance_info_from_db if existing_compliance_info_from_db else {}

                        if parsed_existing_compliance_dict != compliance_ids_data:
                             update_fields['compliance_info'] = db_compliance_info 
                        
                        if not hasattr(existing_order_row, 'bc_shipping_cost_ex_tax') or existing_order_row.bc_shipping_cost_ex_tax != bc_shipping_cost_from_api:
                            update_fields['bc_shipping_cost_ex_tax'] = bc_shipping_cost_from_api
                        
                        billing_fields_to_check = {
                            'customer_billing_first_name': bc_billing_address.get('first_name'), 'customer_billing_last_name': bc_billing_address.get('last_name'),
                            'customer_billing_company': bc_billing_address.get('company'), 'customer_billing_street_1': bc_billing_address.get('street_1'),
                            'customer_billing_street_2': bc_billing_address.get('street_2'), 'customer_billing_city': bc_billing_address.get('city'),
                            'customer_billing_state': bc_billing_address.get('state'), 'customer_billing_zip': bc_billing_address.get('zip'),
                            'customer_billing_country': bc_billing_address.get('country'), 'customer_billing_country_iso2': bc_billing_address.get('country_iso2'),
                            'customer_billing_phone': bc_billing_address.get('phone')
                        }
                        for field_name, new_value in billing_fields_to_check.items():
                            if not hasattr(existing_order_row, field_name) or getattr(existing_order_row, field_name) != new_value:
                                update_fields[field_name] = new_value

                        if existing_order_row.customer_selected_freight_service != parsed_customer_selected_ups_service: update_fields['customer_selected_freight_service'] = parsed_customer_selected_ups_service
                        if existing_order_row.customer_ups_account_number != parsed_customer_ups_account_num: update_fields['customer_ups_account_number'] = parsed_customer_ups_account_num
                        if existing_order_row.customer_ups_account_zipcode != customer_ups_account_zipcode: update_fields['customer_ups_account_zipcode'] = customer_ups_account_zipcode
                        if existing_order_row.is_bill_to_customer_account != is_bill_to_customer_ups_acct: update_fields['is_bill_to_customer_account'] = is_bill_to_customer_ups_acct

                        if existing_order_row.customer_selected_fedex_service != parsed_customer_selected_fedex_service: update_fields['customer_selected_fedex_service'] = parsed_customer_selected_fedex_service
                        if existing_order_row.customer_fedex_account_number != parsed_customer_fedex_account_num: update_fields['customer_fedex_account_number'] = parsed_customer_fedex_account_num
                        if existing_order_row.is_bill_to_customer_fedex_account != is_bill_to_customer_fedex_acct: update_fields['is_bill_to_customer_fedex_account'] = is_bill_to_customer_fedex_acct

                        if db_status not in finalized_or_manual_statuses:
                            new_app_status_by_ingest = 'international_manual' if is_international else 'new'
                            if db_status != new_app_status_by_ingest: update_fields['status'] = new_app_status_by_ingest

                        if update_fields:
                            update_fields['updated_at'] = current_time_utc
                            set_clauses = [f"{key} = :{key}" for key in update_fields.keys()]
                            conn.execute(text(f"UPDATE orders SET {', '.join(set_clauses)} WHERE id = :id"), {"id": existing_order_row.id, **update_fields})
                            updated_count_this_run += 1
                    else: 
                        target_app_status = 'international_manual' if is_international else 'new'
                        order_values = {
                            "bigcommerce_order_id": order_id_from_bc,
                            "customer_company": customer_shipping_address.get('company'),
                            "customer_name": f"{customer_shipping_address.get('first_name', '')} {customer_shipping_address.get('last_name', '')}".strip(),
                            "customer_shipping_address_line1": customer_shipping_address.get('street_1'), 
                            "customer_shipping_address_line2": customer_shipping_address.get('street_2'),
                            "customer_shipping_city": customer_shipping_address.get('city'), 
                            "customer_shipping_state": customer_shipping_address.get('state'),
                            "customer_shipping_zip": customer_shipping_address.get('zip'),
                            "customer_shipping_country": customer_shipping_address.get('country'),
                            "customer_shipping_country_iso2": customer_shipping_address.get('country_iso2'),
                            "customer_phone": customer_shipping_address.get('phone'), 
                            "customer_email": bc_billing_address.get('email', customer_shipping_address.get('email')),
                            "customer_shipping_method": calculated_shipping_method_name, 
                            "customer_notes": customer_notes_for_db, 
                            "compliance_info": db_compliance_info, 
                            "order_date": datetime.strptime(bc_order_summary['date_created'], '%a, %d %b %Y %H:%M:%S %z').replace(tzinfo=timezone.utc) if bc_order_summary.get('date_created') else current_time_utc,
                            "total_sale_price": bc_total_inc_tax, 
                            "bigcommerce_order_tax": bc_total_tax, 
                            "bc_shipping_cost_ex_tax": bc_shipping_cost_from_api,
                            "status": target_app_status, 
                            "is_international": is_international, 
                            "payment_method": bc_order_summary.get('payment_method'),
                            "created_at": current_time_utc, "updated_at": current_time_utc,
                            "customer_selected_freight_service": parsed_customer_selected_ups_service, 
                            "customer_ups_account_number": parsed_customer_ups_account_num,
                            "customer_ups_account_zipcode": customer_ups_account_zipcode,
                            "is_bill_to_customer_account": is_bill_to_customer_ups_acct,
                            "customer_selected_fedex_service": parsed_customer_selected_fedex_service, 
                            "customer_fedex_account_number": parsed_customer_fedex_account_num,
                            "is_bill_to_customer_fedex_account": is_bill_to_customer_fedex_acct,
                            "customer_billing_first_name": bc_billing_address.get('first_name'), 
                            "customer_billing_last_name": bc_billing_address.get('last_name'),
                            "customer_billing_company": bc_billing_address.get('company'), 
                            "customer_billing_street_1": bc_billing_address.get('street_1'),
                            "customer_billing_street_2": bc_billing_address.get('street_2'), 
                            "customer_billing_city": bc_billing_address.get('city'),
                            "customer_billing_state": bc_billing_address.get('state'), 
                            "customer_billing_zip": bc_billing_address.get('zip'),
                            "customer_billing_country": bc_billing_address.get('country'), 
                            "customer_billing_country_iso2": bc_billing_address.get('country_iso2'),
                            "customer_billing_phone": bc_billing_address.get('phone')
                        }
                        
                        order_columns = list(order_values.keys())
                        order_placeholders = [f":{col}" for col in order_columns]
                        insert_sql_str = f"INSERT INTO orders ({', '.join(order_columns)}) VALUES ({', '.join(order_placeholders)}) RETURNING id"
                        insert_sql = text(insert_sql_str)
                        inserted_order_id = conn.execute(insert_sql, order_values).scalar_one()
                        inserted_count_this_run += 1

                        if products_list:
                            for item in products_list:
                                if not isinstance(item, dict): continue
                                li_values = {"order_id": inserted_order_id, "bigcommerce_line_item_id": item.get('id'), "sku": item.get('sku'), "name": item.get('name'), "quantity": item.get('quantity'), "sale_price": Decimal(item.get('price_ex_tax', '0.00')), "created_at": current_time_utc, "updated_at": current_time_utc}
                                li_cols_list = list(li_values.keys())
                                li_placeholders = [f":{col}" for col in li_cols_list]
                                conn.execute(text(f"INSERT INTO order_line_items ({', '.join(li_cols_list)}) VALUES ({', '.join(li_placeholders)})"), li_values)
                    ingested_count += 1
        print(f"INFO INGEST: Processed {ingested_count} orders. Inserted: {inserted_count_this_run}, Updated: {updated_count_this_run}.", flush=True)
        return jsonify({"message": f"Processed {ingested_count} orders. Inserted {inserted_count_this_run} new. Updated {updated_count_this_run}."}), 200
    except requests.exceptions.RequestException as req_e:
        error_msg = f"BC API Request failed: {req_e}"
        status_code, resp_preview = (req_e.response.status_code, req_e.response.text[:500]) if req_e.response is not None else ('N/A', 'N/A')
        print(f"ERROR INGEST: {error_msg}, Status: {status_code}, Response: {resp_preview}", flush=True); traceback.print_exc(file=sys.stderr); sys.stderr.flush()
        return jsonify({"message": error_msg, "status_code": status_code, "response_preview": resp_preview}), 500
    except Exception as e:
        print(f"ERROR INGEST: Unexpected error: {e}", flush=True); traceback.print_exc(file=sys.stderr); sys.stderr.flush()
        return jsonify({"message": f"Unexpected error: {str(e)}", "error_type": type(e).__name__}), 500

@orders_bp.route('/orders/<int:order_id>/process', methods=['POST'])
@verify_firebase_token
def process_order_route(order_id):
    # ... (This function remains unchanged from the version you provided earlier) ...
    print(f"DEBUG PROCESS_ORDER: Received request to process order ID: {order_id}", flush=True)
    db_conn, transaction, processed_pos_info_for_response = None, None, []
    try:
        payload = request.get_json()
        if not payload or 'assignments' not in payload or not isinstance(payload['assignments'], list):
            print("ERROR PROCESS_ORDER: Invalid or missing 'assignments' array in payload", flush=True)
            return jsonify({"error": "Invalid or missing 'assignments' array in payload"}), 400

        assignments = payload['assignments']
        if not assignments:
            print("ERROR PROCESS_ORDER: Assignments array cannot be empty.", flush=True)
            return jsonify({"error": "Assignments array cannot be empty."}), 400

        if engine is None:
            print("ERROR PROCESS_ORDER: Database engine not available.", flush=True)
            return jsonify({"error": "Database engine not available."}), 500

        db_conn = engine.connect()
        transaction = db_conn.begin()

        order_record = db_conn.execute(
            text("""SELECT * FROM orders WHERE id = :id"""),
            {"id": order_id}
        ).fetchone()

        if not order_record:
            if transaction.is_active: transaction.rollback()
            return jsonify({"error": f"Order with ID {order_id} not found"}), 404

        order_data_dict_original = convert_row_to_dict(order_record)

        order_status_from_db = order_data_dict_original.get('status')
        if order_status_from_db and order_status_from_db.lower() in ['processed', 'completed offline']:
            if transaction.is_active: transaction.rollback()
            return jsonify({"error": f"Order {order_id} status is '{order_status_from_db}' and cannot be reprocessed."}), 400

        local_order_line_items_records = db_conn.execute(
            text("SELECT id AS line_item_id, bigcommerce_line_item_id, sku AS original_sku, name AS line_item_name, quantity FROM order_line_items WHERE order_id = :order_id_param ORDER BY id"),
            {"order_id_param": order_id}
        ).fetchall()
        local_order_line_items_list = [convert_row_to_dict(row) for row in local_order_line_items_records]
        all_original_order_line_item_db_ids = {item['line_item_id'] for item in local_order_line_items_list}
        processed_original_order_line_item_db_ids_this_batch = set()

        current_utc_datetime = datetime.now(timezone.utc)

        actual_supplier_assignments = [a for a in assignments if a.get('supplier_id') != G1_ONSITE_FULFILLMENT_IDENTIFIER]
        is_multi_actual_supplier_po_scenario = len(actual_supplier_assignments) > 1

        next_sequence_num = None
        if actual_supplier_assignments:
            starting_po_sequence = 200001
            max_po_query = text("SELECT MAX(CAST(numeric_po_number AS INTEGER)) FROM (SELECT po_number AS numeric_po_number FROM purchase_orders WHERE CAST(po_number AS TEXT) ~ '^[0-9]+$') AS numeric_pos")
            max_po_value_from_db = db_conn.execute(max_po_query).scalar_one_or_none()
            next_sequence_num = starting_po_sequence
            if max_po_value_from_db is not None:
                try:
                    next_sequence_num = max(starting_po_sequence, int(max_po_value_from_db) + 1)
                except ValueError:
                    print(f"WARN PROCESS_ORDER: Could not parse max PO number '{max_po_value_from_db}'. Defaulting PO sequence.", flush=True)

        for assignment_data in assignments:
            supplier_id_from_payload = assignment_data.get('supplier_id')
            shipment_method_from_processing_form = assignment_data.get('shipment_method')
            total_shipment_weight_lbs_str = assignment_data.get('total_shipment_weight_lbs')
            payment_instructions_from_frontend = assignment_data.get('payment_instructions', "")
            po_line_items_input = assignment_data.get('po_line_items', [])

            carrier_from_payload = assignment_data.get('carrier', 'ups').lower()
            is_bill_to_customer_fedex_from_payload = assignment_data.get('is_bill_to_customer_fedex_account', False)
            customer_fedex_account_from_payload = assignment_data.get('customer_fedex_account_number')
            is_bill_to_customer_ups_from_payload = assignment_data.get('is_bill_to_customer_ups_account', False)
            customer_ups_account_from_payload = assignment_data.get('customer_ups_account_number')
            is_blind_drop_ship_from_payload = assignment_data.get('is_blind_drop_ship', False)

            g1_ps_signed_url, g1_label_signed_url = None, None
            po_pdf_signed_url, ps_signed_url_supplier, label_signed_url_supplier = None, None, None

            order_data_for_label = order_data_dict_original.copy() 
            
            if carrier_from_payload == 'fedex':
                order_data_for_label['is_bill_to_customer_fedex_account'] = is_bill_to_customer_fedex_from_payload
                order_data_for_label['customer_fedex_account_number'] = customer_fedex_account_from_payload
                order_data_for_label['is_bill_to_customer_account'] = False 
                order_data_for_label['customer_ups_account_number'] = None
            elif carrier_from_payload == 'ups':
                order_data_for_label['is_bill_to_customer_account'] = is_bill_to_customer_ups_from_payload
                order_data_for_label['customer_ups_account_number'] = customer_ups_account_from_payload
                order_data_for_label['is_bill_to_customer_fedex_account'] = False
                order_data_for_label['customer_fedex_account_number'] = None
            
            effective_ups_third_party_zip = None
            if carrier_from_payload == 'ups' and is_bill_to_customer_ups_from_payload:
                customer_ups_account_zipcode_from_db = order_data_dict_original.get('customer_ups_account_zipcode')
                customer_billing_zip_from_db = order_data_dict_original.get('customer_billing_zip')

                if customer_ups_account_zipcode_from_db and str(customer_ups_account_zipcode_from_db).strip() and str(customer_ups_account_zipcode_from_db).strip().lower() != 'none':
                    effective_ups_third_party_zip = str(customer_ups_account_zipcode_from_db).strip()
                elif customer_billing_zip_from_db and str(customer_billing_zip_from_db).strip():
                    effective_ups_third_party_zip = str(customer_billing_zip_from_db).strip()
                    print(f"DEBUG PROCESS_ORDER: Using customer_billing_zip ('{effective_ups_third_party_zip}') for UPS 3rd party as customer_ups_account_zipcode was not set or invalid.", flush=True)
                else:
                    print(f"WARN PROCESS_ORDER: Neither customer_ups_account_zipcode nor customer_billing_zip is valid for UPS 3rd party billing. Label generation may fail or default to BillShipper.", flush=True)
                order_data_for_label['customer_ups_account_zipcode'] = effective_ups_third_party_zip


            current_ship_from_address = {}
            effective_logo_gcs_uri = COMPANY_LOGO_GCS_URI
            packing_slip_custom_ship_from = None

            if is_blind_drop_ship_from_payload:
                print(f"DEBUG PROCESS_ORDER: Blind drop ship for order {order_id}, assignment to supplier/mode {supplier_id_from_payload}. Using customer billing address as ship-from.", flush=True)
                current_ship_from_address = {
                    'name': order_data_dict_original.get('customer_billing_company') or f"{order_data_dict_original.get('customer_billing_first_name', '')} {order_data_dict_original.get('customer_billing_last_name', '')}".strip(),
                    'contact_person': f"{order_data_dict_original.get('customer_billing_first_name', '')} {order_data_dict_original.get('customer_billing_last_name', '')}".strip(),
                    'street_1': order_data_dict_original.get('customer_billing_street_1'),
                    'street_2': order_data_dict_original.get('customer_billing_street_2', ''),
                    'city': order_data_dict_original.get('customer_billing_city'),
                    'state': order_data_dict_original.get('customer_billing_state'),
                    'zip': order_data_dict_original.get('customer_billing_zip'),
                    'country': order_data_dict_original.get('customer_billing_country_iso2', 'US'),
                    'phone': order_data_dict_original.get('customer_billing_phone')
                }
                if not all(val for key, val in current_ship_from_address.items() if key not in ['street_2', 'contact_person']):
                    raise ValueError("Blind drop ship selected, but customer billing address (used as ship-from) is incomplete. Required: name/company, street1, city, state, zip, country, phone.")
                effective_logo_gcs_uri = None
                packing_slip_custom_ship_from = current_ship_from_address
            else:
                current_ship_from_address = {
                    'name': SHIP_FROM_NAME, 'contact_person': SHIP_FROM_CONTACT,
                    'street_1': SHIP_FROM_STREET1, 'street_2': SHIP_FROM_STREET2,
                    'city': SHIP_FROM_CITY, 'state': SHIP_FROM_STATE,
                    'zip': SHIP_FROM_ZIP, 'country': SHIP_FROM_COUNTRY, 'phone': SHIP_FROM_PHONE
                }

            method_for_label_generation = shipment_method_from_processing_form
            if carrier_from_payload == 'ups' and is_bill_to_customer_ups_from_payload and order_data_dict_original.get('customer_selected_freight_service'):
                method_for_label_generation = order_data_dict_original.get('customer_selected_freight_service')
            elif carrier_from_payload == 'fedex' and is_bill_to_customer_fedex_from_payload and order_data_dict_original.get('customer_selected_fedex_service'):
                 method_for_label_generation = order_data_dict_original.get('customer_selected_fedex_service')
            elif not shipment_method_from_processing_form and (local_order_line_items_list or supplier_id_from_payload == G1_ONSITE_FULFILLMENT_IDENTIFIER):
                method_for_label_generation = order_data_dict_original.get('customer_shipping_method', 'UPS Ground')
            elif not (local_order_line_items_list or (supplier_id_from_payload == G1_ONSITE_FULFILLMENT_IDENTIFIER and po_line_items_input)): # Changed from local_order_line_items_list to po_line_items_input for G1
                method_for_label_generation = None

            if supplier_id_from_payload == G1_ONSITE_FULFILLMENT_IDENTIFIER:
                g1_ps_blob_name_for_db, g1_label_blob_name_for_db = None, None
                g1_tracking_number = None
                generated_label_pdf_bytes = None

                if not local_order_line_items_list: # G1 Onsite fulfillment, but order has no line items in DB
                    print(f"DEBUG PROCESS_ORDER (G1 Onsite): No line items for order {order_id}. Skipping PS/Label.", flush=True)
                else: # G1 Onsite, and there are line items
                    if not total_shipment_weight_lbs_str or not method_for_label_generation:
                        # Error only if blind drop ship OR not blind but has items that would need a label
                         if is_blind_drop_ship_from_payload and (not total_shipment_weight_lbs_str or not method_for_label_generation):
                             raise ValueError("Blind Drop Ship (G1): Shipment method and weight are required when items exist.")
                         elif not is_blind_drop_ship_from_payload: # Not blind, but implies shipping from G1
                             raise ValueError("Shipment method and weight are required for G1 Onsite Fulfillment with items.")
                    try:
                        current_g1_weight = float(total_shipment_weight_lbs_str)
                        if current_g1_weight <= 0: raise ValueError("Shipment weight must be positive for G1 Onsite Fulfillment.")
                    except ValueError:
                        raise ValueError("Invalid shipment weight format for G1 Onsite Fulfillment.")

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
                        ps_args = {
                            "order_data": order_data_for_label,
                            "items_in_this_shipment": items_for_g1_packing_slip,
                            "items_shipping_separately": [],
                            "logo_gcs_uri": effective_logo_gcs_uri,
                            "is_g1_onsite_fulfillment": True,
                            "is_blind_slip": is_blind_drop_ship_from_payload,
                            "custom_ship_from_address": packing_slip_custom_ship_from
                        }
                        g1_packing_slip_pdf_bytes = document_generator.generate_packing_slip_pdf(**ps_args)
                        if g1_packing_slip_pdf_bytes and storage_client and GCS_BUCKET_NAME:
                            ts_suffix = current_utc_datetime.strftime("%Y%m%d%H%M%S")
                            g1_ps_blob_name = f"processed_orders/order_{order_data_for_label['bigcommerce_order_id']}_G1Onsite/ps_g1_{'blind_' if is_blind_drop_ship_from_payload else ''}{ts_suffix}.pdf"
                            g1_ps_blob_name_for_db = f"gs://{GCS_BUCKET_NAME}/{g1_ps_blob_name}"
                            g1_ps_blob = storage_client.bucket(GCS_BUCKET_NAME).blob(g1_ps_blob_name)
                            g1_ps_blob.upload_from_string(g1_packing_slip_pdf_bytes, content_type='application/pdf')
                            try: g1_ps_signed_url = g1_ps_blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
                            except Exception as e_sign_g1ps: print(f"ERROR G1_ONSITE generating signed URL for PS: {e_sign_g1ps}", flush=True)

                    if shipping_service and total_shipment_weight_lbs_str and method_for_label_generation and local_order_line_items_list:
                        if all([current_ship_from_address.get('street_1'), current_ship_from_address.get('city'), current_ship_from_address.get('state'), current_ship_from_address.get('zip'), current_ship_from_address.get('country'), current_ship_from_address.get('phone')]):
                            try:
                                if carrier_from_payload == 'fedex':
                                    generated_label_pdf_bytes, g1_tracking_number = shipping_service.generate_fedex_label(
                                        order_data=order_data_for_label, ship_from_address=current_ship_from_address,
                                        total_weight_lbs=float(total_shipment_weight_lbs_str),
                                        customer_shipping_method_name=method_for_label_generation )
                                else: 
                                    generated_label_pdf_bytes, g1_tracking_number = shipping_service.generate_ups_label(
                                        order_data=order_data_for_label, ship_from_address=current_ship_from_address,
                                        total_weight_lbs=float(total_shipment_weight_lbs_str),
                                        customer_shipping_method_name=method_for_label_generation,
                                        is_bill_to_customer_ups_account=is_bill_to_customer_ups_from_payload,
                                        customer_ups_account_number=customer_ups_account_from_payload,
                                        customer_ups_account_zipcode=effective_ups_third_party_zip
                                    )

                                if generated_label_pdf_bytes and g1_tracking_number and storage_client and GCS_BUCKET_NAME:
                                    ts_suffix = current_utc_datetime.strftime("%Y%m%d%H%M%S")
                                    g1_label_blob_name = f"processed_orders/order_{order_data_for_label['bigcommerce_order_id']}_G1Onsite/label_{carrier_from_payload.upper()}_{g1_tracking_number}_{ts_suffix}.pdf"
                                    g1_label_blob_name_for_db = f"gs://{GCS_BUCKET_NAME}/{g1_label_blob_name}"
                                    g1_label_blob = storage_client.bucket(GCS_BUCKET_NAME).blob(g1_label_blob_name)
                                    g1_label_blob.upload_from_string(generated_label_pdf_bytes, content_type='application/pdf')
                                    try: g1_label_signed_url = g1_label_blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
                                    except Exception as e_sign_g1lbl: print(f"ERROR G1_ONSITE gen signed URL Label: {e_sign_g1lbl}", flush=True)

                                    insert_g1_shipment_sql = text("""INSERT INTO shipments (order_id, purchase_order_id, tracking_number, shipping_method_name, weight_lbs, label_gcs_path, packing_slip_gcs_path, created_at, updated_at) VALUES (:order_id, NULL, :track_num, :method, :weight, :label_path, :ps_path, :now, :now)""")
                                    g1_shipment_params = { "order_id": order_id, "track_num": g1_tracking_number, "method": method_for_label_generation, "weight": float(total_shipment_weight_lbs_str), "label_path": g1_label_blob_name_for_db, "ps_path": g1_ps_blob_name_for_db, "now": current_utc_datetime }
                                    db_conn.execute(insert_g1_shipment_sql, g1_shipment_params)
                            except Exception as label_e_g1: print(f"ERROR G1 Onsite {carrier_from_payload.upper()} Label: {label_e_g1}", flush=True)
                        else:
                            print(f"WARN G1 Onsite: Ship From address (effective) incomplete for label generation. Label not generated. Address used: {current_ship_from_address}", flush=True)

                    if email_service:
                        g1_email_attachments = []
                        if g1_packing_slip_pdf_bytes: g1_email_attachments.append({ "Name": f"PackingSlip_Order_{order_data_for_label['bigcommerce_order_id']}_G1{'_BLIND' if is_blind_drop_ship_from_payload else ''}.pdf", "Content": base64.b64encode(g1_packing_slip_pdf_bytes).decode('utf-8'), "ContentType": "application/pdf" })
                        if generated_label_pdf_bytes: g1_email_attachments.append({ "Name": f"ShippingLabel_Order_{order_data_for_label['bigcommerce_order_id']}_G1_{carrier_from_payload.upper()}.pdf", "Content": base64.b64encode(generated_label_pdf_bytes).decode('utf-8'), "ContentType": "application/pdf" })

                        email_subject_g1_suffix = " (Blind Drop Ship)" if is_blind_drop_ship_from_payload else ""
                        email_subject_g1 = f"G1 Onsite Fulfillment Processed{email_subject_g1_suffix}: Order {order_data_for_label['bigcommerce_order_id']}"
                        email_html_body_g1 = (f"<p>Order {order_data_for_label['bigcommerce_order_id']} has been fulfilled from G1 stock{email_subject_g1_suffix}. Docs attached.</p><p>Tracking: {g1_tracking_number or 'N/A'}</p>")
                        email_text_body_g1 = (f"Order {order_data_for_label['bigcommerce_order_id']} fulfilled{email_subject_g1_suffix}. Docs attached.\nTracking: {g1_tracking_number or 'N/A'}")

                        send_g1_email = False
                        if local_order_line_items_list:
                            if g1_packing_slip_pdf_bytes and generated_label_pdf_bytes:
                                send_g1_email = True
                            # else: # Removed original error raise, now it will print a warning if email not sent
                                # print(f"WARN G1 Onsite Email: Not all documents generated for shipping order {order_data_for_label['bigcommerce_order_id']}. PS: {bool(g1_packing_slip_pdf_bytes)}, Label: {bool(generated_label_pdf_bytes)}. Email not sent.", flush=True)

                        elif g1_packing_slip_pdf_bytes : # No line items, but PS generated (e.g. for a service order)
                            send_g1_email = True
                            email_html_body_g1 = (f"<p>Order {order_data_for_label['bigcommerce_order_id']} processed (G1 Onsite - Packing Slip Only{email_subject_g1_suffix}). Docs attached.</p>")
                            email_text_body_g1 = (f"Order {order_data_for_label['bigcommerce_order_id']} processed (G1 Onsite - Packing Slip Only{email_subject_g1_suffix}). Docs attached.")

                        if send_g1_email and g1_email_attachments:
                            if hasattr(email_service, 'send_sales_notification_email'):
                                email_service.send_sales_notification_email( recipient_email="sales@globalonetechnology.com", subject=email_subject_g1, html_body=email_html_body_g1, text_body=email_text_body_g1, attachments=g1_email_attachments )
                        elif local_order_line_items_list and not send_g1_email:
                             print(f"WARN G1 Onsite Email: Email not sent for order {order_data_for_label['bigcommerce_order_id']} due to missing documents, despite having items.", flush=True)


                bc_order_id_for_update = order_data_for_label.get('bigcommerce_order_id')
                if shipping_service and bc_api_base_url_v2 and bc_order_id_for_update:
                    if g1_tracking_number and local_order_line_items_list:
                        bc_address_id = _get_bc_shipping_address_id(bc_order_id_for_update)
                        bc_items_for_g1_shipment = [{"order_product_id": item_d.get('bigcommerce_line_item_id'), "quantity": item_d.get('quantity')} for item_d in local_order_line_items_list if item_d.get('bigcommerce_line_item_id')]
                        if bc_address_id is not None and bc_items_for_g1_shipment:
                            shipping_service.create_bigcommerce_shipment( bigcommerce_order_id=bc_order_id_for_update, tracking_number=g1_tracking_number, shipping_method_name=method_for_label_generation, line_items_in_shipment=bc_items_for_g1_shipment, order_address_id=bc_address_id, shipping_provider=carrier_from_payload )
                    if bc_shipped_status_id and (g1_tracking_number or not local_order_line_items_list): # Mark as shipped if tracking or no items
                        shipping_service.set_bigcommerce_order_status(bc_order_id_for_update, int(bc_shipped_status_id))
                db_conn.execute(text("UPDATE orders SET status = 'Completed Offline', updated_at = :now WHERE id = :order_id"), {"now": current_utc_datetime, "order_id": order_id})
                processed_pos_info_for_response.append({ "po_number": "N/A (G1 Onsite)", "supplier_id": G1_ONSITE_FULFILLMENT_IDENTIFIER, "tracking_number": g1_tracking_number, "po_pdf_gcs_uri": None, "packing_slip_gcs_uri": g1_ps_signed_url, "label_gcs_uri": g1_label_signed_url, "is_blind_drop_ship": is_blind_drop_ship_from_payload })

            else: # Supplier PO Logic
                if not po_line_items_input:
                    print(f"WARN PROCESS_ORDER: No line items provided for supplier PO to supplier ID {supplier_id_from_payload}. Skipping PO generation for this assignment.", flush=True)
                    processed_pos_info_for_response.append({ "po_number": "N/A (No Items)", "supplier_id": supplier_id_from_payload, "tracking_number": None, "po_pdf_gcs_uri": None, "packing_slip_gcs_uri": None, "label_gcs_uri": None, "status": "Skipped - No Items", "is_blind_drop_ship": is_blind_drop_ship_from_payload})
                    continue

                supplier_record = db_conn.execute(text("SELECT * FROM suppliers WHERE id = :id"), {"id": supplier_id_from_payload}).fetchone()
                if not supplier_record: raise ValueError(f"Supplier with ID {supplier_id_from_payload} not found.")
                supplier_data_dict = convert_row_to_dict(supplier_record)
                if next_sequence_num is None: raise Exception("PO Number sequence not initialized for supplier POs.")
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
                    if not original_line_item_detail: raise ValueError(f"Original line item details for ID {original_oli_id} not found.")
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
                    po_args = {"supplier_data": supplier_data_dict, "po_number": generated_po_number, "po_date": current_utc_datetime, "po_items": po_items_for_pdf, "payment_terms": supplier_data_dict.get('payment_terms'), "payment_instructions": payment_instructions_from_frontend, "order_data": order_data_for_label, "logo_gcs_uri": COMPANY_LOGO_GCS_URI, "is_partial_fulfillment": is_multi_actual_supplier_po_scenario}
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
                    ps_args_supplier = {
                        "order_data": order_data_for_label,
                        "items_in_this_shipment": items_for_packing_slip_this_po_supplier,
                        "items_shipping_separately": items_shipping_separately_supplier,
                        "logo_gcs_uri": effective_logo_gcs_uri,
                        "is_g1_onsite_fulfillment": False,
                        "is_blind_slip": is_blind_drop_ship_from_payload,
                        "custom_ship_from_address": packing_slip_custom_ship_from
                    }
                    ps_pdf_bytes_supplier = document_generator.generate_packing_slip_pdf(**ps_args_supplier)

                label_was_attempted_for_supplier_po = False
                if shipping_service and total_shipment_weight_lbs_str and method_for_label_generation:
                    try:
                        current_weight_supplier = float(total_shipment_weight_lbs_str)
                        if current_weight_supplier > 0 and all([current_ship_from_address.get('street_1'), current_ship_from_address.get('city'), current_ship_from_address.get('state'), current_ship_from_address.get('zip'), current_ship_from_address.get('country'), current_ship_from_address.get('phone')]):
                            label_was_attempted_for_supplier_po = True
                            if carrier_from_payload == 'fedex':
                                label_pdf_bytes_supplier, tracking_this_po = shipping_service.generate_fedex_label(
                                    order_data=order_data_for_label, ship_from_address=current_ship_from_address,
                                    total_weight_lbs=current_weight_supplier, customer_shipping_method_name=method_for_label_generation )
                            else: 
                                label_pdf_bytes_supplier, tracking_this_po = shipping_service.generate_ups_label(
                                    order_data=order_data_for_label, ship_from_address=current_ship_from_address,
                                    total_weight_lbs=current_weight_supplier, customer_shipping_method_name=method_for_label_generation,
                                    is_bill_to_customer_ups_account=is_bill_to_customer_ups_from_payload,
                                    customer_ups_account_number=customer_ups_account_from_payload,
                                    customer_ups_account_zipcode=effective_ups_third_party_zip 
                                )

                            if label_pdf_bytes_supplier and tracking_this_po:
                                insert_ship_sql = text("INSERT INTO shipments (order_id, purchase_order_id, tracking_number, shipping_method_name, weight_lbs, created_at, updated_at) VALUES (:order_id, :po_id, :track, :method, :weight, :now, :now) RETURNING id")
                                ship_params = {"order_id": order_id, "po_id": new_purchase_order_id, "track": tracking_this_po, "method": method_for_label_generation, "weight": current_weight_supplier, "now": current_utc_datetime}
                                db_conn.execute(insert_ship_sql, ship_params)
                        elif current_weight_supplier > 0:
                            print(f"WARN Supplier PO Label: Ship From address (effective) incomplete for label generation. PO: {generated_po_number}. Label not generated. Address used: {current_ship_from_address}", flush=True)
                            label_was_attempted_for_supplier_po = True
                    except Exception as label_e_supplier:
                        print(f"ERROR Supplier PO {carrier_from_payload.upper()} Label: {label_e_supplier}", flush=True)

                if not po_pdf_bytes:
                    raise ValueError(f"PO PDF failed to generate for PO {generated_po_number}. Cannot proceed with this PO.")
                if not ps_pdf_bytes_supplier:
                    raise ValueError(f"Packing Slip PDF failed to generate for PO {generated_po_number}. Cannot proceed with this PO.")
                if label_was_attempted_for_supplier_po and not label_pdf_bytes_supplier:
                    error_detail_label = f"Shipping Label failed to generate for PO {generated_po_number}."
                    if tracking_this_po: error_detail_label += f" Tracking '{tracking_this_po}' might exist, but label PDF is missing."
                    else: error_detail_label += " No tracking number was obtained either."
                    raise ValueError(error_detail_label + " Cannot proceed with this PO.")

                if storage_client and GCS_BUCKET_NAME:
                    ts_suffix = current_utc_datetime.strftime("%Y%m%d%H%M%S")
                    blind_suffix = "_BLIND" if is_blind_drop_ship_from_payload else ""
                    common_prefix_supplier = f"processed_orders/order_{order_data_for_label['bigcommerce_order_id']}_PO_{generated_po_number}{blind_suffix}"
                    bucket = storage_client.bucket(GCS_BUCKET_NAME)
                    gs_po_pdf_path_supplier, gs_ps_path_supplier, gs_label_path_supplier = None, None, None
                    # cloud_run_service_account_email = "992027428168-compute@developer.gserviceaccount.com" # From previous logs; ensure this is correct or remove if not needed for local/default ADC
                    if po_pdf_bytes:
                        po_blob_name = f"{common_prefix_supplier}/po_{generated_po_number}_{ts_suffix}.pdf"
                        gs_po_pdf_path_supplier = f"gs://{GCS_BUCKET_NAME}/{po_blob_name}"
                        po_blob = bucket.blob(po_blob_name); po_blob.upload_from_string(po_pdf_bytes, content_type='application/pdf')
                        db_conn.execute(text("UPDATE purchase_orders SET po_pdf_gcs_path = :path WHERE id = :id"), {"path": gs_po_pdf_path_supplier, "id": new_purchase_order_id})
                        try: po_pdf_signed_url = po_blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET") # Removed service_account_email for ADC
                        except Exception as e_sign_po: print(f"ERROR gen signed URL PO: {e_sign_po}", flush=True)
                    if ps_pdf_bytes_supplier:
                        ps_blob_name = f"{common_prefix_supplier}/ps_{generated_po_number}_{ts_suffix}.pdf"
                        gs_ps_path_supplier = f"gs://{GCS_BUCKET_NAME}/{ps_blob_name}"
                        ps_blob = bucket.blob(ps_blob_name); ps_blob.upload_from_string(ps_pdf_bytes_supplier, content_type='application/pdf')
                        db_conn.execute(text("UPDATE purchase_orders SET packing_slip_gcs_path = :path WHERE id = :id"), {"path": gs_ps_path_supplier, "id": new_purchase_order_id})
                        try: ps_signed_url_supplier = ps_blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
                        except Exception as e_sign_ps: print(f"ERROR gen signed URL PS: {e_sign_ps}", flush=True)
                    if label_pdf_bytes_supplier and tracking_this_po:
                        label_blob_name = f"{common_prefix_supplier}/label_{carrier_from_payload.upper()}_{tracking_this_po}_{ts_suffix}.pdf"
                        gs_label_path_supplier = f"gs://{GCS_BUCKET_NAME}/{label_blob_name}"
                        label_blob = bucket.blob(label_blob_name); label_blob.upload_from_string(label_pdf_bytes_supplier, content_type='application/pdf')
                        db_conn.execute(text("UPDATE shipments SET label_gcs_path = :path WHERE purchase_order_id = :po_id AND tracking_number = :track"), {"path": gs_label_path_supplier, "po_id": new_purchase_order_id, "track": tracking_this_po})
                        try: label_signed_url_supplier = label_blob.generate_signed_url(version="v4", expiration=timedelta(minutes=60), method="GET")
                        except Exception as e_sign_label: print(f"ERROR gen signed URL Label: {e_sign_label}", flush=True)

                attachments_to_supplier = []
                if po_pdf_bytes: attachments_to_supplier.append({"Name": f"PO_{generated_po_number}.pdf", "Content": base64.b64encode(po_pdf_bytes).decode('utf-8'), "ContentType": "application/pdf"})
                if ps_pdf_bytes_supplier: attachments_to_supplier.append({"Name": f"PackingSlip_{generated_po_number}{'_BLIND' if is_blind_drop_ship_from_payload else ''}.pdf", "Content": base64.b64encode(ps_pdf_bytes_supplier).decode('utf-8'), "ContentType": "application/pdf"})
                if label_pdf_bytes_supplier: attachments_to_supplier.append({"Name": f"ShippingLabel_{carrier_from_payload.upper()}_{tracking_this_po}.pdf", "Content": base64.b64encode(label_pdf_bytes_supplier).decode('utf-8'), "ContentType": "application/pdf"})

                min_attachments_required = 3 if label_was_attempted_for_supplier_po else 2

                if email_service and supplier_data_dict.get('email') and len(attachments_to_supplier) >= min_attachments_required:
                    email_service.send_po_email(supplier_email=supplier_data_dict['email'], po_number=generated_po_number, attachments=attachments_to_supplier, is_blind_drop_ship=is_blind_drop_ship_from_payload)
                    db_conn.execute(text("UPDATE purchase_orders SET status = 'SENT_TO_SUPPLIER', updated_at = :now WHERE id = :po_id"), {"po_id": new_purchase_order_id, "now": current_utc_datetime})
                elif email_service and supplier_data_dict.get('email'):
                    raise ValueError(f"PO {generated_po_number}: Email not sent as not all required documents were available (Label attempted: {label_was_attempted_for_supplier_po}, attachments: {len(attachments_to_supplier)}).")

                if shipping_service and bc_api_base_url_v2 and tracking_this_po:
                    bc_order_id_bc_update = order_data_for_label.get('bigcommerce_order_id')
                    bc_address_id_ship = _get_bc_shipping_address_id(bc_order_id_bc_update)
                    bc_items_for_this_ship_api = []
                    for oli_detail in local_order_line_items_list:
                        if oli_detail.get('line_item_id') in ids_in_this_po:
                            po_item_for_bc_qty = next((pi_input for pi_input in po_line_items_input if pi_input.get("original_order_line_item_id") == oli_detail.get('line_item_id')), None)
                            if po_item_for_bc_qty and oli_detail.get('bigcommerce_line_item_id'):
                                bc_items_for_this_ship_api.append({"order_product_id": oli_detail.get('bigcommerce_line_item_id'), "quantity": po_item_for_bc_qty.get('quantity')})
                    if bc_order_id_bc_update and bc_address_id_ship is not None and bc_items_for_this_ship_api:
                        shipping_service.create_bigcommerce_shipment( bigcommerce_order_id=bc_order_id_bc_update, tracking_number=tracking_this_po, shipping_method_name=method_for_label_generation, line_items_in_shipment=bc_items_for_this_ship_api, order_address_id=bc_address_id_ship, shipping_provider=carrier_from_payload )

                processed_pos_info_for_response.append({ "po_number": generated_po_number, "supplier_id": supplier_id_from_payload, "tracking_number": tracking_this_po, "po_pdf_gcs_uri": po_pdf_signed_url, "packing_slip_gcs_uri": ps_signed_url_supplier, "label_gcs_uri": label_signed_url_supplier, "status": "Processed", "is_blind_drop_ship": is_blind_drop_ship_from_payload })

        is_only_g1_onsite_processed = all(a.get('supplier_id') == G1_ONSITE_FULFILLMENT_IDENTIFIER for a in assignments)
        if is_only_g1_onsite_processed:
            # If only G1 Onsite, status already set to Completed Offline
            pass
        else: # One or more supplier POs were generated
            db_conn.execute(text("UPDATE orders SET status = 'Processed', updated_at = :now WHERE id = :order_id"), {"now": current_utc_datetime, "order_id": order_id})
            
            # Only update BC to "Shipped" if all original items were part of generated supplier POs (not G1)
            # AND at least one of those POs generated a tracking number.
            if all_original_order_line_item_db_ids.issubset(processed_original_order_line_item_db_ids_this_batch):
                if shipping_service and bc_api_base_url_v2 and bc_shipped_status_id and order_data_dict_original.get('bigcommerce_order_id'):
                    any_supplier_po_with_tracking = any(
                        po_info.get('tracking_number') 
                        for po_info in processed_pos_info_for_response 
                        if po_info.get("supplier_id") != G1_ONSITE_FULFILLMENT_IDENTIFIER and po_info.get("status") == "Processed"
                    )
                    if any_supplier_po_with_tracking:
                        shipping_service.set_bigcommerce_order_status( 
                            bigcommerce_order_id=order_data_dict_original.get('bigcommerce_order_id'), 
                            status_id=int(bc_shipped_status_id) 
                        )
                    else:
                        print(f"INFO PROCESS_ORDER: Order {order_id} fully processed for app, but no supplier tracking numbers from *processed* POs. BC status NOT set to Shipped.", flush=True)
            else:
                 print(f"INFO PROCESS_ORDER: Order {order_id} processed for app, but not all original line items were part of this batch of supplier POs. BC status NOT set to Shipped by this operation.", flush=True)


        transaction.commit()
        final_message = f"Order {order_id} processed successfully."
        return jsonify({ "message": final_message, "order_id": order_id, "processed_purchase_orders": make_json_safe(processed_pos_info_for_response) }), 201

    except ValueError as ve:
        if transaction and transaction.is_active: transaction.rollback()
        print(f"ERROR PROCESS_ORDER (ValueError): {ve}", flush=True); traceback.print_exc(file=sys.stderr); sys.stderr.flush()
        return jsonify({"error": "Processing failed due to invalid data or missing document.", "details": str(ve)}), 400
    except Exception as e:
        if transaction and transaction.is_active:
             try: transaction.rollback()
             except Exception as rb_e: print(f"ERROR PROCESS_ORDER: Error during transaction rollback: {rb_e}", flush=True)
        print(f"ERROR PROCESS_ORDER (Exception): Unhandled Exception: {e}", flush=True); traceback.print_exc(file=sys.stderr); sys.stderr.flush()
        return jsonify({"error": "An unexpected error occurred during order processing.", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print(f"DEBUG PROCESS_ORDER: DB Connection closed for order {order_id}", flush=True)