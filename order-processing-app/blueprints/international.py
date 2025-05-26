from flask import Blueprint, jsonify, current_app
from sqlalchemy.sql import text
import re # Though not used in this specific version, often useful in blueprints

# CORRECTED IMPORTS
# Import shared helper functions and variables from the new utility module
from app_utils import get_country_name_from_iso, SHIPPER_EIN
# Import the authentication decorator from the main app file
from app import verify_firebase_token

international_bp = Blueprint('international_bp', __name__)

def get_hpe_option_pn_from_sku(sku_to_check, conn):
    """
    Attempts to find an HPE Option PN from an original SKU.
    This is a simplified version. The original app had more complex fallback logic
    (e.g., splitting SKU by '_' if direct match fails).
    For this version, we'll do a direct lookup.
    You may need to integrate the more complex 'get_hpe_mapping_with_fallback' logic here.
    """
    query = text("SELECT option_pn FROM hpe_part_mappings WHERE sku = :sku LIMIT 1")
    result = conn.execute(query, {"sku": sku_to_check}).fetchone()
    if result:
        return result['option_pn']
    
    # Simplified fallback: if SKU contains '_', try the part after the last '_'
    if '_' in sku_to_check:
        parts = sku_to_check.split('_')
        if len(parts) > 1:
            potential_option_pn = parts[-1]
            result_fallback = conn.execute(query, {"sku": potential_option_pn}).fetchone()
            if result_fallback:
                 return result_fallback['option_pn']
            # As a last resort for this simplified version, check if the potential_option_pn itself exists as an option_pn
            query_option_pn_direct = text("SELECT option_pn FROM hpe_part_mappings WHERE option_pn = :option_pn LIMIT 1")
            result_option_pn_direct = conn.execute(query_option_pn_direct, {"option_pn": potential_option_pn}).fetchone()
            if result_option_pn_direct:
                return result_option_pn_direct['option_pn']

    return None # Or return sku_to_check if no mapping found and original SKU should be used

@international_bp.route("/api/order/<int:order_id>/international-details", methods=['GET'])
@verify_firebase_token # Ensures the user is authenticated and authorized
def get_international_details(order_id):
    """
    Fetches all customs and compliance data needed for an international order.
    """
    try:
        # Use a 'with' statement to manage the connection from the application context
        with current_app.engine.connect() as conn:

            # 1. Fetch the order to get the destination country ISO
            order_query = text("SELECT customer_shipping_country_iso2 FROM orders WHERE id = :order_id")
            order_result = conn.execute(order_query, {"order_id": order_id}).fetchone()

            if not order_result:
                return jsonify({"error": "Order not found"}), 404

            customer_shipping_country_iso2 = order_result['customer_shipping_country_iso2']

            # 2. Convert ISO to full name using the helper function from app_utils
            country_name = get_country_name_from_iso(customer_shipping_country_iso2)
            if not country_name:
                # If the country ISO can't be mapped, we might not find specific compliance fields
                # but we can still proceed with '*' (global) compliance fields.
                # Or, you could return an error if a valid country name is strictly required.
                # For now, we'll allow it to proceed and rely on the '*' rule.
                pass

            # 3. Fetch compliance fields for that country name and the '*' wildcard
            compliance_fields_query = text("""
                SELECT field_label, id_owner, is_required, has_exempt_option
                FROM country_compliance_fields
                WHERE country_name = :country_name OR country_name = '*'
            """)
            # Ensure country_name is passed, even if None, for the '*' rule to apply if specific country not found
            compliance_results = conn.execute(compliance_fields_query, {"country_name": country_name}).fetchall()
            required_compliance_fields = [dict(row._mapping) for row in compliance_results]

            # 4. Fetch line items for the order
            line_items_query = text("""
                SELECT id AS original_order_line_item_id, sku, quantity
                FROM order_line_items WHERE order_id = :order_id
            """)
            line_items_results = conn.execute(line_items_query, {"order_id": order_id}).fetchall()

            line_items_customs_info = []
            if line_items_results:
                for item_row in line_items_results:
                    item = dict(item_row._mapping)
                    original_sku = item['sku']
                    customs_data = {
                        "original_order_line_item_id": item['original_order_line_item_id'],
                        "sku": original_sku,
                        "quantity": item['quantity'],
                        "customs_description": "N/A - Product not mapped", # Default
                        "harmonized_tariff_code": "N/A", # Default
                        "default_country_of_origin": "N/A" # Default
                    }

                    # Lookup chain:
                    # a. SKU from order_line_items -> option_pn from hpe_part_mappings
                    option_pn = get_hpe_option_pn_from_sku(original_sku, conn)

                    if option_pn:
                        # b. option_pn -> product_type from product_types
                        pt_query = text("SELECT product_type FROM product_types WHERE option_pn = :option_pn LIMIT 1")
                        pt_result = conn.execute(pt_query, {"option_pn": option_pn}).fetchone()

                        if pt_result:
                            product_type_val = pt_result['product_type']
                            # c. product_type -> customs_info
                            ci_query = text("""
                                SELECT customs_description, harmonized_tariff_code, default_country_of_origin
                                FROM customs_info WHERE product_type = :product_type LIMIT 1
                            """)
                            ci_result = conn.execute(ci_query, {"product_type": product_type_val}).fetchone()

                            if ci_result:
                                customs_data["customs_description"] = ci_result['customs_description']
                                customs_data["harmonized_tariff_code"] = ci_result['harmonized_tariff_code']
                                customs_data["default_country_of_origin"] = ci_result['default_country_of_origin']
                            else:
                                customs_data["customs_description"] = f"N/A - Customs info not found for product type: {product_type_val}"
                        else:
                            customs_data["customs_description"] = f"N/A - Product type not found for Option PN: {option_pn}"
                    else:
                         customs_data["customs_description"] = f"N/A - Option PN not found for SKU: {original_sku}"

                    line_items_customs_info.append(customs_data)

            # 6. Assemble the final response
            response_data = {
                "line_items_customs_info": line_items_customs_info,
                "required_compliance_fields": required_compliance_fields,
                "shipper_ein": SHIPPER_EIN # SHIPPER_EIN from app_utils
            }

            return jsonify(response_data), 200

    except Exception as e:
        # Use Flask's logger for better error handling in production
        current_app.logger.error(f"Error in get_international_details for order {order_id}: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred while fetching international details.", "details": str(e)}), 500