# iif_generator.py (Updated Supplier Name & Fulfillment Note - PRODUCTION DATE LOGIC)

import os
import sqlalchemy
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta 
from decimal import Decimal
import traceback
import html 
import re # For supplier name stripping

# --- Email Service Import ---
try:
    import email_service
except ImportError:
    print("WARN IIF_GEN: Could not import 'email_service'. Email sending will fail.")
    email_service = None

# --- Database Engine Import/Setup ---
try:
    from app import engine 
except ImportError:
    print("WARN IIF_GEN: Could not import 'engine' from app.py. Will try to create one if run standalone.")
    engine = None

# --- QuickBooks Specific Configuration ---
QUICKBOOKS_PO_ACCOUNT = "Purchase Orders" 
QUICKBOOKS_DEFAULT_EXPENSE_ACCOUNT = "Cost of Goods Sold"

# --- QB Item Name Lookup Function ---
def get_qb_item_name_for_option_pn(conn, option_pn_from_po):
    if not option_pn_from_po:
        print(f"WARN IIF_GEN_MAP: Received empty or None Option PN for INVITEM.")
        return "", False 
    
    sql_mapping_query = text("SELECT qb_item_name FROM qb_product_mapping WHERE option_pn = :option_pn;")
    try:
        mapping_result = conn.execute(sql_mapping_query, {"option_pn": option_pn_from_po}).fetchone()
        if mapping_result and mapping_result.qb_item_name:
            qb_item_name = mapping_result.qb_item_name
            print(f"DEBUG IIF_GEN_MAP: Found QB mapping for Option PN '{option_pn_from_po}': INVITEM='{qb_item_name}'")
            return qb_item_name, True 
        else:
            print(f"WARN IIF_GEN_MAP: No QuickBooks mapping found for Option PN '{option_pn_from_po}'. Using Option PN as INVITEM.")
            return str(option_pn_from_po), False 
    except sqlalchemy.exc.SQLAlchemyError as db_err:
         print(f"ERROR IIF_GEN_MAP: Database error looking up Option PN '{option_pn_from_po}': {db_err}")
         return str(option_pn_from_po), False 
    except Exception as e:
        print(f"ERROR IIF_GEN_MAP: Unexpected error looking up Option PN '{option_pn_from_po}': {e}")
        return str(option_pn_from_po), False 

def sanitize_field(value, max_length=None):
    """Sanitizes a field value for IIF output."""
    if value is None:
        return ""
    s_value = str(value).strip()
    s_value = s_value.replace('\t', ' ')    
    s_value = s_value.replace('\r\n', ' ') 
    s_value = s_value.replace('\n', ' ')   
    s_value = s_value.replace('\r', ' ')   
    if max_length and len(s_value) > max_length:
        original_value_preview = str(value)[:30] + "..." if len(str(value)) > 30 else str(value)
        s_value = s_value[:max_length]
        print(f"WARN IIF_GEN: Truncated field content to {max_length} chars. Original: '{original_value_preview}', Truncated: '{s_value}'")
    return s_value

def strip_supplier_contact(supplier_name_full):
    """Strips (Contact Person) from supplier name if present."""
    if supplier_name_full is None:
        return ""
    # Use regex to remove content within the last parentheses, including parentheses
    # This handles cases like "Supplier Name (Contact A)" -> "Supplier Name"
    # and "Supplier Name (Branch) (Contact B)" -> "Supplier Name (Branch)"
    # To be more specific for "(Person)", we can adjust.
    # For simplicity, if the pattern is always "Name (Contact)", splitting works.
    match = re.search(r'^(.*?)\s*\([^)]*\)$', supplier_name_full)
    if match:
        return match.group(1).strip()
    return supplier_name_full # Return original if no parentheses found at the end


