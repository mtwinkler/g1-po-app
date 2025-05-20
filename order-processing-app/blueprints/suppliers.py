# order-processing-app/blueprints/suppliers.py

import traceback
from flask import Blueprint, jsonify, request, g, current_app
import sqlalchemy # Keep for sqlalchemy.exc.IntegrityError
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert # Used for create_supplier
from datetime import datetime, timezone
from decimal import Decimal # For get_supplier data conversion

# Imports from the main app.py
from app import (
    engine, verify_firebase_token,
    convert_row_to_dict, make_json_safe
)
# No specific service modules like document_generator are directly used by supplier CRUD

suppliers_bp = Blueprint('suppliers_bp', __name__)

@suppliers_bp.route('/suppliers', methods=['POST'])
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
        
        # Extract all potential fields from supplier_data
        name = supplier_data.get('name')
        email = supplier_data.get('email')
        payment_terms = supplier_data.get('payment_terms')
        address_line1 = supplier_data.get('address_line1')
        address_line2 = supplier_data.get('address_line2')
        city = supplier_data.get('city')
        state = supplier_data.get('state')
        zip_code = supplier_data.get('zip') # Frontend might send 'zip'
        country = supplier_data.get('country')
        phone = supplier_data.get('phone')
        contact_person = supplier_data.get('contact_person')
        actual_default_po_notes_value = supplier_data.get('defaultponotes')

        conn = engine.connect(); trans = conn.begin()
        
        # Define table and columns for SQLAlchemy insert helper
        suppliers_table = sqlalchemy.table('suppliers',
            sqlalchemy.column('name'), sqlalchemy.column('email'), sqlalchemy.column('payment_terms'),
            sqlalchemy.column('address_line1'), sqlalchemy.column('address_line2'),
            sqlalchemy.column('city'), sqlalchemy.column('state'), sqlalchemy.column('zip'), # Use 'zip' to match DB
            sqlalchemy.column('country'), sqlalchemy.column('phone'), sqlalchemy.column('contact_person'),
            sqlalchemy.column('defaultponotes'), sqlalchemy.column('created_at'), sqlalchemy.column('updated_at')
        )

        insert_supplier_stmt = insert(suppliers_table).values(
            name=name, email=email, payment_terms=payment_terms,
            address_line1=address_line1, address_line2=address_line2,
            city=city, state=state, zip=zip_code, country=country, phone=phone, # Use zip_code for value
            contact_person=contact_person, defaultponotes=actual_default_po_notes_value,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)
        )
        result = conn.execute(insert_supplier_stmt.returning(sqlalchemy.column('id')))
        inserted_supplier_id = result.fetchone()[0]
        trans.commit()
        print(f"DEBUG CREATE_SUPPLIER: Successfully inserted supplier with ID: {inserted_supplier_id}")
        return jsonify({"message": "Supplier created successfully", "supplier_id": inserted_supplier_id}), 201
    except sqlalchemy.exc.IntegrityError as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG CREATE_SUPPLIER: Integrity Error: {e}")
        # Check if the error is due to a duplicate key violation (e.g. unique constraint on name or email)
        # The exact error message might vary depending on the DB and constraint names
        if "duplicate key value violates unique constraint" in str(e.orig).lower():
             return jsonify({"message": f"Supplier creation failed: Duplicate entry (name or email likely already exists).", "error_type": "IntegrityError"}), 409
        return jsonify({"message": f"Supplier creation failed due to database integrity: {e.orig}", "error_type": "IntegrityError"}), 409
    except Exception as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG CREATE_SUPPLIER: Caught unexpected exception: {e}")
        traceback.print_exc()
        return jsonify({"message": f"Supplier creation failed: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print("DEBUG CREATE_SUPPLIER: Database connection closed.")

@suppliers_bp.route('/suppliers', methods=['GET'])
@verify_firebase_token
def list_suppliers():
    print("Received request for GET /api/suppliers")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn = None
    try:
        conn = engine.connect()
        query = text("SELECT * FROM suppliers ORDER BY name") # sqlalchemy.text
        result = conn.execute(query)
        # Use convert_row_to_dict and make_json_safe for consistency
        suppliers_list = [convert_row_to_dict(row) for row in result]
        print(f"DEBUG LIST_SUPPLIERS: Found {len(suppliers_list)} suppliers.")
        return jsonify(make_json_safe(suppliers_list)), 200
    except Exception as e:
        print(f"DEBUG LIST_SUPPLIERS: Caught unexpected exception: {e}")
        traceback.print_exc()
        return jsonify({"message": f"Error fetching suppliers: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print("DEBUG LIST_SUPPLIERS: Database connection closed.")

@suppliers_bp.route('/suppliers/<int:supplier_id>', methods=['GET'])
@verify_firebase_token
def get_supplier(supplier_id):
    print(f"Received request for GET /api/suppliers/{supplier_id}")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn = None
    try:
        conn = engine.connect()
        query = text("SELECT * FROM suppliers WHERE id = :supplier_id") # sqlalchemy.text
        result = conn.execute(query, {"supplier_id": supplier_id}).fetchone()
        if result is None:
            print(f"DEBUG GET_SUPPLIER: Supplier with ID {supplier_id} not found.")
            return jsonify({"message": f"Supplier with ID {supplier_id} not found."}), 404
        
        supplier_dict = convert_row_to_dict(result) # Use helper
        print(f"DEBUG GET_SUPPLIER: Found supplier with ID: {supplier_id}.")
        return jsonify(make_json_safe(supplier_dict)), 200 # Use helper
    except Exception as e:
        print(f"DEBUG GET_SUPPLIER: Caught unexpected exception: {e}")
        traceback.print_exc()
        return jsonify({"message": f"Error fetching supplier: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG GET_SUPPLIER: Database connection closed for ID {supplier_id}.")

@suppliers_bp.route('/suppliers/<int:supplier_id>', methods=['PUT'])
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
        existing_supplier = conn.execute(text("SELECT id FROM suppliers WHERE id = :supplier_id"), {"supplier_id": supplier_id}).fetchone() # sqlalchemy.text
        if not existing_supplier:
            trans.rollback(); print(f"DEBUG UPDATE_SUPPLIER: Supplier ID {supplier_id} not found.")
            return jsonify({"message": f"Supplier with ID {supplier_id} not found."}), 404
        
        update_fields_clauses, update_params = [], {"supplier_id": supplier_id, "updated_at": datetime.now(timezone.utc)}
        # Match these field names with what frontend sends and what your DB expects
        allowed_fields_map = {
            'name': 'name', 'email': 'email', 'payment_terms': 'payment_terms',
            'address_line1': 'address_line1', 'address_line2': 'address_line2',
            'city': 'city', 'state': 'state', 'zip': 'zip', # frontend might send 'zip', DB has 'zip'
            'country': 'country', 'phone': 'phone', 'contact_person': 'contact_person',
            'defaultponotes': 'defaultponotes'
        }
        
        for frontend_key, db_column_key in allowed_fields_map.items():
            if frontend_key in supplier_data: # Check if the key exists in payload
                update_fields_clauses.append(f"{db_column_key} = :{frontend_key}") # Use frontend_key for param name
                update_params[frontend_key] = supplier_data[frontend_key]
        
        if not update_fields_clauses:
             trans.rollback(); print(f"DEBUG UPDATE_SUPPLIER: No valid fields for ID {supplier_id}.")
             return jsonify({"message": "No valid update fields provided."}), 400
        
        update_query_text = f"UPDATE suppliers SET {', '.join(update_fields_clauses)}, updated_at = :updated_at WHERE id = :supplier_id"
        conn.execute(text(update_query_text), update_params) # sqlalchemy.text
        trans.commit(); print(f"DEBUG UPDATE_SUPPLIER: Updated supplier ID: {supplier_id}")
        return jsonify({"message": f"Supplier with ID {supplier_id} updated successfully"}), 200
    except sqlalchemy.exc.IntegrityError as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG UPDATE_SUPPLIER: Integrity Error: {e}")
        if "duplicate key value violates unique constraint" in str(e.orig).lower():
            return jsonify({"message": f"Supplier update failed: Duplicate entry (name or email likely already exists).", "error_type": "IntegrityError"}), 409
        return jsonify({"message": f"Supplier update failed due to database integrity: {e.orig}", "error_type": "IntegrityError"}), 409
    except Exception as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG UPDATE_SUPPLIER: Caught unexpected exception: {e}")
        traceback.print_exc()
        return jsonify({"message": f"Supplier update failed: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG UPDATE_SUPPLIER: DB conn closed for ID {supplier_id}.")

@suppliers_bp.route('/suppliers/<int:supplier_id>', methods=['DELETE'])
@verify_firebase_token
def delete_supplier(supplier_id):
    print(f"Received request for DELETE /api/suppliers/{supplier_id}")
    if engine is None: return jsonify({"message": "Database engine not initialized."}), 500
    conn, trans = None, None
    try:
        conn = engine.connect(); trans = conn.begin()
        check_po_sql = text("SELECT 1 FROM purchase_orders WHERE supplier_id = :supplier_id LIMIT 1") # sqlalchemy.text
        existing_po = conn.execute(check_po_sql, {"supplier_id": supplier_id}).fetchone()
        if existing_po:
            trans.rollback()
            print(f"DEBUG DELETE_SUPPLIER: Cannot delete supplier {supplier_id}, POs exist.")
            return jsonify({"message": "Cannot delete supplier: They are associated with existing purchase orders."}), 409

        result = conn.execute(text("DELETE FROM suppliers WHERE id = :supplier_id"), {"supplier_id": supplier_id}) # sqlalchemy.text
        if result.rowcount == 0:
            trans.rollback(); print(f"DEBUG DELETE_SUPPLIER: Supplier ID {supplier_id} not found.")
            return jsonify({"message": f"Supplier with ID {supplier_id} not found."}), 404
        trans.commit(); print(f"DEBUG DELETE_SUPPLIER: Deleted supplier ID: {supplier_id}")
        return jsonify({"message": f"Supplier with ID {supplier_id} deleted successfully"}), 200
    except Exception as e:
        if conn and trans and trans.is_active: trans.rollback()
        print(f"DEBUG DELETE_SUPPLIER: Exception during delete: {e}")
        traceback.print_exc()
        # You might want to check for specific DB foreign key errors if other tables reference suppliers
        # if "violates foreign key constraint" in str(e).lower():
        # return jsonify({"message": "Cannot delete supplier due to existing references.", "error_type":"ForeignKeyViolation"}),409
        return jsonify({"message": f"Supplier deletion failed: {e}", "error_type": type(e).__name__}), 500
    finally:
        if conn and not conn.closed: conn.close(); print(f"DEBUG DELETE_SUPPLIER: DB conn closed for ID {supplier_id}.")