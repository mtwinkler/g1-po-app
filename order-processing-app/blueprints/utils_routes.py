# order-processing-app/blueprints/utils_routes.py

import traceback
from flask import Blueprint, jsonify, request, g, current_app
from datetime import datetime, timezone
import base64 # For email attachment
import sys # For traceback

# Imports from the main app.py or other modules
from app import (
    engine, verify_firebase_token, # verify_firebase_token is crucial
    SHIP_FROM_NAME, SHIP_FROM_CONTACT, SHIP_FROM_STREET1, SHIP_FROM_STREET2,
    SHIP_FROM_CITY, SHIP_FROM_STATE, SHIP_FROM_ZIP, SHIP_FROM_COUNTRY, SHIP_FROM_PHONE
)

# Import service modules
import shipping_service
import email_service

# The url_prefix here will be combined with the prefix used during registration in app.py
# If app.py registers with app.register_blueprint(utils_bp, url_prefix='/api/utils')
# and this blueprint has url_prefix='/generate_standalone_ups_label'
# then the final route is /api/utils/generate_standalone_ups_label.
# Let's define the full path within the route decorator for clarity matching original app.
utils_bp = Blueprint('utils_bp', __name__) # No url_prefix here, will be set at registration

@utils_bp.route('/generate_standalone_ups_label', methods=['POST'])
@verify_firebase_token
def generate_standalone_ups_label_route(): # Renamed function
    print("DEBUG STANDALONE_LABEL_BP: --- ROUTE ENTERED ---", flush=True)
    current_utc_datetime = datetime.now(timezone.utc)
    try:
        print("DEBUG STANDALONE_LABEL_BP: Attempting to get payload.", flush=True)
        payload = request.get_json()
        print(f"DEBUG STANDALONE_LABEL_BP: Payload received: {payload}", flush=True)

        ship_to_data = payload.get('ship_to')
        package_data = payload.get('package')
        shipping_method_name_from_payload = payload.get('shipping_method_name')
        
        if not all([ship_to_data, package_data, shipping_method_name_from_payload]):
            print("ERROR STANDALONE_LABEL_BP: Missing critical payload parts.", flush=True)
            return jsonify({"error": "Missing ship_to, package, or shipping_method_name in payload"}), 400

        if engine is None: # Though not used directly by this route, good to check services availability
            print("ERROR STANDALONE_LABEL_BP: Database engine is None (indirect check for app health)!", flush=True)
            # This route doesn't directly use the DB, but good to be aware if other utils might.
        if shipping_service is None:
            print("ERROR STANDALONE_LABEL_BP: shipping_service is None!", flush=True)
            return jsonify({"error": "Shipping service module not available."}), 500
        if email_service is None:
            print("ERROR STANDALONE_LABEL_BP: email_service is None!", flush=True)
            return jsonify({"error": "Email service module not available."}), 500
        
        ship_from_address_details = {
            'name': SHIP_FROM_NAME, 'contact_person': SHIP_FROM_CONTACT, 'street_1': SHIP_FROM_STREET1,
            'street_2': SHIP_FROM_STREET2, 'city': SHIP_FROM_CITY, 'state': SHIP_FROM_STATE,
            'zip': SHIP_FROM_ZIP, 'country': SHIP_FROM_COUNTRY, 'phone': SHIP_FROM_PHONE
        }
        if not all([ship_from_address_details['street_1'], ship_from_address_details['city'], 
                    ship_from_address_details['state'], ship_from_address_details['zip'], 
                    ship_from_address_details['phone']]):
            print("ERROR STANDALONE_LABEL_BP: Ship From address is not fully configured in environment variables.", flush=True)
            return jsonify({"error": "Server-side ship-from address not fully configured."}), 500
        
        ad_hoc_order_data = {
            "bigcommerce_order_id": f"STANDALONE_{int(current_utc_datetime.timestamp())}",
            "customer_company": ship_to_data.get('name'),
            "customer_name": ship_to_data.get('attention_name', ship_to_data.get('name')),
            "customer_phone": ship_to_data.get('phone'),
            "customer_shipping_address_line1": ship_to_data.get('address_line1'),
            "customer_shipping_address_line2": ship_to_data.get('address_line2', ''),
            "customer_shipping_city": ship_to_data.get('city'),
            "customer_shipping_state": ship_to_data.get('state'),
            "customer_shipping_zip": ship_to_data.get('zip_code'), # Matches frontend
            "customer_shipping_country": ship_to_data.get('country_code', 'US'), # Matches frontend
            "customer_email": "sales@globalonetechnology.com" # Default or from payload if available
        }
        
        total_weight_lbs = float(package_data['weight_lbs'])
        
        label_pdf_bytes, tracking_number = shipping_service.generate_ups_label(
            order_data=ad_hoc_order_data,
            ship_from_address=ship_from_address_details,
            total_weight_lbs=total_weight_lbs,
            customer_shipping_method_name=shipping_method_name_from_payload
        )

        if not label_pdf_bytes or not tracking_number:
            print(f"ERROR STANDALONE_LABEL_BP: Failed to generate UPS label. Tracking: {tracking_number}, Label Bytes: {bool(label_pdf_bytes)}", flush=True)
            return jsonify({"error": "Failed to generate UPS label. Check server logs.", "tracking_number": tracking_number}), 500
        
        print(f"INFO STANDALONE_LABEL_BP: UPS Label generated successfully. Tracking: {tracking_number}")

        email_subject = f"Standalone UPS Label Generated - Tracking: {tracking_number}"
        email_html_body = (
            f"<p>A UPS shipping label has been generated via the Standalone Label Generator.</p>"
            f"<p><b>Tracking Number:</b> {tracking_number}</p>"
            f"<p><b>Ship To:</b><br>"
            f"{ship_to_data.get('name', '')}<br>"
            f"{ship_to_data.get('attention_name', '') if ship_to_data.get('attention_name') else ''}<br>" # Handle if attention_name is empty
            f"{ship_to_data.get('address_line1', '')}<br>"
            f"{ship_to_data.get('address_line2', '') if ship_to_data.get('address_line2') else ''}<br>" # Handle if address_line2 is empty
            f"{ship_to_data.get('city', '')}, {ship_to_data.get('state', '')} {ship_to_data.get('zip_code', '')}<br>"
            f"{ship_to_data.get('country_code', '')}</p>"
            f"<p><b>Package Description:</b> {package_data.get('description', 'N/A')}</p>"
            f"<p><b>Weight:</b> {total_weight_lbs} lbs</p>"
            f"<p><b>Shipping Method:</b> {shipping_method_name_from_payload}</p>"
            f"<p>The label is attached to this email.</p>"
        )
        email_text_body = email_html_body.replace("<p>", "").replace("</p>", "\n").replace("<br>", "\n").replace("<b>", "").replace("</b>", "")

        attachments = [{
            "Name": f"UPS_Label_{tracking_number}.pdf",
            "Content": base64.b64encode(label_pdf_bytes).decode('utf-8'),
            "ContentType": "application/pdf"
        }]
        email_sent = False
        # Check for specific function 'send_sales_notification_email' first
        if hasattr(email_service, 'send_sales_notification_email'):
            email_service.send_sales_notification_email(
                recipient_email="sales@globalonetechnology.com", # Hardcoded as per original
                subject=email_subject,
                html_body=email_html_body,
                text_body=email_text_body,
                attachments=attachments
            )
            email_sent = True
        elif hasattr(email_service, 'send_generic_email'): # Fallback
             email_service.send_generic_email(
                recipient_email="sales@globalonetechnology.com",
                subject=email_subject,
                html_body=email_html_body,
                # text_body=email_text_body, # Ensure your generic function handles this or remove
                attachments=attachments
            )
             email_sent = True
        else:
            print("ERROR STANDALONE_LABEL_BP: Suitable email function not found in email_service.py.")

        if email_sent:
            print(f"INFO STANDALONE_LABEL_BP: Email with label sent to sales@globalonetechnology.com.")
        else:
             print(f"WARN STANDALONE_LABEL_BP: Email function not found/failed, but label was generated. Tracking: {tracking_number}")

        return jsonify({
            "message": "UPS label generated and emailed successfully.",
            "tracking_number": tracking_number
        }), 200

    except ValueError as ve:
        print(f"ERROR STANDALONE_LABEL_BP (ValueError): {ve}", flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return jsonify({"error": "Processing failed due to invalid data.", "details": str(ve)}), 400
    except Exception as e:
        print(f"CRITICAL STANDALONE_LABEL_BP: UNHANDLED EXCEPTION IN ROUTE: {e}", flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return jsonify({"error": "An unexpected error occurred during standalone label generation.", "details": str(e)}), 500
    finally:
        print("DEBUG STANDALONE_LABEL_BP: --- ROUTE EXITING ---", flush=True)