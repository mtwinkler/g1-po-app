# order-processing-app/blueprints/international.py

from flask import Blueprint, jsonify, current_app, request, g
from sqlalchemy.sql import text
import re
import json
from datetime import datetime, timezone
import traceback
import time

from app import (
    verify_firebase_token,
    engine,
    SHIPPER_EIN,
    get_country_name_from_iso,
    get_hpe_mapping_with_fallback
)
import shipping_service # Assuming shipping_service.py is at the root
import gcs_service      # Assuming gcs_service.py is at the root

international_bp = Blueprint('international_bp', __name__)

@international_bp.route("/order/<int:order_id>/international-details", methods=['GET'])
@verify_firebase_token
def get_international_details(order_id):
    user_token_info = g.decoded_token
    print(f"DEBUG INTERN_DETAILS: Request for order {order_id} by user {user_token_info.get('uid', 'Unknown') if user_token_info else 'Unauthenticated'}")
    if engine is None:
        current_app.logger.error("Database engine not available.")
        return jsonify({"error": "Database engine not available."}), 500

    with engine.connect() as conn:
        try:
            order_query = text("SELECT customer_shipping_country_iso2 FROM orders WHERE id = :order_id")
            order_result = conn.execute(order_query, {"order_id": order_id}).fetchone()

            if not order_result:
                return jsonify({"error": "Order not found"}), 404

            customer_shipping_country_iso2 = order_result.customer_shipping_country_iso2
            print(f"DEBUG INTERN_DETAILS: Order {order_id}, Country ISO: {customer_shipping_country_iso2}")

            target_country_name = get_country_name_from_iso(customer_shipping_country_iso2)
            print(f"DEBUG INTERN_DETAILS: Order {order_id}, Target Country Name for query: {target_country_name}")

            compliance_fields_query = text("""
                SELECT field_label, id_owner, is_required, has_exempt_option
                FROM country_compliance_fields
                WHERE country_name = :country_name_param OR country_name = '*'
            """)
            compliance_results = conn.execute(compliance_fields_query, {"country_name_param": target_country_name}).fetchall()
            required_compliance_fields = [dict(row._mapping) for row in compliance_results]
            print(f"DEBUG INTERN_DETAILS: Found {len(required_compliance_fields)} compliance fields for '{target_country_name}' (and *).")

            line_items_query = text("""
                SELECT id AS original_order_line_item_id, sku, quantity, name AS product_name
                FROM order_line_items WHERE order_id = :order_id
            """)
            line_items_results = conn.execute(line_items_query, {"order_id": order_id}).fetchall()
            print(f"DEBUG INTERN_DETAILS: Found {len(line_items_results)} line items for order {order_id}.")

            line_items_customs_info = []
            if line_items_results:
                for item_row in line_items_results:
                    item = dict(item_row._mapping)
                    original_sku = item['sku']
                    print(f"DEBUG INTERN_DETAILS: Processing SKU {original_sku} for line item {item['original_order_line_item_id']}")

                    customs_data = {
                        "original_order_line_item_id": item['original_order_line_item_id'],
                        "sku": original_sku,
                        "product_name": item.get('product_name', 'N/A'),
                        "quantity": item['quantity'],
                        "option_pn_used_for_lookup": None,
                        "product_type_used_for_lookup": None,
                        "customs_description": f"N/A - Mapping/Customs data lookup failed for SKU: {original_sku}",
                        "harmonized_tariff_code": "N/A",
                        "default_country_of_origin": "US"
                    }

                    hpe_option_pn, _, _ = get_hpe_mapping_with_fallback(original_sku, conn)
                    customs_data["option_pn_used_for_lookup"] = hpe_option_pn
                    print(f"DEBUG INTERN_DETAILS: SKU {original_sku} mapped to Option PN: {hpe_option_pn}")

                    if hpe_option_pn:
                        pt_query = text("SELECT product_type FROM product_types WHERE option_pn = :option_pn LIMIT 1")
                        pt_result = conn.execute(pt_query, {"option_pn": hpe_option_pn}).fetchone()

                        if pt_result:
                            product_type_val = pt_result.product_type
                            customs_data["product_type_used_for_lookup"] = product_type_val
                            print(f"DEBUG INTERN_DETAILS: Option PN {hpe_option_pn} mapped to Product Type: {product_type_val}")

                            ci_query = text("""
                                SELECT customs_description, harmonized_tariff_code, default_country_of_origin
                                FROM customs_info WHERE LOWER(product_type) = LOWER(:product_type) LIMIT 1
                            """)
                            ci_result = conn.execute(ci_query, {"product_type": product_type_val}).fetchone()

                            if ci_result:
                                customs_data["customs_description"] = ci_result.customs_description
                                customs_data["harmonized_tariff_code"] = ci_result.harmonized_tariff_code
                                customs_data["default_country_of_origin"] = ci_result.default_country_of_origin
                                print(f"DEBUG INTERN_DETAILS: Found customs info for Product Type {product_type_val}")
                            else:
                                print(f"WARN INTERN_DETAILS: Customs info not found for product type: {product_type_val}")
                                customs_data["customs_description"] = f"Customs info not found for product type: {product_type_val}"
                        else:
                            print(f"WARN INTERN_DETAILS: Product type not found for Option PN: {hpe_option_pn}")
                            customs_data["customs_description"] = f"Product type not found for Option PN: {hpe_option_pn}"
                    else:
                         print(f"WARN INTERN_DETAILS: Option PN not found for SKU: {original_sku}")

                    line_items_customs_info.append(customs_data)

            response_data = {
                "order_id": order_id,
                "customer_shipping_country_iso2": customer_shipping_country_iso2,
                "country_name": target_country_name,
                "line_items_customs_info": line_items_customs_info,
                "required_compliance_fields": required_compliance_fields,
                "shipper_ein": SHIPPER_EIN
            }
            print(f"DEBUG INTERN_DETAILS: Successfully prepared data for order {order_id}")
            return jsonify(response_data), 200

        except Exception as e:
            current_app.logger.error(f"Error in get_international_details for order {order_id}: {e}", exc_info=True)
            return jsonify({"error": "An internal error occurred while fetching international details.", "details": str(e)}), 500

