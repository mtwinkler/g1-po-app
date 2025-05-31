# order-processing-app/blueprints/international.py

from flask import Blueprint, jsonify, current_app, request, g
from sqlalchemy.sql import text
from datetime import datetime, timezone
import logging
import base64
from decimal import Decimal
import json
import os

from app import (
    verify_firebase_token,
    engine,
    SHIPPER_EIN,
    COMPANY_LOGO_GCS_URI,
    GCS_BUCKET_NAME,
    get_country_name_from_iso,
    get_hpe_mapping_with_fallback,
    _get_bc_shipping_address_id,
    bc_api_base_url_v2,
    bc_shipped_status_id
)
import shipping_service
import gcs_service
from document_generator import generate_purchase_order_pdf, generate_packing_slip_pdf
import email_service

international_bp = Blueprint('international_bp', __name__)

# --- get_international_details function (remains the same from last correct version) ---
@international_bp.route("/order/<int:order_id>/international-details", methods=['GET'])
@verify_firebase_token
def get_international_details(order_id):
    user_token_info = g.decoded_token
    logging.debug(f"INTERN_DETAILS: Request for order {order_id} by user {user_token_info.get('uid', 'Unknown') if user_token_info else 'Unauthenticated'}")
    if engine is None:
        current_app.logger.error("Database engine not available.")
        return jsonify({"error": "Database engine not available."}), 500

    with engine.connect() as conn:
        try:
            order_query_text = """
                SELECT
                    o.id, o.bigcommerce_order_id, o.order_date,
                    o.customer_name, o.customer_company,
                    o.customer_shipping_address_line1, o.customer_shipping_address_line2,
                    o.customer_shipping_city, o.customer_shipping_state,
                    o.customer_shipping_zip, o.customer_shipping_country, o.customer_shipping_country_iso2,
                    o.customer_phone, o.customer_shipping_method, o.payment_method, o.customer_notes,
                    o.is_bill_to_customer_account, o.customer_ups_account_number, o.customer_ups_account_zipcode, -- Added for UPS 3rd party
                    o.is_bill_to_customer_fedex_account, o.customer_fedex_account_number -- For FedEx 3rd party
                FROM orders o
                WHERE o.id = :order_id
            """
            order_query = text(order_query_text)
            order_result = conn.execute(order_query, {"order_id": order_id}).fetchone()

            if not order_result:
                return jsonify({"error": "Order not found"}), 404

            order_details_for_docs_and_customs = dict(order_result._mapping)

            customer_shipping_country_iso2 = order_result.customer_shipping_country_iso2
            logging.debug(f"INTERN_DETAILS: Order {order_id}, Country ISO: {customer_shipping_country_iso2}")

            target_country_name = get_country_name_from_iso(customer_shipping_country_iso2)
            logging.debug(f"INTERN_DETAILS: Order {order_id}, Target Country Name for query: {target_country_name}")

            compliance_fields_query = text("""
                SELECT field_label, id_owner, is_required, has_exempt_option
                FROM country_compliance_fields
                WHERE country_name = :country_name_param OR country_name = '*'
            """)
            compliance_results = conn.execute(compliance_fields_query, {"country_name_param": target_country_name}).fetchall()
            required_compliance_fields = [dict(row._mapping) for row in compliance_results]
            logging.debug(f"INTERN_DETAILS: Found {len(required_compliance_fields)} compliance fields for '{target_country_name}' (and *).")

            line_items_query = text("""
                SELECT id AS original_order_line_item_id, sku, quantity, name AS product_name, sale_price
                FROM order_line_items WHERE order_id = :order_id
            """)
            line_items_results = conn.execute(line_items_query, {"order_id": order_id}).fetchall()
            logging.debug(f"DEBUG INTERN_DETAILS: Found {len(line_items_results)} line items for order {order_id}.")

            line_items_customs_info = []
            if line_items_results:
                for item_row_mapping in line_items_results:
                    item = dict(item_row_mapping._mapping)
                    original_sku = item['sku']
                    customs_data = {
                        "original_order_line_item_id": item['original_order_line_item_id'],
                        "sku": original_sku,
                        "product_name": item.get('product_name', 'N/A'),
                        "name": item.get('product_name', 'N/A'),
                        "quantity": item['quantity'],
                        "sale_price": item.get('sale_price'),
                        "option_pn_used_for_lookup": None,
                        "product_type_used_for_lookup": None,
                        "customs_description": f"N/A - Mapping/Customs data lookup failed for SKU: {original_sku}",
                        "harmonized_tariff_code": "N/A",
                        "default_country_of_origin": "US"
                    }
                    hpe_option_pn, _, _ = get_hpe_mapping_with_fallback(original_sku, conn)
                    customs_data["option_pn_used_for_lookup"] = hpe_option_pn
                    if hpe_option_pn:
                        pt_query = text("SELECT product_type FROM product_types WHERE option_pn = :option_pn LIMIT 1")
                        pt_result = conn.execute(pt_query, {"option_pn": hpe_option_pn}).fetchone()
                        if pt_result:
                            product_type_val = pt_result.product_type
                            customs_data["product_type_used_for_lookup"] = product_type_val
                            ci_query = text("""
                                SELECT customs_description, harmonized_tariff_code, default_country_of_origin
                                FROM customs_info WHERE LOWER(product_type) = LOWER(:product_type) LIMIT 1
                            """)
                            ci_result = conn.execute(ci_query, {"product_type": product_type_val}).fetchone()
                            if ci_result:
                                customs_data["customs_description"] = ci_result.customs_description
                                customs_data["harmonized_tariff_code"] = ci_result.harmonized_tariff_code
                                customs_data["default_country_of_origin"] = ci_result.default_country_of_origin
                    line_items_customs_info.append(customs_data)

            response_data = {
                "order_id": order_id,
                "customer_shipping_country_iso2": customer_shipping_country_iso2,
                "country_name": target_country_name,
                "line_items_customs_info": line_items_customs_info,
                "required_compliance_fields": required_compliance_fields,
                "shipper_ein": SHIPPER_EIN,
                "order_details_for_po": order_details_for_docs_and_customs
            }
            logging.debug(f"DEBUG INTERN_DETAILS: Successfully prepared data for order {order_id}")
            return jsonify(response_data), 200
        except Exception as e:
            current_app.logger.error(f"Error in get_international_details for order {order_id}: {e}", exc_info=True)
            return jsonify({"error": "An internal error occurred while fetching international details.", "details": str(e)}), 500

