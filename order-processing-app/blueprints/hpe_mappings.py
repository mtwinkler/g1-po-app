# order-processing-app/blueprints/hpe_mappings.py

import traceback
from flask import Blueprint, jsonify, request, g, current_app
import sqlalchemy # For sqlalchemy.exc.IntegrityError
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert # For create_hpe_description_mapping
from datetime import datetime, timezone # Not directly used in these routes but good practice if needed
from decimal import Decimal # Not directly used but good practice

# Imports from the main app.py
from app import (
    engine, verify_firebase_token,
    convert_row_to_dict, make_json_safe,
    get_hpe_mapping_with_fallback # This helper is used by get_description_for_sku
)
# No specific service modules like document_generator are directly used by these CRUD/lookup routes

hpe_mappings_bp = Blueprint('hpe_mappings_bp', __name__)

@hpe_mappings_bp.route('/hpe-descriptions', methods=['POST', 'OPTIONS'])
@verify_firebase_token
def create_hpe_description_mapping():
    # OPTIONS is handled by verify_firebase_token
    print("Received request for POST /api/hpe-descriptions (HPE Description Mapping)")
    if engine is None:
        return jsonify({"message": "Database engine not initialized."}), 500

    conn = None
    trans = None
    try:
        data = request.json
        print(f"DEBUG CREATE_HPE_DESC: Received data: {data}")

        option_pn = data.get('option_pn')
        po_description = data.get('po_description')

        if not option_pn or not po_description:
            print(f"DEBUG CREATE_HPE_DESC: Missing required field: option_pn or po_description")
            return jsonify({"message": "Missing required field: option_pn or po_description"}), 400

        conn = engine.connect()
        trans = conn.begin()

        hpe_table = sqlalchemy.table('hpe_description_mappings',
                                     sqlalchemy.column('option_pn'),
                                     sqlalchemy.column('po_description'))

        insert_stmt = insert(hpe_table).values(
            option_pn=option_pn,
            po_description=po_description
        )
        conn.execute(insert_stmt)

        trans.commit()
        print(f"DEBUG CREATE_HPE_DESC: Inserted HPE Description Mapping for Option PN: {option_pn}")
        return jsonify({"message": "HPE Description Mapping created successfully", "option_pn": option_pn, "po_description": po_description}), 201
    except sqlalchemy.exc.IntegrityError as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG CREATE_HPE_DESC: Integrity Error: {e}")
        if "duplicate key value violates unique constraint" in str(e.orig).lower() and "hpe_description_mappings_pkey" in str(e.orig).lower():
            return jsonify({"message": f"Creation failed: Option PN '{option_pn}' already exists.", "error_type": "DuplicateOptionPN"}), 409
        return jsonify({"message": f"Database integrity error: {e.orig}", "error_type": "IntegrityError"}), 409
    except Exception as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG CREATE_HPE_DESC: Unexpected exception: {e}")
        traceback.print_exc()
        return jsonify({"message": f"HPE Description Mapping creation failed: {str(e)}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print("DEBUG CREATE_HPE_DESC: DB connection closed.")

@hpe_mappings_bp.route('/hpe-descriptions', methods=['GET']) # OPTIONS handled by decorator
@verify_firebase_token
def list_hpe_description_mappings():
    print("Received request for GET /api/hpe-descriptions (HPE Description Mappings)")
    if engine is None:
        return jsonify({"error": "Database engine not initialized."}), 500

    conn = None
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 25, type=int)
        if page < 1: page = 1
        if per_page < 1: per_page = 1
        if per_page > 100: per_page = 100
        offset = (page - 1) * per_page
        filter_option_pn = request.args.get('filter_option_pn', None, type=str)

        base_query_fields = "SELECT option_pn, po_description FROM hpe_description_mappings"
        count_query_fields = "SELECT COUNT(*) FROM hpe_description_mappings"
        where_clauses = []
        query_params = {}

        if filter_option_pn and filter_option_pn.strip():
            where_clauses.append("option_pn ILIKE :filter_option_pn_param")
            query_params["filter_option_pn_param"] = f"%{filter_option_pn.strip()}%"
        
        where_sql = ""
        if where_clauses:
            where_sql = " WHERE " + " AND ".join(where_clauses)

        pagination_query_params = {"limit_param": per_page, "offset_param": offset}
        data_sql_str = f"{base_query_fields}{where_sql} ORDER BY option_pn LIMIT :limit_param OFFSET :offset_param"
        final_data_query_params = {**query_params, **pagination_query_params}
        data_query = text(data_sql_str)

        count_sql_str = f"{count_query_fields}{where_sql}"
        count_query = text(count_sql_str)

        conn = engine.connect()
        result = conn.execute(data_query, final_data_query_params)
        mappings_list = [convert_row_to_dict(row) for row in result]
        
        total_count_result = conn.execute(count_query, query_params).scalar_one_or_none()
        total_items = total_count_result if total_count_result is not None else 0
        total_pages = (total_items + per_page - 1) // per_page if per_page > 0 else 0

        return jsonify({
            "mappings": make_json_safe(mappings_list),
            "pagination": {
                "currentPage": page, "perPage": per_page,
                "totalItems": total_items, "totalPages": total_pages
            }
        }), 200
    except Exception as e:
        print(f"ERROR LIST_HPE_DESC: Unexpected exception: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Error fetching HPE description mappings: {str(e)}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed:
            conn.close()
            print("DEBUG LIST_HPE_DESC: DB connection closed.")

@hpe_mappings_bp.route('/hpe-descriptions/<path:mapping_id>', methods=['GET'])
@verify_firebase_token
def get_hpe_description_mapping(mapping_id):
    option_pn_param = mapping_id
    print(f"Received request for GET /api/hpe-descriptions/{option_pn_param} (HPE Description Mapping)")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn = None
    try:
        conn = engine.connect()
        query = text("SELECT option_pn, po_description FROM hpe_description_mappings WHERE option_pn = :option_pn_param")
        result = conn.execute(query, {"option_pn_param": option_pn_param}).fetchone()
        if result is None:
            print(f"DEBUG GET_HPE_DESC: HPE Mapping with Option PN '{option_pn_param}' not found.")
            return jsonify({"message": f"HPE Mapping with Option PN '{option_pn_param}' not found."}), 404
        
        mapping_dict = convert_row_to_dict(result)
        print(f"DEBUG GET_HPE_DESC: Found HPE mapping for Option PN: {option_pn_param}.")
        return jsonify(make_json_safe(mapping_dict)), 200
    except Exception as e:
        print(f"DEBUG GET_HPE_DESC: Unexpected exception: {e}")
        traceback.print_exc()
        return jsonify({"message": f"Error fetching HPE mapping: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG GET_HPE_DESC: DB conn closed for Option PN {option_pn_param}.")

@hpe_mappings_bp.route('/hpe-descriptions/<path:mapping_id>', methods=['PUT'])
@verify_firebase_token
def update_hpe_description_mapping(mapping_id):
    option_pn_param = mapping_id
    print(f"Received request for PUT /api/hpe-descriptions/{option_pn_param} (HPE Description Mapping)")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn, trans = None, None
    try:
        data = request.json
        print(f"DEBUG UPDATE_HPE_DESC: Data for Option PN {option_pn_param}: {data}")
        
        new_po_description = data.get('po_description')
        if new_po_description is None:
             return jsonify({"message": "No 'po_description' field provided for update."}), 400
        
        conn = engine.connect(); trans = conn.begin()
        
        check_sql = text("SELECT 1 FROM hpe_description_mappings WHERE option_pn = :option_pn_param")
        exists = conn.execute(check_sql, {"option_pn_param": option_pn_param}).fetchone()
        if not exists:
            trans.rollback(); print(f"DEBUG UPDATE_HPE_DESC: HPE Mapping with Option PN {option_pn_param} not found.")
            return jsonify({"message": f"HPE Mapping with Option PN {option_pn_param} not found."}), 404
        
        update_sql = text("UPDATE hpe_description_mappings SET po_description = :new_po_description WHERE option_pn = :option_pn_param")
        update_params = {"new_po_description": new_po_description, "option_pn_param": option_pn_param}
        result = conn.execute(update_sql, update_params)
        
        if result.rowcount == 0: # Should not happen if exists check passed
            trans.rollback()
            return jsonify({"message": f"HPE Mapping with Option PN {option_pn_param} found but not updated (no change or error)."}), 404

        trans.commit(); print(f"DEBUG UPDATE_HPE_DESC: Updated HPE mapping for Option PN: {option_pn_param}")
        return jsonify({"message": f"HPE Mapping for Option PN {option_pn_param} updated successfully"}), 200
    except Exception as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG UPDATE_HPE_DESC: Unexpected exception: {e}")
        traceback.print_exc()
        return jsonify({"message": f"HPE Mapping update failed: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG UPDATE_HPE_DESC: DB conn closed for Option PN {option_pn_param}.")

@hpe_mappings_bp.route('/hpe-descriptions/<path:mapping_id>', methods=['DELETE'])
@verify_firebase_token
def delete_hpe_description_mapping(mapping_id):
    option_pn_param = mapping_id
    print(f"Received request for DELETE /api/hpe-descriptions/{option_pn_param} (HPE Description Mapping)")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn, trans = None, None
    try:
        conn = engine.connect(); trans = conn.begin()
        delete_sql = text("DELETE FROM hpe_description_mappings WHERE option_pn = :option_pn_param")
        result = conn.execute(delete_sql, {"option_pn_param": option_pn_param})
        
        if result.rowcount == 0:
            trans.rollback(); print(f"DEBUG DELETE_HPE_DESC: HPE Mapping with Option PN {option_pn_param} not found.")
            return jsonify({"message": f"HPE Mapping with Option PN {option_pn_param} not found."}), 404
        
        trans.commit(); print(f"DEBUG DELETE_HPE_DESC: Deleted HPE mapping for Option PN: {option_pn_param}")
        return jsonify({"message": f"HPE Mapping for Option PN {option_pn_param} deleted successfully"}), 200
    except Exception as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG DELETE_HPE_DESC: Unexpected exception: {e}")
        traceback.print_exc()
        return jsonify({"message": f"HPE Mapping deletion failed: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG DELETE_HPE_DESC: DB conn closed for Option PN {option_pn_param}.")

@hpe_mappings_bp.route('/lookup/spare_part/<path:option_sku>', methods=['GET'])
@verify_firebase_token
def get_spare_part_for_option(option_sku):
    if not option_sku: return jsonify({"error": "Option SKU is required"}), 400
    db_conn = None
    print(f"DEBUG LOOKUP_SPARE: Received request for option SKU: {option_sku}")
    try:
        if engine is None: return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect() # Use db_conn as per original
        find_spare_query = text("SELECT sku FROM hpe_part_mappings WHERE option_pn = :option_sku AND pn_type = 'spare'")
        spare_part_sku_record = db_conn.execute(find_spare_query, {"option_sku": option_sku}).fetchone()
        if spare_part_sku_record and spare_part_sku_record.sku:
            spare_sku = spare_part_sku_record.sku
            return jsonify({"spare_sku": spare_sku}), 200
        else:
            # is_option_query = text("SELECT 1 FROM hpe_part_mappings WHERE option_pn = :option_sku AND pn_type = 'option' LIMIT 1")
            # is_valid_option = db_conn.execute(is_option_query, {"option_sku": option_sku}).fetchone()
            # if not is_valid_option:
            # print(f"DEBUG LOOKUP_SPARE: Input SKU '{option_sku}' is not registered as an 'option' type.")
            return jsonify({"spare_sku": None, "message": "No corresponding spare part found or input SKU is not a valid option."}), 404
    except Exception as e:
        print(f"ERROR LOOKUP_SPARE: Error looking up spare part for option SKU {option_sku}: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to lookup spare part", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print(f"DEBUG LOOKUP_SPARE: DB connection closed for option SKU {option_sku}.")

@hpe_mappings_bp.route('/lookup/description/<path:sku_value>', methods=['GET'])
@verify_firebase_token
def get_description_for_sku(sku_value):
    if not sku_value: return jsonify({"description": None}), 400
    db_conn, description = None, None
    print(f"DEBUG LOOKUP_DESC: Received request for SKU: {sku_value}")
    try:
        if engine is None: return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect() # Use db_conn as per original

        # Logic using get_hpe_mapping_with_fallback for consistency with order details
        # This helper function already checks hpe_part_mappings
        hpe_option_pn, _, _ = get_hpe_mapping_with_fallback(sku_value, db_conn) # Pass db_conn

        if hpe_option_pn:
            # If we got an option_pn (either direct match or via spare part mapping), look it up in hpe_description_mappings
            desc_query = text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn")
            description = db_conn.execute(desc_query, {"option_pn": hpe_option_pn}).scalar_one_or_none()
            if description:
                print(f"DEBUG LOOKUP_DESC: Found description in hpe_description_mappings for (mapped/direct) OptionPN '{hpe_option_pn}'.")
        
        # Fallback: If no description from hpe_description_mappings, or if sku_value didn't map to an option_pn,
        # try the original products table (standard_description column).
        # Note: Your original code had a complex series of fallbacks.
        # The current `get_hpe_mapping_with_fallback` and then `hpe_description_mappings` should cover most cases.
        # If you need to check `products.standard_description` as an ultimate fallback, add it here.
        # For now, aligning with the primary purpose of custom PO descriptions:
        if description is None:
             # One direct check against products.standard_description for the original sku_value if desired
             # desc_query_products = text("SELECT standard_description FROM products WHERE sku = :sku")
             # description = db_conn.execute(desc_query_products, {"sku": sku_value}).scalar_one_or_none()
             # if description:
             # print(f"DEBUG LOOKUP_DESC: Found description in products.standard_description for '{sku_value}'.")
            print(f"DEBUG LOOKUP_DESC: No description found via hpe_description_mappings for SKU '{sku_value}' (or its mapped Option PN).")


        if description is None:
            return jsonify({"description": None}), 200 # 200 with None if not found by this logic
        
        return jsonify({"description": description}), 200
    except Exception as e:
        print(f"ERROR LOOKUP_DESC: Error looking up description for SKU {sku_value}: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to lookup description", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print(f"DEBUG LOOKUP_DESC: DB connection closed for SKU {sku_value}.")