@international_bp.route('/order/<int:order_id>/generate-international-shipment', methods=['POST'])
@verify_firebase_token
def generate_international_shipment_route(order_id): # Changed: Removed 'user' param, use g.decoded_token
    user_token_info = g.decoded_token
    print(f"INFO INTL_SHIP_ROUTE: Request for order {order_id} by user {user_token_info.get('uid', 'Unknown') if user_token_info else 'Unauthenticated'}")
    if not shipping_service or not gcs_service:
        current_app.logger.error("Shipping or GCS service not initialized. Cannot generate international shipment.")
        return jsonify({"message": "Server configuration error: Shipping or GCS service not available."}), 503

    shipment_payload_from_frontend = request.get_json()
    if not shipment_payload_from_frontend:
        return jsonify({"message": "Request body is missing or not valid JSON"}), 400

    with engine.connect() as conn_outer: # Renamed to avoid conflict if inner 'conn' is used
        try:
            order_query = text("SELECT id, bigcommerce_order_id FROM orders WHERE id = :order_id")
            order_data_result = conn_outer.execute(order_query, {"order_id": order_id}).fetchone()

            if not order_data_result:
                current_app.logger.error(f"Order {order_id} not found during shipment generation attempt.")
                return jsonify({"message": "Order not found"}), 404

            order_details = dict(order_data_result._mapping)
            bigcommerce_order_id_for_filename = order_details.get('bigcommerce_order_id') or order_id

            print(f"INFO INTL_SHIP_ROUTE: Calling generate_ups_international_shipment for order {order_id}")
            # generate_ups_international_shipment now returns raw image_bytes (e.g., GIF)
            raw_label_image_bytes, tracking_number = shipping_service.generate_ups_international_shipment(shipment_payload_from_frontend)

            if not tracking_number:
                current_app.logger.error(f"generate_ups_international_shipment returned no tracking for order {order_id}.")
                return jsonify({"message": "Shipment generation failed. Carrier might have rejected request. See server logs."}), 502

            label_url = None
            final_pdf_bytes_for_gcs = None

            if raw_label_image_bytes:
                print(f"DEBUG INTL_SHIP_ROUTE: Raw label image bytes received (length: {len(raw_label_image_bytes)}). Attempting PDF conversion.")
                # Convert the raw image (GIF) to PDF
                final_pdf_bytes_for_gcs = shipping_service.convert_image_bytes_to_pdf_bytes(raw_label_image_bytes, image_format="GIF")
                if not final_pdf_bytes_for_gcs:
                    current_app.logger.error(f"CRITICAL: PDF conversion failed for tracking {tracking_number}. Label will not be uploaded as PDF.")
                    # Optionally, you could decide to upload the raw GIF here or handle the error differently
                else:
                    print(f"DEBUG INTL_SHIP_ROUTE: PDF conversion successful for tracking {tracking_number}.")
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    filename = f"shipping_labels/order_{bigcommerce_order_id_for_filename}/UPS_INTL_{tracking_number}_{timestamp}.pdf"
                    try:
                        print(f"INFO INTL_SHIP_ROUTE: Uploading PDF label to GCS: {filename}")
                        label_url = gcs_service.upload_file_bytes(
                            file_bytes=final_pdf_bytes_for_gcs, # Upload the converted PDF
                            destination_blob_name=filename,
                            content_type='application/pdf'
                        )
                        print(f"INFO INTL_SHIP_ROUTE: Successfully uploaded label for {tracking_number} to {label_url}")
                    except Exception as gcs_e:
                        current_app.logger.error(f"CRITICAL: GCS upload failed for tracking {tracking_number}. Error: {gcs_e}", exc_info=True)
                        # Still return tracking, but with a warning about the label
            else:
                print(f"WARN INTL_SHIP_ROUTE: No raw label image bytes received from shipping service for tracking {tracking_number}. Label not saved to GCS.")

            # Record the new shipment in the local database (using conn_outer)
            try:
                print(f"INFO INTL_SHIP_ROUTE: Saving shipment record for tracking {tracking_number} to database.")
                shipment_insert_query = text("""
                    INSERT INTO shipments (order_id, carrier, tracking_number, label_gcs_url, created_at, service_used)
                    VALUES (:order_id, :carrier, :tracking_number, :label_gcs_url, :created_at, :service_used)
                """)
                service_code_used = shipment_payload_from_frontend.get('ShipmentRequest', {}).get('Shipment', {}).get('Service', {}).get('Code', 'N/A')

                conn_outer.execute(shipment_insert_query, {
                    "order_id": order_id, "carrier": 'UPS', "tracking_number": tracking_number,
                    "label_gcs_url": label_url, "created_at": datetime.now(timezone.utc),
                    "service_used": service_code_used
                })
                print(f"INFO INTL_SHIP_ROUTE: Updating order {order_id} status to 'Processed'.")
                order_update_query = text("UPDATE orders SET status = :status WHERE id = :order_id")
                conn_outer.execute(order_update_query, {"status": 'Processed', "order_id": order_id})
                conn_outer.commit()
                print(f"INFO INTL_SHIP_ROUTE: Shipment record for {tracking_number} and order status update committed.")
            except Exception as db_e:
                conn_outer.rollback()
                current_app.logger.error(f"CRITICAL: DB write failed for tracking {tracking_number}. Error: {db_e}", exc_info=True)
                return jsonify({
                    "message": "Shipment generated but failed to record in database.",
                    "trackingNumber": tracking_number, "labelUrl": label_url,
                    "error": "A database error occurred after shipment creation."
                }), 500

            return jsonify({
                "message": "International shipment generated successfully.",
                "trackingNumber": tracking_number, "labelUrl": label_url
            }), 200

        except Exception as e:
            if conn_outer.in_transaction: conn_outer.rollback()
            current_app.logger.error(f"Unexpected error in generate_international_shipment_route for order {order_id}: {e}", exc_info=True)
            return jsonify({"message": "An unexpected server error occurred while processing the shipment."}), 500