# --- generate_international_shipment_route function (remains the same from your last correct version) ---
@international_bp.route('/order/<int:order_id>/generate-international-shipment', methods=['POST'])
@verify_firebase_token
def generate_international_shipment_route(order_id):
    user_token_info = g.decoded_token
    logging.info(f"INFO INTL_SHIP_ROUTE: Request for order {order_id} by user {user_token_info.get('uid', 'Unknown') if user_token_info else 'Unauthenticated'}")
    if not shipping_service or not gcs_service:
        current_app.logger.error("Shipping or GCS service not initialized.")
        return jsonify({"message": "Server configuration error"}), 503
    shipment_payload_from_frontend = request.get_json()
    if not shipment_payload_from_frontend:
        return jsonify({"message": "Request body is missing or not valid JSON"}), 400

    with engine.connect() as conn:
        with conn.begin() as transaction:
            try:
                order_query = text("SELECT id, bigcommerce_order_id FROM orders WHERE id = :order_id")
                order_data_result = conn.execute(order_query, {"order_id": order_id}).fetchone()

                if not order_data_result:
                    current_app.logger.error(f"Order {order_id} not found during shipment generation attempt.")
                    return jsonify({"message": "Order not found"}), 404

                order_details = dict(order_data_result._mapping)
                bigcommerce_order_id_for_filename = order_details.get('bigcommerce_order_id') or order_id

                logging.info(f"INFO INTL_SHIP_ROUTE: Calling generate_ups_international_shipment for order {order_id}")
                label_pdf_bytes, tracking_number = shipping_service.generate_ups_international_shipment(shipment_payload_from_frontend)

                if not label_pdf_bytes or not tracking_number:
                    raise Exception("Shipment generation failed. Carrier might have rejected request or no label PDF returned. See server logs.")

                label_url = None
                logging.debug(f"DEBUG INTL_SHIP_ROUTE: Label PDF bytes received (length: {len(label_pdf_bytes)}).")
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                filename = f"shipping_labels/order_{bigcommerce_order_id_for_filename}/UPS_INTL_{tracking_number}_{timestamp}.pdf"
                logging.info(f"INFO INTL_SHIP_ROUTE: Uploading PDF label to GCS: {filename}")
                label_url = gcs_service.upload_file_bytes(
                    file_bytes=label_pdf_bytes,
                    destination_blob_name=filename,
                    content_type='application/pdf'
                )
                logging.info(f"INFO INTL_SHIP_ROUTE: Successfully uploaded label for {tracking_number} to {label_url}")

                logging.info(f"INFO INTL_SHIP_ROUTE: Saving shipment record for tracking {tracking_number} to database.")
                shipment_insert_query = text("""
                    INSERT INTO shipments (order_id, carrier, tracking_number, label_gcs_url, created_at, service_used)
                    VALUES (:order_id, :carrier, :tracking_number, :label_gcs_url, :created_at, :service_used)
                """)
                service_code_used = shipment_payload_from_frontend.get('ShipmentRequest', {}).get('Shipment', {}).get('Service', {}).get('Code', 'N/A')

                conn.execute(shipment_insert_query, {
                    "order_id": order_id, "carrier": 'UPS', "tracking_number": tracking_number,
                    "label_gcs_url": label_url, "created_at": datetime.now(timezone.utc),
                    "service_used": service_code_used
                })
                logging.info(f"INFO INTL_SHIP_ROUTE: Updating order {order_id} status to 'Processed'.")
                order_update_query = text("UPDATE orders SET status = :status WHERE id = :order_id")
                conn.execute(order_update_query, {"status": 'Processed', "order_id": order_id})

                transaction.commit() # Commit if all successful

                return jsonify({
                    "message": "International shipment generated successfully.",
                    "trackingNumber": tracking_number, "labelUrl": label_url
                }), 200

            except Exception as e:
                # transaction will be rolled back by the 'with conn.begin()' context manager on exception
                current_app.logger.error(f"Error in generate_international_shipment_route for order {order_id}: {e}", exc_info=True)
                return jsonify({"message": f"An error occurred: {str(e)}"}), 500