def generate_iif_content_for_date(db_engine_ref, target_date_str):
    iif_lines = [] 
    mapping_failures = [] 

    trns_header_fields = [
        "TRNSID", "TRNSTYPE", "DATE", "ACCNT", "NAME", "CLASS", "AMOUNT", "DOCNUM", "MEMO", 
        "CLEAR", "TOPRINT", "NAMEISTAXABLE", 
        "ADDR1", "ADDR2", "ADDR3", "ADDR4", "ADDR5", 
        "DUEDATE", "TERMS", "PAID", "PAYMETH", "SHIPVIA", "SHIPDATE", 
        "OTHER1", "REP", "FOB", "PONUM", "INVTITLE", "INVMEMO", 
        "SADDR1", "SADDR2", "SADDR3", "SADDR4", "SADDR5"
    ]
    spl_header_fields = [
        "SPLID", "TRNSTYPE", "DATE", "ACCNT", "NAME", "CLASS", "AMOUNT", "DOCNUM", "MEMO", 
        "CLEAR", "QNTY", "PRICE", "INVITEM", 
        "PAYMETH", "TAXABLE",
        "VALADJ", "REIMBEXP", "SERVICEDATE", "OTHER2", "OTHER3", 
        "PAYITEM", "YEARTODATE", "WAGEBASE", "EXTRA"
    ]
    
    iif_lines.append("!TRNS\t" + "\t".join(trns_header_fields))
    iif_lines.append("!SPL\t" + "\t".join(spl_header_fields))
    iif_lines.append("!ENDTRNS")

    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        print(f"CRITICAL IIF_GEN: Invalid target_date_str format: {target_date_str}. Expected yyyy-mm-dd.")
        return None, []

    conn = None
    try:
        if not db_engine_ref:
             print("CRITICAL IIF_GEN: Database engine is not available.")
             return None, []
        conn = db_engine_ref.connect()
        print(f"INFO IIF_GEN: Connected to DB to fetch POs for {target_date_str}")

        sql_data_query = text("""
            SELECT
                po.id as po_id, po.po_number, po.po_date,
                po.payment_instructions as payment_instructions, 
                s.name as supplier_name_full, -- Fetch full supplier name
                po.total_amount,
                o.customer_name, o.customer_shipping_address_line1, o.customer_shipping_address_line2,
                o.customer_shipping_city, o.customer_shipping_state, o.customer_shipping_zip,
                o.customer_shipping_country,
                o.bigcommerce_order_id -- Fetch BigCommerce Order ID for the fulfillment note
            FROM purchase_orders po
            JOIN suppliers s ON po.supplier_id = s.id
            JOIN orders o ON po.order_id = o.id 
            WHERE po.status = 'SENT_TO_SUPPLIER'
              AND DATE(po.po_date AT TIME ZONE 'UTC') = :target_date;
        """)
        purchase_orders_data = conn.execute(sql_data_query, {"target_date": target_date}).fetchall()
        print(f"INFO IIF_GEN: Found {len(purchase_orders_data)} Purchase Orders with status 'SENT_TO_SUPPLIER' for date {target_date_str}.")

        if not purchase_orders_data:
            empty_iif_trns_line = "TRNS\t" + "\t".join([""] * len(trns_header_fields))
            empty_iif_spl_line = "SPL\t" + "\t".join([""] * len(spl_header_fields))
            iif_lines.extend([empty_iif_trns_line, empty_iif_spl_line, "ENDTRNS"])
            return "\r\n".join(iif_lines) + "\r\n", []

        for po_row in purchase_orders_data:
            if po_row.po_date is None:
                print(f"WARN IIF_GEN: PO Number {po_row.po_number} has no po_date. Skipping this PO.")
                continue
            po_date_formatted = po_row.po_date.strftime("%m/%d/%Y")
            po_total_cost = Decimal(po_row.total_amount if po_row.total_amount is not None else '0.00')

            # Strip contact from supplier name for IIF
            iif_supplier_name = strip_supplier_contact(po_row.supplier_name_full)

            saddr1 = po_row.customer_name
            saddr2 = po_row.customer_shipping_address_line1
            saddr3 = po_row.customer_shipping_address_line2
            saddr4_parts = [po_row.customer_shipping_city, po_row.customer_shipping_state, po_row.customer_shipping_zip]
            saddr4 = " ".join(filter(None, saddr4_parts)) 
            saddr5 = po_row.customer_shipping_country
            
            trns_values_dict = {
                "TRNSID": "", "TRNSTYPE": "PURCHORD", "DATE": po_date_formatted,
                "ACCNT": QUICKBOOKS_PO_ACCOUNT, "NAME": iif_supplier_name, # Use stripped name
                "CLASS": "", "AMOUNT": str(po_total_cost * -1), 
                "DOCNUM": po_row.po_number, "MEMO": f"PO {po_row.po_number}",
                "CLEAR": "N", "TOPRINT": "Y", "NAMEISTAXABLE": "N", 
                "ADDR1": "", "ADDR2": "", "ADDR3": "", "ADDR4": "", "ADDR5": "", 
                "DUEDATE": po_date_formatted, 
                "TERMS": "", # Blank as requested
                "PAID": "N", "PAYMETH": "", 
                "SHIPVIA": "", # Blank as requested
                "SHIPDATE": po_date_formatted, 
                "OTHER1": "", "REP": "", "FOB": "", 
                "PONUM": po_row.po_number, 
                "INVTITLE": "", "INVMEMO": "", 
                "SADDR1": saddr1, "SADDR2": saddr2, "SADDR3": saddr3, 
                "SADDR4": saddr4, "SADDR5": saddr5
            }
            trns_data_ordered = [sanitize_field(trns_values_dict.get(field, "")) for field in trns_header_fields]
            iif_lines.append("TRNS\t" + "\t".join(trns_data_ordered))

            sql_line_items_query = text("""
                SELECT pli.sku as item_sku, pli.description AS item_description, 
                       pli.quantity, pli.unit_cost
                FROM po_line_items pli WHERE pli.purchase_order_id = :current_po_id;
            """)
            line_items = conn.execute(sql_line_items_query, {"current_po_id": po_row.po_id}).fetchall()

            if not line_items:
                print(f"WARN IIF_GEN: No line items found for PO ID {po_row.po_id} (PO Number: {po_row.po_number}).")

            for item_row in line_items:
                sku_to_lookup = item_row.item_sku 
                qb_invitem_name, mapping_found = get_qb_item_name_for_option_pn(conn, sku_to_lookup)
                
                if not mapping_found:
                    mapping_failures.append({
                        "po_number": po_row.po_number,
                        "failed_sku": sku_to_lookup if sku_to_lookup else "[EMPTY SKU]",
                        "description": item_row.item_description
                    })
                
                unit_cost = Decimal(item_row.unit_cost if item_row.unit_cost is not None else 0)
                quantity = Decimal(item_row.quantity if item_row.quantity is not None else 0)
                line_total_cost = unit_cost * quantity
                item_description_content = item_row.item_description if item_row.item_description else "Item"
                
                spl_values_dict = {
                    "SPLID": "", "TRNSTYPE": "PURCHORD", "DATE": po_date_formatted,
                    "ACCNT": QUICKBOOKS_DEFAULT_EXPENSE_ACCOUNT, "NAME": "", 
                    "CLASS": "", "AMOUNT": str(line_total_cost), 
                    "DOCNUM": po_row.po_number, "MEMO": item_description_content, 
                    "CLEAR": "N", "QNTY": str(quantity), "PRICE": str(unit_cost), 
                    "INVITEM": qb_invitem_name, 
                    "PAYMETH": "", "TAXABLE": "N",
                    "VALADJ": "N", "REIMBEXP": "NOTHING", "SERVICEDATE": "", "OTHER2": "", "OTHER3": "",
                    "PAYITEM": "", "YEARTODATE": "", "WAGEBASE": "", "EXTRA": ""
                }
                spl_data_ordered = [sanitize_field(spl_values_dict.get(field, "")) for field in spl_header_fields]
                iif_lines.append("SPL\t" + "\t".join(spl_data_ordered))
            
            # Add Payment Instructions as a zero-amount SPL line
            payment_instructions_text = po_row.payment_instructions
            if payment_instructions_text:
                memo_spl_values_dict = {
                    "SPLID": "", "TRNSTYPE": "PURCHORD", "DATE": po_date_formatted,
                    "ACCNT": QUICKBOOKS_DEFAULT_EXPENSE_ACCOUNT, "NAME": "", "CLASS": "",
                    "AMOUNT": "0.00", "DOCNUM": po_row.po_number,
                    "MEMO": payment_instructions_text, "CLEAR": "N",
                    "QNTY": "", "PRICE": "", "INVITEM": "", "PAYMETH": "", "TAXABLE": "N",
                    "VALADJ": "N", "REIMBEXP": "NOTHING", "SERVICEDATE": "", "OTHER2": "", "OTHER3": "",
                    "PAYITEM": "", "YEARTODATE": "", "WAGEBASE": "", "EXTRA": ""
                }
                memo_spl_data_ordered = [sanitize_field(memo_spl_values_dict.get(field, "")) for field in spl_header_fields]
                iif_lines.append("SPL\t" + "\t".join(memo_spl_data_ordered))
            
            # Add Fulfillment Note as another zero-amount SPL line
            bc_order_id = po_row.bigcommerce_order_id
            if bc_order_id:
                fulfillment_note = f"Fulfillment of G1 Order #{bc_order_id}"
                fulfillment_spl_values_dict = {
                    "SPLID": "", "TRNSTYPE": "PURCHORD", "DATE": po_date_formatted,
                    "ACCNT": QUICKBOOKS_DEFAULT_EXPENSE_ACCOUNT, "NAME": "", "CLASS": "",
                    "AMOUNT": "0.00", "DOCNUM": po_row.po_number,
                    "MEMO": fulfillment_note, "CLEAR": "N",
                    "QNTY": "", "PRICE": "", "INVITEM": "", "PAYMETH": "", "TAXABLE": "N",
                    "VALADJ": "N", "REIMBEXP": "NOTHING", "SERVICEDATE": "", "OTHER2": "", "OTHER3": "",
                    "PAYITEM": "", "YEARTODATE": "", "WAGEBASE": "", "EXTRA": ""
                }
                fulfillment_spl_data_ordered = [sanitize_field(fulfillment_spl_values_dict.get(field, "")) for field in spl_header_fields]
                iif_lines.append("SPL\t" + "\t".join(fulfillment_spl_data_ordered))
                print(f"DEBUG IIF_GEN: Added fulfillment note for G1 Order #{bc_order_id} to PO {po_row.po_number}")


            iif_lines.append("ENDTRNS")

        print(f"INFO IIF_GEN: Finished generating IIF content. Found {len(mapping_failures)} item mapping failures.")
        return "\r\n".join(iif_lines) + "\r\n", mapping_failures

    except sqlalchemy.exc.SQLAlchemyError as db_e:
        print(f"CRITICAL IIF_GEN: Database error generating IIF content for {target_date_str}: {db_e}")
        traceback.print_exc()
        return None, mapping_failures
    except Exception as e:
        print(f"CRITICAL IIF_GEN: Unexpected error generating IIF content for {target_date_str}: {e}")
        traceback.print_exc()
        return None, mapping_failures
    finally:
        if conn:
            conn.close()
            print(f"INFO IIF_GEN: DB connection closed for {target_date_str}")