@international_bp.route('/order/<int:order_id>/process-international-dropship', methods=['POST', 'OPTIONS'])
@verify_firebase_token
def process_international_dropship_route(order_id): # Changed: Removed 'user' param, use g.decoded_token
    user_token_info = g.decoded_token
    print(f"INFO INTL_DROPSHIP_ROUTE: Request for order {order_id} by user {user_token_info.get('uid', 'Unknown') if user_token_info else 'Unauthenticated'}")

    if request.method == 'OPTIONS':
        return jsonify({"message": "OPTIONS request successful"}), 200

    combined_payload = request.get_json()
    if not combined_payload:
        return jsonify({"message": "Request body is missing or not valid JSON"}), 400

    po_data = combined_payload.get('po_data')
    shipment_data = combined_payload.get('shipment_data')

    if not shipment_data:
        return jsonify({"message": "Shipment data is missing in the payload"}), 400

    created_po_number = None
    # Placeholder for actual PO database ID after PO creation
    po_db_id_for_shipment_association = None

    if po_data:
        print(f"INFO INTL_DROPSHIP_ROUTE: PO Data received for order {order_id}: {po_data.get('supplier_id')}")
        # TODO: Implement actual PO creation logic here.
        # This would involve database inserts for purchase_orders and purchase_order_line_items.
        # After successful PO creation, you would get a po_db_id_for_shipment_association.
        # And then generate PO PDF and email it.
        created_po_number = f"PO_INTL_DS_{order_id}_{int(time.time())}" # Placeholder
        print(f"INFO INTL_DROPSHIP_ROUTE: Placeholder PO Number created: {created_po_number}")
        # For now, po_db_id_for_shipment_association remains None. In a real implementation,
        # it would be the ID of the PO record created in the database.

    try:
        print(f"INFO INTL_DROPSHIP_ROUTE: Calling shipping_service.generate_ups_international_shipment for order {order_id}")
        # generate_ups_international_shipment now returns raw image_bytes (e.g., GIF)
        raw_label_image_bytes, tracking_number = shipping_service.generate_ups_international_shipment(shipment_data)

        if not tracking_number:
            current_app.logger.error(f"shipping_service.generate_ups_international_shipment returned no tracking for order {order_id} (dropship).")
            return jsonify({"message": "International shipment generation failed. Carrier might have rejected request."}), 502

        label_url = None
        final_pdf_bytes_for_gcs = None # Initialize

        if raw_label_image_bytes:
            print(f"DEBUG INTL_DROPSHIP_ROUTE: Raw label image bytes received (length: {len(raw_label_image_bytes)}). Attempting PDF conversion.")
            # Convert the raw image (GIF) to PDF using the function from shipping_service
            if hasattr(shipping_service, 'convert_image_bytes_to_pdf_bytes'):
                final_pdf_bytes_for_gcs = shipping_service.convert_image_bytes_to_pdf_bytes(raw_label_image_bytes, image_format="GIF")
                if not final_pdf_bytes_for_gcs:
                    current_app.logger.error(f"CRITICAL: PDF conversion failed for tracking {tracking_number} (dropship). Label will not be uploaded as PDF.")
                else:
                    print(f"DEBUG INTL_DROPSHIP_ROUTE: PDF conversion successful for tracking {tracking_number} (dropship).")
            else:
                current_app.logger.error("CRITICAL: shipping_service.convert_image_bytes_to_pdf_bytes function not found. Cannot convert label to PDF.")
                # Decide how to handle: maybe upload raw GIF or return error

            # Proceed to upload if PDF conversion was successful (or if uploading raw GIF is acceptable fallback)
            if final_pdf_bytes_for_gcs: # Only attempt upload if we have PDF bytes
                bigcommerce_order_id_for_filename = order_id # Default
                # Fetch bigcommerce_order_id for a more descriptive filename
                # This can be done more efficiently if order_details are fetched once at the start of the route
                temp_conn_for_bc_id = None
                try:
                    temp_conn_for_bc_id = engine.connect()
                    order_bc_id_query = text("SELECT bigcommerce_order_id FROM orders WHERE id = :order_id")
                    order_data_result_for_fn = temp_conn_for_bc_id.execute(order_bc_id_query, {"order_id": order_id}).fetchone()
                    if order_data_result_for_fn and order_data_result_for_fn.bigcommerce_order_id:
                        bigcommerce_order_id_for_filename = order_data_result_for_fn.bigcommerce_order_id
                except Exception as bc_id_err:
                    current_app.logger.warning(f"Could not fetch bigcommerce_order_id for filename construction: {bc_id_err}")
                finally:
                    if temp_conn_for_bc_id:
                        temp_conn_for_bc_id.close()

                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                filename = f"shipping_labels/order_{bigcommerce_order_id_for_filename}/UPS_INTL_DS_{tracking_number}_{timestamp}.pdf"
                try:
                    label_url = gcs_service.upload_file_bytes(file_bytes=final_pdf_bytes_for_gcs, destination_blob_name=filename, content_type='application/pdf')
                    print(f"INFO INTL_DROPSHIP_ROUTE: Successfully uploaded PDF label for {tracking_number} to {label_url}")
                except Exception as gcs_e:
                    current_app.logger.error(f"CRITICAL: GCS upload of PDF failed for tracking {tracking_number} (dropship). Error: {gcs_e}", exc_info=True)
                    # Label URL will remain None
        else:
            print(f"WARN INTL_DROPSHIP_ROUTE: No raw label image bytes received from shipping service for tracking {tracking_number} (dropship). Label not saved to GCS.")

        with engine.connect() as conn:
            try:
                shipment_insert_query = text("""
                    INSERT INTO shipments (order_id, carrier, tracking_number, label_gcs_url, created_at, service_used, purchase_order_id)
                    VALUES (:order_id, :carrier, :tracking_number, :label_gcs_url, :created_at, :service_used, :purchase_order_id)
                """)
                service_code_used = shipment_data.get('ShipmentRequest', {}).get('Shipment', {}).get('Service', {}).get('Code', 'N/A')
                conn.execute(shipment_insert_query, {
                    "order_id": order_id, "carrier": 'UPS', "tracking_number": tracking_number,
                    "label_gcs_url": label_url, "created_at": datetime.now(timezone.utc),
                    "service_used": service_code_used, "purchase_order_id": po_db_id_for_shipment_association # Use the ID from created PO
                })
                order_update_query = text("UPDATE orders SET status = :status WHERE id = :order_id")
                conn.execute(order_update_query, {"status": 'Processed', "order_id": order_id})
                conn.commit()
            except Exception as db_e:
                conn.rollback()
                current_app.logger.error(f"CRITICAL: DB write failed for tracking {tracking_number} (dropship). Error: {db_e}", exc_info=True)
                return jsonify({"message": "Shipment generated but failed to record in database.", "trackingNumber": tracking_number, "labelUrl": label_url, "poNumber": created_po_number, "db_error": True}), 500

        return jsonify({
            "message": "International drop-ship processed successfully.",
            "poNumber": created_po_number,
            "trackingNumber": tracking_number,
            "labelUrl": label_url
        }), 200

    except Exception as e:
        current_app.logger.error(f"Unexpected error in process_international_dropship_route for order {order_id}: {e}", exc_info=True)
        return jsonify({"message": "An unexpected server error occurred."}), 500