@international_bp.route('/order/<int:order_id>/process-international-dropship', methods=['POST'])
@verify_firebase_token
def process_international_dropship_route(order_id):
    user_token_info = g.decoded_token
    logging.info(f"INFO INTL_DROPSHIP_ROUTE: Request for order {order_id} by user {user_token_info.get('uid', 'Unknown') if user_token_info else 'Unauthenticated'}")

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    po_data = data.get('po_data') # If null/empty, it's G1 Onsite International
    shipment_data = data.get('shipment_data') # This is always expected for label

    if not shipment_data:
        return jsonify({"error": "Shipment data (for label) is required"}), 400

    # Initialize variables that might be used in either flow
    generated_po_number = None
    po_pdf_http_url = None
    packing_slip_http_url = None # Can be for PO's PS or G1's PS
    gcs_label_http_url = None # For the shipping label
    tracking_number = None

    # Document bytes for email
    po_pdf_bytes_for_email = None
    packing_slip_pdf_bytes_for_email = None
    label_pdf_bytes_for_email = None # This will be from shipment_data processing

    is_blind_drop_ship_flag = po_data.get('is_blind_drop_ship', False) if po_data else shipment_data.get('is_blind_drop_ship', False) # Get from shipment_data if no po_data

    try:
        with engine.connect() as db_connection:
            with db_connection.begin() as transaction:
                # Fetch general order details first
                order_info_query_text = """
                    SELECT
                        o.id, o.bigcommerce_order_id, o.order_date,
                        o.customer_name, o.customer_company,
                        o.customer_shipping_address_line1, o.customer_shipping_address_line2,
                        o.customer_shipping_city, o.customer_shipping_state, o.customer_shipping_zip,
                        o.customer_shipping_country, o.customer_shipping_country_iso2,
                        o.customer_phone, o.customer_shipping_method, o.payment_method, o.customer_notes,
                        o.is_bill_to_customer_account, o.customer_ups_account_number, o.customer_ups_account_zipcode,
                        o.is_bill_to_customer_fedex_account, o.customer_fedex_account_number,
                        o.customer_billing_first_name, o.customer_billing_last_name, o.customer_billing_company,
                        o.customer_billing_street_1, o.customer_billing_street_2, o.customer_billing_city,
                        o.customer_billing_state, o.customer_billing_zip, o.customer_billing_country,
                        o.customer_billing_country_iso2, o.customer_billing_phone
                    FROM orders o WHERE id = :order_id
                """
                order_info_for_docs_result = db_connection.execute(text(order_info_query_text), {"order_id": order_id}).fetchone()

                if not order_info_for_docs_result:
                    raise ValueError(f"Order details not found for order ID {order_id} for document generation.")
                order_data_for_docs = dict(order_info_for_docs_result._mapping)
                bc_order_id_for_paths = order_data_for_docs.get('bigcommerce_order_id')
                current_utc_datetime = datetime.now(timezone.utc) # For timestamps

                # --- Generate Shipping Label (Common for both PO and G1 Onsite International) ---
                label_pdf_bytes, tn_from_ship_service = shipping_service.generate_ups_international_shipment(shipment_data)
                if not label_pdf_bytes or not tn_from_ship_service:
                    raise Exception("Failed to get label PDF from UPS.")
                tracking_number = tn_from_ship_service # Assign to broader scope
                label_pdf_bytes_for_email = label_pdf_bytes
                logging.info(f"INTL_DROPSHIP_ROUTE: UPS Label Success! Tracking: {tracking_number}.")

                label_timestamp = current_utc_datetime.strftime("%Y%m%d%H%M%S")
                label_gcs_folder = f"shipping_labels/order_{bc_order_id_for_paths}"
                label_gcs_filename_part = f"{label_gcs_folder}/UPS_INTL_DS_{tracking_number}_{label_timestamp}.pdf"
                gcs_label_http_url = gcs_service.upload_file_bytes(label_pdf_bytes, label_gcs_filename_part, "application/pdf")
                if not gcs_label_http_url:
                    raise Exception("Failed to upload shipping label PDF to GCS.")
                logging.info(f"INTL_DROPSHIP_ROUTE: Successfully uploaded shipping label PDF to {gcs_label_http_url}")
                # Shipment DB record will be inserted after PO/G1 Onsite logic

                # Initialize common GCS folder prefix parts
                gcs_common_prefix_main_part = f"processed_orders/order_{bc_order_id_for_paths}"
                gcs_blind_suffix = "_BLIND" if is_blind_drop_ship_flag else ""
                gcs_timestamp_suffix = current_utc_datetime.strftime("%Y%m%d%H%M%S")


                if po_data: # --- Logic for Drop-Ship PO to Supplier ---
                    logging.info(f"INTL_DROPSHIP_ROUTE: Processing as Drop-Ship PO for order {order_id}.")
                    new_po_id = None # Specific to this block
                    supplier_id = po_data.get('supplierId')
                    po_notes = po_data.get('poNotes')
                    line_items_from_frontend = po_data.get('lineItems')

                    if not supplier_id or not line_items_from_frontend:
                        raise ValueError("Supplier ID and line items are required for PO.")

                    # PO Number Generation
                    starting_po_sequence = 200001
                    max_po_query = text("SELECT MAX(CAST(numeric_po_number AS INTEGER)) FROM (SELECT po_number AS numeric_po_number FROM purchase_orders WHERE CAST(po_number AS TEXT) ~ '^[0-9]+$') AS numeric_pos")
                    max_po_value_from_db = db_connection.execute(max_po_query).scalar_one_or_none()
                    next_sequence_num = starting_po_sequence
                    if max_po_value_from_db is not None:
                        try: next_sequence_num = max(starting_po_sequence, int(max_po_value_from_db) + 1)
                        except ValueError: logging.warning(f"Could not parse max PO number '{max_po_value_from_db}'.")
                    generated_po_number = str(next_sequence_num)

                    total_po_amount = sum(Decimal(str(item.get('quantity', 0))) * Decimal(str(item.get('unitCost', '0'))) for item in line_items_from_frontend)
                    po_insert_query = text("INSERT INTO purchase_orders (po_number, order_id, supplier_id, payment_instructions, status, created_by, po_date, total_amount) VALUES (:po_number, :order_id, :supplier_id, :payment_instructions, :status, :created_by, :po_date, :total_amount) RETURNING id;")
                    po_result = db_connection.execute(po_insert_query, {"po_number": generated_po_number, "order_id": order_id, "supplier_id": supplier_id, "payment_instructions": po_notes, "status": "New", "created_by": g.decoded_token['email'], "po_date": current_utc_datetime, "total_amount": total_po_amount}).fetchone()
                    if not po_result or not po_result.id: raise ValueError("Failed to create PO or retrieve PO ID.")
                    new_po_id = po_result.id

                    po_line_items_for_db_and_pdf = []
                    bc_line_items_for_shipment_api = [] # For this PO
                    for item_fe in line_items_from_frontend:
                        po_line_items_for_db_and_pdf.append({"sku": item_fe.get('sku'), "description": item_fe.get('description'), "name": item_fe.get('description'), "quantity": item_fe.get('quantity'), "unit_cost": item_fe.get('unitCost'), "unitCost": item_fe.get('unitCost'), "original_order_line_item_id": item_fe.get("original_order_line_item_id") })
                        if item_fe.get("original_order_line_item_id"):
                            oli_query = text("SELECT bigcommerce_line_item_id FROM order_line_items WHERE id = :id AND order_id = :order_id_param")
                            oli_result = db_connection.execute(oli_query, {"id": item_fe.get("original_order_line_item_id"), "order_id_param": order_id}).fetchone()
                            if oli_result and oli_result.bigcommerce_line_item_id:
                                bc_line_items_for_shipment_api.append({"order_product_id": oli_result.bigcommerce_line_item_id, "quantity": item_fe.get('quantity')})
                            else: logging.warning(f"Could not find bigcommerce_line_item_id for OLI ID {item_fe.get('original_order_line_item_id')} in PO {generated_po_number}")

                    for item_db_info in po_line_items_for_db_and_pdf:
                        line_item_query = text("INSERT INTO po_line_items (purchase_order_id, sku, description, quantity, unit_cost, original_order_line_item_id) VALUES (:po_id, :sku, :desc, :qty, :cost, :original_id);")
                        db_connection.execute(line_item_query, {"po_id": new_po_id, "sku": item_db_info.get('sku'), "desc": item_db_info.get('description'), "qty": item_db_info.get('quantity'), "cost": item_db_info.get('unitCost'), "original_id": item_db_info.get("original_order_line_item_id") })

                    supplier_info_for_pdf_row = db_connection.execute(text("SELECT * FROM suppliers WHERE id = :supplier_id"), {"supplier_id": supplier_id}).fetchone()
                    if not supplier_info_for_pdf_row: raise ValueError(f"Supplier details not found for ID {supplier_id}.")
                    supplier_data_for_pdf = dict(supplier_info_for_pdf_row._mapping)

                    # PO PDF
                    items_for_po_pdf_generator = [{'unit_cost': item['unitCost'], **item} for item in po_line_items_for_db_and_pdf]
                    po_pdf_data_args = {"order_data": order_data_for_docs, "supplier_data": supplier_data_for_pdf, "po_number": generated_po_number, "po_date": current_utc_datetime, "po_items": items_for_po_pdf_generator, "payment_terms": supplier_data_for_pdf.get('payment_terms'), "payment_instructions": po_notes, "logo_gcs_uri": COMPANY_LOGO_GCS_URI, "is_partial_fulfillment": False } # Assuming not partial for international single PO
                    po_pdf_bytes_for_email = generate_purchase_order_pdf(**po_pdf_data_args)

                    # Packing Slip for PO
                    packing_slip_items_for_po_ps_gen = []
                    original_bc_item_name_query_po = text("SELECT name FROM order_line_items WHERE id = :original_line_item_id")
                    hpe_po_desc_query_po = text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn_param LIMIT 1")
                    for po_item_detail in po_line_items_for_db_and_pdf:
                        ps_sku = po_item_detail.get("sku")
                        ps_desc = None
                        original_oli_id = po_item_detail.get("original_order_line_item_id")
                        hpe_mapped_desc = db_connection.execute(hpe_po_desc_query_po, {"option_pn_param": ps_sku}).scalar_one_or_none()
                        if hpe_mapped_desc: ps_desc = hpe_mapped_desc
                        elif original_oli_id:
                            original_bc_name = db_connection.execute(original_bc_item_name_query_po, {"original_line_item_id": original_oli_id}).scalar_one_or_none()
                            if original_bc_name: ps_desc = original_bc_name
                        if not ps_desc: ps_desc = po_item_detail.get("description", "Item Description Unavailable")
                        packing_slip_items_for_po_ps_gen.append({"name": ps_desc, "quantity": po_item_detail.get("quantity"), "sku": ps_sku})

                    packing_slip_pdf_bytes_for_email = generate_packing_slip_pdf(order_data=order_data_for_docs, items_in_this_shipment=packing_slip_items_for_po_ps_gen, items_shipping_separately=[], logo_gcs_uri=COMPANY_LOGO_GCS_URI, is_g1_onsite_fulfillment=False, is_blind_slip=is_blind_drop_ship_flag, custom_ship_from_address=None)

                    # GCS Uploads for PO flow
                    common_gcs_folder_for_po = f"{gcs_common_prefix_main_part}_PO_{generated_po_number}{gcs_blind_suffix}"
                    po_pdf_gcs_path_part = f"{common_gcs_folder_for_po}/po_{generated_po_number}_{gcs_timestamp_suffix}.pdf"
                    po_pdf_gs_uri_db = f"gs://{GCS_BUCKET_NAME}/{po_pdf_gcs_path_part}"
                    po_pdf_http_url = gcs_service.upload_file_bytes(po_pdf_bytes_for_email, po_pdf_gcs_path_part, "application/pdf")
                    if po_pdf_http_url: db_connection.execute(text("UPDATE purchase_orders SET po_pdf_gcs_path = :path WHERE id = :id"), {"path": po_pdf_gs_uri_db, "id": new_po_id})

                    if packing_slip_pdf_bytes_for_email:
                        ps_pdf_gcs_path_part_po = f"{common_gcs_folder_for_po}/ps_{generated_po_number}_{gcs_timestamp_suffix}.pdf"
                        ps_pdf_gs_uri_db_po = f"gs://{GCS_BUCKET_NAME}/{ps_pdf_gcs_path_part_po}"
                        packing_slip_http_url = gcs_service.upload_file_bytes(packing_slip_pdf_bytes_for_email, ps_pdf_gcs_path_part_po, "application/pdf")
                        if packing_slip_http_url: db_connection.execute(text("UPDATE purchase_orders SET packing_slip_gcs_path = :path WHERE id = :id"), {"path": ps_pdf_gs_uri_db_po, "id": new_po_id})

                    # Insert shipment record for this PO's label
                    shipment_insert_query = text("INSERT INTO shipments (order_id, carrier, tracking_number, label_gcs_url, created_at, service_used, purchase_order_id, packing_slip_gcs_path) VALUES (:order_id, :carrier, :tracking, :label_url, :created_at, :service, :po_id, NULL)") # packing_slip_gcs_path refers to G1 generated for now.
                    db_connection.execute(shipment_insert_query, {"order_id": order_id, "carrier": "UPS", "tracking": tracking_number, "label_url": gcs_label_http_url, "created_at": current_utc_datetime, "service": shipment_data.get('ShipmentRequest', {}).get('Shipment', {}).get('Service', {}).get('Code'), "po_id": new_po_id})

                    # Email to Supplier
                    if supplier_info_for_pdf_row.email:
                        attachments = []
                        if po_pdf_bytes_for_email: attachments.append({"Name": f"PO_{generated_po_number}.pdf", "Content": base64.b64encode(po_pdf_bytes_for_email).decode('utf-8'), "ContentType": "application/pdf"})
                        if label_pdf_bytes_for_email: attachments.append({"Name": f"ShippingLabel_{tracking_number}.pdf", "Content": base64.b64encode(label_pdf_bytes_for_email).decode('utf-8'), "ContentType": "application/pdf"})
                        if packing_slip_pdf_bytes_for_email: attachments.append({"Name": f"PackingSlip_PO_{generated_po_number}.pdf", "Content": base64.b64encode(packing_slip_pdf_bytes_for_email).decode('utf-8'), "ContentType": "application/pdf"})
                        if attachments:
                            email_sent = email_service.send_po_email(supplier_email=supplier_info_for_pdf_row.email, po_number=generated_po_number, attachments=attachments, is_blind_drop_ship=is_blind_drop_ship_flag)
                            if email_sent: db_connection.execute(text("UPDATE purchase_orders SET status = 'SENT_TO_SUPPLIER' WHERE id = :po_id"), {"po_id": new_po_id})
                            else: logging.error(f"Failed to send email to supplier {supplier_info_for_pdf_row.email}")
                    else: logging.warning(f"No email for supplier ID {supplier_id}")

                else: # --- Logic for G1 Onsite International Fulfillment ---
                    logging.info(f"INTL_DROPSHIP_ROUTE: Processing as G1 Onsite International Fulfillment for order {order_id}.")
                    new_po_id = None # No PO for G1 Onsite
                    ps_gs_uri_db_g1 = None # Initialize for G1 onsite case

                    # Fetch all original line items for the order for PS and BC Shipment
                    all_order_line_items_query = text("SELECT id AS line_item_id, sku, name, quantity, bigcommerce_line_item_id FROM order_line_items WHERE order_id = :order_id_param")
                    all_order_line_items_results = db_connection.execute(all_order_line_items_query, {"order_id_param": order_id}).fetchall()

                    items_for_g1_packing_slip = []
                    bc_line_items_for_shipment_api = [] # For G1 shipment

                    if all_order_line_items_results:
                        hpe_po_desc_query_g1 = text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn_param LIMIT 1")
                        for item_row in all_order_line_items_results:
                            item = dict(item_row._mapping)
                            ps_sku = item.get('sku')
                            ps_desc = item.get('name')
                            # Apply HPE mapping for PS description if applicable
                            mapped_sku_for_hpe_lookup, _, _ = get_hpe_mapping_with_fallback(ps_sku, db_connection) # get_hpe_mapping_with_fallback needs connection
                            if mapped_sku_for_hpe_lookup: # If original SKU maps to an Option PN
                                hpe_desc = db_connection.execute(hpe_po_desc_query_g1, {"option_pn_param": mapped_sku_for_hpe_lookup}).scalar_one_or_none()
                                if hpe_desc: ps_desc = hpe_desc
                                ps_sku = mapped_sku_for_hpe_lookup # Use Option PN as SKU on PS

                            items_for_g1_packing_slip.append({'sku': ps_sku, 'name': ps_desc, 'quantity': item.get('quantity')})
                            if item.get('bigcommerce_line_item_id'):
                                bc_line_items_for_shipment_api.append({'order_product_id': item.get('bigcommerce_line_item_id'), 'quantity': item.get('quantity')})

                        packing_slip_pdf_bytes_for_email = generate_packing_slip_pdf(order_data=order_data_for_docs, items_in_this_shipment=items_for_g1_packing_slip, items_shipping_separately=[], logo_gcs_uri=COMPANY_LOGO_GCS_URI, is_g1_onsite_fulfillment=True, is_blind_slip=is_blind_drop_ship_flag, custom_ship_from_address=None)

                        if packing_slip_pdf_bytes_for_email:
                            ps_gcs_folder_g1 = f"{gcs_common_prefix_main_part}_G1OnsiteIntl{gcs_blind_suffix}"
                            ps_gcs_filename_part_g1 = f"{ps_gcs_folder_g1}/ps_g1intl_{gcs_timestamp_suffix}.pdf"
                            ps_gs_uri_db_g1 = f"gs://{GCS_BUCKET_NAME}/{ps_gcs_filename_part_g1}"
                            packing_slip_http_url = gcs_service.upload_file_bytes(packing_slip_pdf_bytes_for_email, ps_gcs_filename_part_g1, "application/pdf")
                        else:
                            logging.warning(f"INTL_DROPSHIP_ROUTE: G1 Onsite - Failed to generate packing slip for order {order_id}")
                    else:
                        logging.info(f"INTL_DROPSHIP_ROUTE: G1 Onsite - No line items on order {order_id} to generate packing slip for.")

                    # Insert shipment record for G1 Onsite International
                    shipment_insert_query_g1 = text("INSERT INTO shipments (order_id, carrier, tracking_number, label_gcs_url, created_at, service_used, purchase_order_id, packing_slip_gcs_path) VALUES (:order_id, :carrier, :tracking, :label_url, :created_at, :service, NULL, :ps_path)")
                    db_connection.execute(shipment_insert_query_g1, {"order_id": order_id, "carrier": "UPS", "tracking": tracking_number, "label_url": gcs_label_http_url, "created_at": current_utc_datetime, "service": shipment_data.get('ShipmentRequest', {}).get('Shipment', {}).get('Service', {}).get('Code'), "ps_path": ps_gs_uri_db_g1 })

                    # Internal Sales Email Notification
                    g1_intl_email_attachments = []
                    if packing_slip_pdf_bytes_for_email: g1_intl_email_attachments.append({"Name": f"PackingSlip_G1Intl_Order_{bc_order_id_for_paths}{gcs_blind_suffix}.pdf", "Content": base64.b64encode(packing_slip_pdf_bytes_for_email).decode('utf-8'), "ContentType": "application/pdf"})
                    if label_pdf_bytes_for_email: g1_intl_email_attachments.append({"Name": f"ShippingLabel_UPS_INTL_{tracking_number}.pdf", "Content": base64.b64encode(label_pdf_bytes_for_email).decode('utf-8'), "ContentType": "application/pdf"})

                    if g1_intl_email_attachments:
                        sales_email_subject = f"G1 Intl Fulfillment Processed{gcs_blind_suffix}: Order {bc_order_id_for_paths}"
                        sales_email_html_body = f"<p>International Order {bc_order_id_for_paths} has been fulfilled from G1 stock{gcs_blind_suffix}. Docs attached.</p><p>Tracking: {tracking_number}</p>"
                        sales_email_text_body = f"International Order {bc_order_id_for_paths} fulfilled{gcs_blind_suffix}. Docs attached.\nTracking: {tracking_number}"

                        sales_recipient = os.getenv("SALES_EMAIL_RECIPIENT", "sales@globalonetechnology.com")
                        email_service.send_sales_notification_email(
                            recipient_email=sales_recipient,
                            subject=sales_email_subject,
                            html_body=sales_email_html_body,
                            text_body=sales_email_text_body,
                            attachments=g1_intl_email_attachments
                        )
                    else:
                        logging.warning(f"INTL_DROPSHIP_ROUTE: G1 Onsite - No documents to attach for sales notification email for order {order_id}.")

                # Common for both flows (PO and G1 Onsite) after this point:
                logging.info(f"INTL_DROPSHIP_ROUTE: Updating local order {order_id} status to 'Processed'.")
                db_connection.execute(text("UPDATE orders SET status = 'Processed', updated_at = :now WHERE id = :order_id"), {"now": current_utc_datetime, "order_id": order_id})

                if bc_order_id_for_paths and tracking_number:
                    bc_address_id = _get_bc_shipping_address_id(bc_order_id_for_paths)
                    if bc_address_id is not None and bc_line_items_for_shipment_api:
                        logging.info(f"INTL_DROPSHIP_ROUTE: Attempting to create BigCommerce shipment for BC Order ID {bc_order_id_for_paths} with {len(bc_line_items_for_shipment_api)} item groups.")
                        bc_shipping_method_name = shipment_data.get('ShipmentRequest', {}).get('Shipment', {}).get('Service', {}).get('Description', 'UPS International') # Try to get service description
                        shipping_service.create_bigcommerce_shipment(bigcommerce_order_id=bc_order_id_for_paths, tracking_number=tracking_number, shipping_method_name=bc_shipping_method_name, line_items_in_shipment=bc_line_items_for_shipment_api, order_address_id=bc_address_id, shipping_provider="ups")
                    else:
                        logging.warning(f"INTL_DROPSHIP_ROUTE: Skipping BigCommerce shipment creation for BC Order {bc_order_id_for_paths}. Missing address ID ({bc_address_id}) or shipment items ({len(bc_line_items_for_shipment_api)}).")

                    if bc_shipped_status_id and bc_api_base_url_v2:
                        logging.info(f"INTL_DROPSHIP_ROUTE: Attempting to update BigCommerce order status to Shipped for BC Order ID {bc_order_id_for_paths}.")
                        shipping_service.set_bigcommerce_order_status(bigcommerce_order_id=bc_order_id_for_paths, status_id=int(bc_shipped_status_id))
                    else:
                        logging.warning(f"INTL_DROPSHIP_ROUTE: Skipping BigCommerce status update for BC Order {bc_order_id_for_paths}. BC_SHIPPED_STATUS_ID or BC_API_BASE_URL_V2 not configured.")

                transaction.commit()

        return jsonify({
            "message": "International shipment processed successfully.", "trackingNumber": tracking_number,
            "labelUrl": gcs_label_http_url, "poNumber": generated_po_number,
            "poPdfUrl": po_pdf_http_url, "packingSlipPdfUrl": packing_slip_http_url
        }), 200

    except Exception as e:
        if 'transaction' in locals() and transaction is not None and transaction.is_active :
            try: transaction.rollback(); logging.info("Transaction rolled back due to exception.")
            except Exception as rb_e: logging.error(f"Error during transaction rollback: {rb_e}")
        logging.critical(f"A critical error occurred in process_international_dropship_route for order {order_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred.", "details": str(e)}), 500