def create_and_email_daily_iif_batch(db_engine_ref):
    # --- PRODUCTION DATE LOGIC: Use yesterday's date ---
    target_date_for_production = datetime.now(timezone.utc).date() - timedelta(days=1)
    batch_date_str = target_date_for_production.strftime("%Y-%m-%d")
    print(f"INFO IIF_BATCH: Generating IIF batch for date: {batch_date_str}")
    # --- END PRODUCTION DATE LOGIC ---

    iif_content, mapping_failures = generate_iif_content_for_date(db_engine_ref, batch_date_str)
    email_warning_html = None 

    if mapping_failures: 
        warning_lines = [
             '<p><strong><span style="color: red; font-size: 1.2em;">WARNING: QuickBooks Item Mapping Failures</span></strong></p>',
             '<p>The INVITEM field in the attached IIF file uses the original Option PN for items that could not be mapped. Please review your `qb_product_mapping` table or add these items in QuickBooks:</p>',
             '<ul>']
        unique_failures = set()
        for failure in mapping_failures:
            failure_key = (failure['po_number'], failure['failed_sku'])
            if failure_key not in unique_failures:
                desc_display = html.escape(failure['description'] or '[No Description]', quote=True)
                failed_sku_display = html.escape(failure['failed_sku'] or '[EMPTY SKU]', quote=True)
                po_num_display = html.escape(failure['po_number'] or '[N/A]', quote=True)
                warning_lines.append(f"<li>PO Number: <strong>{po_num_display}</strong>, Failed Option PN (used as INVITEM): <strong>{failed_sku_display}</strong> (Desc: {desc_display})</li>")
                unique_failures.add(failure_key)
        warning_lines.append('</ul><hr>')
        email_warning_html = "\n".join(warning_lines)

    if iif_content:
        print(f"INFO IIF_BATCH: IIF content generated for {batch_date_str}. Length: {len(iif_content)}. Failures: {len(mapping_failures)}")
        local_iif_filename = f"debug_output_ProdLogic_{batch_date_str.replace('-', '')}.iif"
        try:
            with open(local_iif_filename, "w", encoding="utf-8", newline='\r\n') as f:
                f.write(iif_content) 
            print(f"INFO IIF_BATCH: IIF content also saved locally to: {local_iif_filename}")
        except Exception as e_save:
            print(f"ERROR IIF_BATCH: Failed to save IIF content locally: {e_save}")

        if email_service:
            email_sent = email_service.send_iif_batch_email(
                iif_content_string=iif_content,
                batch_date_str=batch_date_str,
                warning_message_html=email_warning_html
            )
            if email_sent:
                print(f"SUCCESS IIF_BATCH: IIF Batch email for {batch_date_str} sent successfully.")
                if email_warning_html: 
                     print(f"INFO IIF_BATCH: Email included a warning about {len(mapping_failures)} item mapping failures.")
            else:
                print(f"ERROR IIF_BATCH: Failed to send IIF Batch email for {batch_date_str}.")
        else:
            print("ERROR IIF_BATCH: email_service not available. Cannot send email.")
    else:
        print(f"ERROR IIF_BATCH: No IIF content generated for {batch_date_str}, or a critical error occurred. Email not sent.")

if __name__ == '__main__':
    print("--- Running IIF Generator Standalone Test ---")
    from dotenv import load_dotenv
    load_dotenv()
    test_engine = engine
    connector_instance_for_cleanup = None
    if not test_engine:
        print("INFO IIF_TEST: 'engine' not imported from app. Attempting to create a new engine for testing.")
        try:
            db_user = os.getenv("DB_USER")
            db_pass = os.getenv("DB_PASS")
            db_name = os.getenv("DB_NAME")
            instance_connection_name = os.getenv("DB_CONNECTION_NAME")
            db_host = os.getenv("DB_HOST", "127.0.0.1")
            db_port = os.getenv("DB_PORT", "5432")
            if not all([db_user, db_pass, db_name]):
                 raise ValueError("Missing required DB credentials (DB_USER, DB_PASS, DB_NAME)")
            if instance_connection_name:
                print(f"INFO IIF_TEST: Using Cloud SQL Connector for instance: {instance_connection_name}")
                from google.cloud.sql.connector import Connector
                connector = Connector()
                connector_instance_for_cleanup = connector
                def getconn():
                    return connector.connect(instance_connection_name, "pg8000", user=db_user, password=db_pass, db=db_name)
                test_engine = create_engine("postgresql+pg8000://", creator=getconn, echo=False)
                print("INFO IIF_TEST: Cloud SQL Python Connector engine created for test.")
            elif db_host:
                print(f"INFO IIF_TEST: Using direct DB connection to {db_host}:{db_port}")
                db_url = f"postgresql+pg8000://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
                test_engine = create_engine(db_url, echo=False)
                print(f"INFO IIF_TEST: Direct connection engine created for test.")
            else:
                raise ValueError("Insufficient DB config: Need DB_CONNECTION_NAME (for Cloud SQL) or DB_HOST (for direct).")
        except Exception as e_engine:
            print(f"CRITICAL IIF_TEST: Failed to create test DB engine: {e_engine}")
            test_engine = None
            if connector_instance_for_cleanup:
                 try: connector_instance_for_cleanup.close()
                 except: pass
    if test_engine:
        print("INFO IIF_TEST: Database engine available. Proceeding with test execution.")
        try:
            create_and_email_daily_iif_batch(test_engine)
        finally:
            if connector_instance_for_cleanup:
                try:
                    connector_instance_for_cleanup.close()
                    print("INFO IIF_TEST: Cloud SQL Connector closed.")
                except Exception as e_close:
                    print(f"WARN IIF_TEST: Error closing Cloud SQL Connector: {e_close}")
            if test_engine and (engine is None or test_engine != engine) :
                 try:
                     test_engine.dispose()
                     print("INFO IIF_TEST: Local test engine disposed.")
                 except Exception as e_dispose:
                     print(f"WARN IIF_TEST: Error disposing local test engine: {e_dispose}")
            elif engine and test_engine == engine:
                 print("INFO IIF_TEST: Using imported engine from app.py, not disposing it here.")
    else:
        print("CRITICAL IIF_TEST: Database engine not available. Cannot run IIF generation test.")

    print("--- Finished IIF Generator Standalone Test ---")
