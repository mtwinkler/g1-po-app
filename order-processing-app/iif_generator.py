# iif_generator.py (Truly Full Version - Updated to process all pending, and for Sales Invoices & Payments, and POs)

import os
import sqlalchemy
from sqlalchemy import text, create_engine
# from sqlalchemy.orm import sessionmaker # Not strictly needed for this file's current usage
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

# --- QuickBooks Specific Configuration for POs ---
QUICKBOOKS_PO_ACCOUNT = "Purchase Orders"
QUICKBOOKS_DEFAULT_EXPENSE_ACCOUNT = "Cost of Goods Sold" # For PO line items

# --- QuickBooks Specific Configuration for Sales/Invoices/Payments ---
QUICKBOOKS_ACCOUNTS_RECEIVABLE = "Accounts Receivable"
QUICKBOOKS_UNDEPOSITED_FUNDS = "Undeposited Funds"
QUICKBOOKS_SALES_INCOME_MERCHANDISE = "Sales:Merchandise"  # Default income account for mapped sales items
QUICKBOOKS_SALES_INCOME_SHIPPING = "Sales:Shipping and Handling" # Income account for shipping item
QUICKBOOKS_OTHER_INCOME_FOR_SALES_TAX_ITEM = "Other Income" # Account linked to the "Sales Tax" service item

QUICKBOOKS_TERMS_DEFAULT_PREPAY = "Prepay-Credit Card" # Default terms for website orders
QUICKBOOKS_CUSTOMER_WEBSITE = "G1.com Website Customer" # Generic customer for all website orders

# Item Names (for INVITEM field in IIF)
QUICKBOOKS_ITEM_SHIPPING_CHARGES = "Freight Collected" # QB Item Name for shipping charges
QUICKBOOKS_ITEM_SALES_TAX = "Sales Tax" # QB Item Name for sales tax collected

# --- QB Item Name Lookup Function (used by both PO and Sales) ---
def get_qb_item_name_for_option_pn(conn, option_pn_from_po_or_sale):
    if not option_pn_from_po_or_sale:
        print(f"WARN IIF_GEN_MAP: Received empty or None Option PN for INVITEM.")
        return "", False

    original_sku_for_reporting = str(option_pn_from_po_or_sale) # For consistent reporting if lookup fails
    sku_to_lookup = original_sku_for_reporting

    sql_mapping_query = text("SELECT qb_item_name FROM qb_product_mapping WHERE option_pn = :option_pn;")
    
    try:
        # Attempt 1: Direct lookup with the provided SKU
        mapping_result = conn.execute(sql_mapping_query, {"option_pn": sku_to_lookup}).fetchone()
        if mapping_result and mapping_result.qb_item_name:
            qb_item_name = mapping_result.qb_item_name
            print(f"DEBUG IIF_GEN_MAP: Found QB mapping for Option PN '{sku_to_lookup}': INVITEM='{qb_item_name}'")
            return qb_item_name, True
        
        # Attempt 2: If direct lookup fails and SKU contains an underscore, try the part after the last underscore
        if '_' in sku_to_lookup:
            sku_after_underscore = sku_to_lookup.split('_')[-1]
            if sku_after_underscore and sku_after_underscore != sku_to_lookup: # Ensure there's something after '_' and it's different
                print(f"DEBUG IIF_GEN_MAP: Direct lookup failed for '{sku_to_lookup}'. Trying fallback with SKU part after underscore: '{sku_after_underscore}'")
                fallback_result = conn.execute(sql_mapping_query, {"option_pn": sku_after_underscore}).fetchone()
                if fallback_result and fallback_result.qb_item_name:
                    qb_item_name = fallback_result.qb_item_name
                    print(f"DEBUG IIF_GEN_MAP: Found QB mapping for fallback SKU '{sku_after_underscore}': INVITEM='{qb_item_name}' (Original Full SKU: '{original_sku_for_reporting}')")
                    return qb_item_name, True
                else:
                    # Fallback also failed
                    print(f"WARN IIF_GEN_MAP: No QuickBooks mapping found for original SKU '{original_sku_for_reporting}' or fallback SKU '{sku_after_underscore}'. Using original full SKU as INVITEM.")
                    return original_sku_for_reporting, False
            else:
                # Underscore present, but no valid part after it, or it's the same as the original
                 print(f"WARN IIF_GEN_MAP: No QuickBooks mapping found for Option PN '{original_sku_for_reporting}'. Fallback part after underscore was invalid or same. Using original full SKU as INVITEM.")
                 return original_sku_for_reporting, False
        else:
            # No underscore, and direct lookup failed
            print(f"WARN IIF_GEN_MAP: No QuickBooks mapping found for Option PN '{original_sku_for_reporting}'. Using original full SKU as INVITEM.")
            return original_sku_for_reporting, False
            
    except sqlalchemy.exc.SQLAlchemyError as db_err:
         print(f"ERROR IIF_GEN_MAP: Database error looking up Option PN '{original_sku_for_reporting}': {db_err}")
         return original_sku_for_reporting, False # Return original full SKU on DB error
    except Exception as e:
        print(f"ERROR IIF_GEN_MAP: Unexpected error looking up Option PN '{original_sku_for_reporting}': {e}")
        traceback.print_exc()
        return original_sku_for_reporting, False # Return original full SKU on other errors

def sanitize_field(value, max_length=None):
    """Sanitizes a field value for IIF output."""
    if value is None:
        return ""
    s_value = str(value).strip()

    s_value = s_value.replace('\t', ' ')
    s_value = s_value.replace('\r\n', ' ') 
    s_value = s_value.replace('\n', ' ')   
    s_value = s_value.replace('\r', ' ')   
    s_value = s_value.replace('"', 'in')

    if max_length and len(s_value) > max_length:
        original_value_preview = str(value)[:30] + "..." if len(str(value)) > 30 else str(value)
        s_value = s_value[:max_length]
        print(f"WARN IIF_GEN: Truncated field content to {max_length} chars. Original: '{original_value_preview}', Truncated: '{s_value}'")
    return s_value

def strip_supplier_contact(supplier_name_full):
    if supplier_name_full is None: return ""
    match = re.search(r'^(.*?)\s*\([^)]*\)$', supplier_name_full)
    return match.group(1).strip() if match else supplier_name_full


# --- IIF Generation for Purchase Orders ---
def generate_po_iif_content_for_date(db_engine_ref, target_date_str=None, process_all_pending=False):
    iif_lines = []
    po_mapping_failures = []
    processed_po_db_ids = [] 

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

    target_date = None
    if not process_all_pending:
        if not target_date_str: print("CRITICAL IIF_PO_GEN: target_date_str is required."); return None, [], []
        try: target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError: print(f"CRITICAL IIF_PO_GEN: Invalid target_date_str: {target_date_str}."); return None, [], []
    conn = None
    try:
        if not db_engine_ref: print("CRITICAL IIF_PO_GEN: DB engine not available."); return None, [], []
        conn = db_engine_ref.connect()
        log_message_date_part = f"POs for {target_date_str}" if target_date and not process_all_pending else "all pending POs"
        print(f"INFO IIF_PO_GEN: Connected to DB to fetch {log_message_date_part}")

        base_sql = """
            SELECT
                po.id as po_id, po.po_number, po.po_date,
                po.payment_instructions as payment_instructions,
                s.name as supplier_name_full,
                po.total_amount,
                o.customer_name, o.customer_shipping_address_line1, o.customer_shipping_address_line2,
                o.customer_shipping_city, o.customer_shipping_state, o.customer_shipping_zip,
                o.customer_shipping_country, o.customer_shipping_country_iso2, 
                o.bigcommerce_order_id
            FROM purchase_orders po
            JOIN suppliers s ON po.supplier_id = s.id
            JOIN orders o ON po.order_id = o.id
            WHERE po.status = 'SENT_TO_SUPPLIER'
              AND (po.qb_po_sync_status IS NULL OR po.qb_po_sync_status IN ('pending_sync', 'error'))
        """
        query_params = {}
        if not process_all_pending and target_date:
            base_sql += " AND DATE(po.po_date AT TIME ZONE 'UTC') = :target_date"
            query_params["target_date"] = target_date
        base_sql += " ORDER BY po.po_date, po.id;"

        sql_data_query = text(base_sql)
        purchase_orders_data = conn.execute(sql_data_query, query_params).fetchall()
        print(f"INFO IIF_PO_GEN: Found {len(purchase_orders_data)} eligible Purchase Orders matching criteria.")

        if not purchase_orders_data:
            empty_iif_trns_line = "TRNS\t" + "\t".join([""] * len(trns_header_fields))
            empty_iif_spl_line = "SPL\t" + "\t".join([""] * len(spl_header_fields))
            iif_lines.extend([empty_iif_trns_line, empty_iif_spl_line, "ENDTRNS"])
            return "\r\n".join(iif_lines) + "\r\n", [], []

        for po_row in purchase_orders_data:
            if po_row.po_date is None:
                print(f"WARN IIF_PO_GEN: PO Number {po_row.po_number} has no po_date. Skipping this PO.")
                continue
            po_date_formatted = po_row.po_date.strftime("%m/%d/%Y")
            po_total_cost = Decimal(po_row.total_amount if po_row.total_amount is not None else '0.00')
            iif_supplier_name = strip_supplier_contact(po_row.supplier_name_full)

            s_lines = []
            cust_company = getattr(po_row, 'customer_company', None) # Get company from order if available (not directly on PO)
            cust_name_po = getattr(po_row, 'customer_name', None)
            if cust_company: s_lines.append(cust_company)
            if cust_name_po: s_lines.append(cust_name_po)
            
            s_street1 = getattr(po_row, 'customer_shipping_address_line1', None)
            if s_street1: s_lines.append(s_street1)
            s_street2 = getattr(po_row, 'customer_shipping_address_line2', None)
            if s_street2: s_lines.append(s_street2)

            s_city = getattr(po_row, 'customer_shipping_city', None)
            s_state_raw = getattr(po_row, 'customer_shipping_state', None)
            s_country_iso_po = getattr(po_row, 'customer_shipping_country_iso2', "").upper() # from orders table
            s_country_full_po = getattr(po_row, 'customer_shipping_country', None) # from orders table
            s_zip = getattr(po_row, 'customer_shipping_zip', None)
            s_state_proc = get_us_state_abbreviation(s_state_raw, s_country_iso_po)

            s_city_state_zip_parts = []
            if s_city: s_city_state_zip_parts.append(s_city + ",")
            if s_state_proc: s_city_state_zip_parts.append(s_state_proc)
            if s_zip: s_city_state_zip_parts.append(s_zip)
            s_city_state_zip = " ".join(filter(None, s_city_state_zip_parts)).strip()
            if s_city_state_zip: s_lines.append(s_city_state_zip)

            is_us_shipping_po = s_country_iso_po == "US"
            if not is_us_shipping_po and s_country_full_po:
                 s_lines.append(s_country_full_po)

            saddr1 = sanitize_field(s_lines[0] if len(s_lines) > 0 else "", 41)
            saddr2 = sanitize_field(s_lines[1] if len(s_lines) > 1 else "", 41)
            saddr3 = sanitize_field(s_lines[2] if len(s_lines) > 2 else "", 41)
            saddr4 = sanitize_field(s_lines[3] if len(s_lines) > 3 else "", 41)
            saddr5 = sanitize_field(s_lines[4] if len(s_lines) > 4 else "", 41)


            trns_values_dict = {
                "TRNSID": "", "TRNSTYPE": "PURCHORD", "DATE": po_date_formatted,
                "ACCNT": QUICKBOOKS_PO_ACCOUNT, "NAME": iif_supplier_name,
                "CLASS": "", "AMOUNT": str(po_total_cost * -1), 
                "DOCNUM": po_row.po_number, "MEMO": f"PO {po_row.po_number}",
                "CLEAR": "N", "TOPRINT": "Y", "NAMEISTAXABLE": "N",
                "ADDR1": "", "ADDR2": "", "ADDR3": "", "ADDR4": "", "ADDR5": "", 
                "DUEDATE": po_date_formatted, "TERMS": "", "PAID": "N", "PAYMETH": "",
                "SHIPVIA": "", "SHIPDATE": po_date_formatted, 
                "OTHER1": "", "REP": "", "FOB": "", "PONUM": po_row.po_number,
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
                print(f"WARN IIF_PO_GEN: No line items found for PO ID {po_row.po_id} (PO Number: {po_row.po_number}).")

            for item_row in line_items:
                sku_to_lookup = item_row.item_sku
                qb_invitem_name, mapping_found = get_qb_item_name_for_option_pn(conn, sku_to_lookup)
                if not mapping_found:
                    po_mapping_failures.append({
                        "po_number": po_row.po_number,
                        "failed_sku": sku_to_lookup if sku_to_lookup else "[EMPTY SKU]",
                        "description": item_row.item_description
                    })
                unit_cost = Decimal(item_row.unit_cost if item_row.unit_cost is not None else 0)
                quantity = Decimal(item_row.quantity if item_row.quantity is not None else 0)
                line_total_cost = unit_cost * quantity
                item_description_content = sanitize_field(item_row.item_description if item_row.item_description else "Item", 4095)

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

            if po_row.payment_instructions:
                memo_spl_values_dict = { "TRNSTYPE": "PURCHORD", "DATE": po_date_formatted, "ACCNT": QUICKBOOKS_DEFAULT_EXPENSE_ACCOUNT, "AMOUNT": "0.00", "DOCNUM": po_row.po_number, "MEMO": sanitize_field(po_row.payment_instructions, 4095)}
                memo_spl_data_ordered = [sanitize_field(memo_spl_values_dict.get(field, "")) for field in spl_header_fields]
                iif_lines.append("SPL\t" + "\t".join(memo_spl_data_ordered))

            if po_row.bigcommerce_order_id:
                fulfillment_note = f"Fulfillment of G1 Order #{po_row.bigcommerce_order_id}"
                fulfillment_spl_values_dict = { "TRNSTYPE": "PURCHORD", "DATE": po_date_formatted, "ACCNT": QUICKBOOKS_DEFAULT_EXPENSE_ACCOUNT, "AMOUNT": "0.00", "DOCNUM": po_row.po_number, "MEMO": sanitize_field(fulfillment_note, 4095)}
                fulfillment_spl_data_ordered = [sanitize_field(fulfillment_spl_values_dict.get(field, "")) for field in spl_header_fields]
                iif_lines.append("SPL\t" + "\t".join(fulfillment_spl_data_ordered))

            iif_lines.append("ENDTRNS")
            processed_po_db_ids.append(po_row.po_id) 

        print(f"INFO IIF_PO_GEN: Finished generating PO IIF content. Processed IDs: {len(processed_po_db_ids)}. Failures: {len(po_mapping_failures)}.")
        return "\r\n".join(iif_lines) + "\r\n", po_mapping_failures, processed_po_db_ids

    except sqlalchemy.exc.SQLAlchemyError as db_e:
        print(f"CRITICAL IIF_PO_GEN: Database error: {db_e}")
        traceback.print_exc()
        return None, po_mapping_failures, [] 
    except Exception as e:
        print(f"CRITICAL IIF_PO_GEN: Unexpected error: {e}")
        traceback.print_exc()
        return None, po_mapping_failures, [] 
    finally:
        if conn: conn.close()

# --- Add US State Abbreviation Mapping ---
US_STATE_ABBREVIATIONS = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL",
    "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN",
    "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
    "puerto rico": "PR"
}

def get_us_state_abbreviation(state_name_full, country_name_or_iso):
    if not state_name_full or not country_name_or_iso:
        return state_name_full 

    country_lower = str(country_name_or_iso).lower()
    is_us_country = country_lower in ["us", "usa", "united states", "united states of america"]

    if is_us_country:
        return US_STATE_ABBREVIATIONS.get(str(state_name_full).lower().strip(), str(state_name_full).strip()) 
    return str(state_name_full).strip() 

# --- IIF Generation for Sales Invoices & Payments ---
def generate_sales_iif_content_for_date(db_engine_ref, target_date_str=None, process_all_pending=False):
    iif_lines, sales_item_mapping_failures = [], []
    processed_sales_order_db_ids = [] 
    trns_header_fields = ["TRNSID", "TRNSTYPE", "DATE", "ACCNT", "NAME", "CLASS", "AMOUNT", "DOCNUM", "MEMO", "CLEAR", "TOPRINT", "NAMEISTAXABLE", "ADDR1", "ADDR2", "ADDR3", "ADDR4", "ADDR5", "DUEDATE", "TERMS", "PAID", "PAYMETH", "SHIPVIA", "SHIPDATE", "OTHER1", "REP", "FOB", "PONUM", "INVTITLE", "INVMEMO", "SADDR1", "SADDR2", "SADDR3", "SADDR4", "SADDR5"]
    spl_header_fields = ["SPLID", "TRNSTYPE", "DATE", "ACCNT", "NAME", "CLASS", "AMOUNT", "DOCNUM", "MEMO", "CLEAR", "QNTY", "PRICE", "INVITEM", "PAYMETH", "TAXABLE", "VALADJ", "REIMBEXP", "SERVICEDATE", "OTHER2", "OTHER3", "PAYITEM", "YEARTODATE", "WAGEBASE", "EXTRA"]
    iif_lines.extend(["!TRNS\t" + "\t".join(trns_header_fields), "!SPL\t" + "\t".join(spl_header_fields), "!ENDTRNS"])

    target_date = None
    if not process_all_pending:
        if not target_date_str: print("CRITICAL IIF_SALES_GEN: target_date_str required."); return None, [], []
        try: target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError: print(f"CRITICAL IIF_SALES_GEN: Invalid target_date_str: {target_date_str}."); return None, [], []
    conn = None
    try:
        if not db_engine_ref: print("CRITICAL IIF_SALES_GEN: DB engine not available."); return None, [], []
        conn = db_engine_ref.connect()
        log_message_date_part = f"Sales Orders for {target_date_str}" if target_date and not process_all_pending else "all pending Sales Orders"
        print(f"INFO IIF_SALES_GEN: Connected to DB to fetch {log_message_date_part}")

        base_sql = """
            SELECT
                o.id as app_order_id, o.bigcommerce_order_id, o.order_date,
                o.total_sale_price, o.bigcommerce_order_tax, o.bc_shipping_cost_ex_tax AS customer_shipping_cost,
                o.payment_method, o.customer_shipping_method,
                o.customer_name, o.customer_company,
                o.customer_shipping_address_line1, o.customer_shipping_address_line2,
                o.customer_shipping_city, o.customer_shipping_state,
                o.customer_shipping_zip, o.customer_shipping_country, o.customer_shipping_country_iso2,
                o.customer_billing_first_name, o.customer_billing_last_name, o.customer_billing_company,
                o.customer_billing_street_1, o.customer_billing_street_2,
                o.customer_billing_city, o.customer_billing_state,
                o.customer_billing_zip, o.customer_billing_country, o.customer_billing_country_iso2
            FROM orders o
            WHERE (o.qb_sales_order_sync_status IS NULL OR o.qb_sales_order_sync_status IN ('pending_sync', 'error'))
        """
        query_params = {}
        if not process_all_pending and target_date:
            base_sql += " AND DATE(o.order_date AT TIME ZONE 'UTC') = :target_date"
            query_params["target_date"] = target_date
        base_sql += " ORDER BY o.order_date, o.id;"

        sql_sales_orders_query = text(base_sql)
        sales_orders_data = conn.execute(sql_sales_orders_query, query_params).fetchall()
        print(f"INFO IIF_SALES_GEN: Found {len(sales_orders_data)} eligible Sales Orders matching criteria.")

        if not sales_orders_data:
            empty_iif_trns_line = "TRNS\t" + "\t".join([""] * len(trns_header_fields))
            empty_iif_spl_line = "SPL\t" + "\t".join([""] * len(spl_header_fields))
            iif_lines.extend([empty_iif_trns_line, empty_iif_spl_line, "ENDTRNS"])
            return "\r\n".join(iif_lines) + "\r\n", [], []

        for order_row in sales_orders_data:
            order_date_formatted = order_row.order_date.strftime("%m/%d/%Y") if order_row.order_date else datetime.now(timezone.utc).strftime("%m/%d/%Y")
            bc_order_id_str = str(order_row.bigcommerce_order_id)
            invoice_total_amount = Decimal(order_row.total_sale_price if order_row.total_sale_price is not None else '0.00')

            _bill_lines = []
            bill_comp = getattr(order_row, 'customer_billing_company', None)
            bill_first = getattr(order_row, 'customer_billing_first_name', None)
            bill_last = getattr(order_row, 'customer_billing_last_name', None)
            bill_name_line = ""
            if bill_first and bill_last: bill_name_line = f"{bill_first} {bill_last}"
            elif bill_first: bill_name_line = bill_first
            elif bill_last: bill_name_line = bill_last

            if bill_comp: _bill_lines.append(bill_comp)
            if bill_name_line: _bill_lines.append(bill_name_line)
            
            bill_street1 = getattr(order_row, 'customer_billing_street_1', None)
            if bill_street1: _bill_lines.append(bill_street1)
            bill_street2 = getattr(order_row, 'customer_billing_street_2', None)
            if bill_street2: _bill_lines.append(bill_street2)
            
            bill_city = getattr(order_row, 'customer_billing_city', None)
            bill_state_raw = getattr(order_row, 'customer_billing_state', None)
            bill_country_iso = getattr(order_row, 'customer_billing_country_iso2', "").upper()
            bill_country_full = getattr(order_row, 'customer_billing_country', None)
            bill_zip = getattr(order_row, 'customer_billing_zip', None)
            bill_state_proc = get_us_state_abbreviation(bill_state_raw, bill_country_iso)

            city_state_zip_line_bill_parts = []
            if bill_city: city_state_zip_line_bill_parts.append(bill_city + ",")
            if bill_state_proc: city_state_zip_line_bill_parts.append(bill_state_proc)
            if bill_zip: city_state_zip_line_bill_parts.append(bill_zip)
            city_state_zip_line_bill = " ".join(filter(None, city_state_zip_line_bill_parts)).strip()
            if city_state_zip_line_bill: _bill_lines.append(city_state_zip_line_bill)
            
            is_us_billing = bill_country_iso == "US"
            if not is_us_billing and bill_country_full:
                _bill_lines.append(bill_country_full)
            
            addr1_inv = sanitize_field(_bill_lines[0] if len(_bill_lines) > 0 else QUICKBOOKS_CUSTOMER_WEBSITE, 41)
            addr2_inv = sanitize_field(_bill_lines[1] if len(_bill_lines) > 1 else "", 41)
            addr3_inv = sanitize_field(_bill_lines[2] if len(_bill_lines) > 2 else "", 41)
            addr4_inv = sanitize_field(_bill_lines[3] if len(_bill_lines) > 3 else "", 41)
            addr5_inv = sanitize_field(_bill_lines[4] if len(_bill_lines) > 4 else "", 41)

            _ship_lines = []
            ship_comp = order_row.customer_company 
            ship_name = order_row.customer_name 

            if ship_comp: _ship_lines.append(ship_comp)
            if ship_name: _ship_lines.append(ship_name) 

            ship_street1 = order_row.customer_shipping_address_line1
            if ship_street1: _ship_lines.append(ship_street1)
            ship_street2 = order_row.customer_shipping_address_line2
            if ship_street2: _ship_lines.append(ship_street2)

            ship_city = order_row.customer_shipping_city
            ship_state_raw = order_row.customer_shipping_state
            ship_country_iso = getattr(order_row, 'customer_shipping_country_iso2', "").upper()
            ship_country_full = order_row.customer_shipping_country
            ship_zip = order_row.customer_shipping_zip
            ship_state_proc = get_us_state_abbreviation(ship_state_raw, ship_country_iso)
            
            city_state_zip_line_ship_parts = []
            if ship_city: city_state_zip_line_ship_parts.append(ship_city + ",")
            if ship_state_proc: city_state_zip_line_ship_parts.append(ship_state_proc)
            if ship_zip: city_state_zip_line_ship_parts.append(ship_zip)
            city_state_zip_line_ship = " ".join(filter(None, city_state_zip_line_ship_parts)).strip()
            if city_state_zip_line_ship: _ship_lines.append(city_state_zip_line_ship)
            
            is_us_shipping = ship_country_iso == "US"
            if not is_us_shipping and ship_country_full:
                _ship_lines.append(ship_country_full)

            saddr1_inv = sanitize_field(_ship_lines[0] if len(_ship_lines) > 0 else "", 41)
            saddr2_inv = sanitize_field(_ship_lines[1] if len(_ship_lines) > 1 else "", 41)
            saddr3_inv = sanitize_field(_ship_lines[2] if len(_ship_lines) > 2 else "", 41)
            saddr4_inv = sanitize_field(_ship_lines[3] if len(_ship_lines) > 3 else "", 41)
            saddr5_inv = sanitize_field(_ship_lines[4] if len(_ship_lines) > 4 else "", 41)

            terms_from_order = getattr(order_row, 'customer_payment_terms', None)
            terms_for_invoice = sanitize_field(terms_from_order or QUICKBOOKS_TERMS_DEFAULT_PREPAY, 20)
            customer_po_num_from_order = getattr(order_row, 'customer_po_number', None)

            invoice_trns_dict = {
                "TRNSTYPE": "INVOICE", "DATE": order_date_formatted,
                "ACCNT": QUICKBOOKS_ACCOUNTS_RECEIVABLE, "NAME": QUICKBOOKS_CUSTOMER_WEBSITE,
                "AMOUNT": str(invoice_total_amount), "DOCNUM": bc_order_id_str,
                "TERMS": terms_for_invoice,
                "ADDR1": addr1_inv, "ADDR2": addr2_inv, "ADDR3": addr3_inv, "ADDR4": addr4_inv, "ADDR5": addr5_inv,
                "SADDR1": saddr1_inv, "SADDR2": saddr2_inv, "SADDR3": saddr3_inv, "SADDR4": saddr4_inv, "SADDR5": saddr5_inv,
                "MEMO": f"Order #{bc_order_id_str}", "TOPRINT": "Y", "PAID": "Y",
                "SHIPDATE": order_date_formatted,
                "PONUM": sanitize_field(customer_po_num_from_order, 25)
            }
            trns_data_ordered = [sanitize_field(invoice_trns_dict.get(field, "")) for field in trns_header_fields]
            iif_lines.append("TRNS\t" + "\t".join(trns_data_ordered))

            sql_line_items_query = text("""
                SELECT oli.sku, oli.name as product_name, oli.quantity, oli.sale_price
                FROM order_line_items oli WHERE oli.order_id = :app_order_id;
            """)
            line_items_data = conn.execute(sql_line_items_query, {"app_order_id": order_row.app_order_id}).fetchall()

            for item_row in line_items_data:
                original_bc_sku = item_row.sku
                option_pn_for_item = None
                item_description_for_iif = sanitize_field(item_row.product_name, 4095)
                sql_hpe_map = text("SELECT option_pn FROM hpe_part_mappings WHERE sku = :sku_val;")
                hpe_res = conn.execute(sql_hpe_map, {"sku_val": original_bc_sku}).fetchone()
                if hpe_res and hpe_res.option_pn:
                    option_pn_for_item = hpe_res.option_pn
                    sql_desc_map = text("SELECT po_description FROM hpe_description_mappings WHERE option_pn = :option_pn_val;")
                    desc_res = conn.execute(sql_desc_map, {"option_pn_val": option_pn_for_item}).scalar_one_or_none()
                    if desc_res: item_description_for_iif = sanitize_field(desc_res, 4095)
                else:
                    # If no HPE mapping, use original SKU as the basis for QB item lookup
                    option_pn_for_item = original_bc_sku 
                    # No failure logged here for HPE mapping missing, as per existing logic.
                    # The failure will be logged if the subsequent qb_product_mapping lookup fails.

                qb_invitem_name, mapping_found = get_qb_item_name_for_option_pn(conn, option_pn_for_item)
                if not mapping_found: 
                    sales_item_mapping_failures.append({
                        "bc_order_id": bc_order_id_str, 
                        "failed_step": "OptionPN_to_QBItem", 
                        "original_sku": original_bc_sku, # Report the very original SKU from BC
                        "option_pn": option_pn_for_item, # Report the SKU used for QB lookup (could be original_bc_sku or HPE mapped)
                        "product_name": item_row.product_name
                    })

                item_quantity = Decimal(item_row.quantity if item_row.quantity is not None else 0)
                item_sale_price = Decimal(item_row.sale_price if item_row.sale_price is not None else 0)
                item_line_total = item_quantity * item_sale_price
                item_spl_dict = {"TRNSTYPE": "INVOICE", "DATE": order_date_formatted, "ACCNT": QUICKBOOKS_SALES_INCOME_MERCHANDISE, "INVITEM": qb_invitem_name, "QNTY": str(item_quantity), "PRICE": str(item_sale_price), "AMOUNT": str(item_line_total * -1), "MEMO": item_description_for_iif, "DOCNUM": bc_order_id_str, "NAME": QUICKBOOKS_CUSTOMER_WEBSITE, "TAXABLE": "N"}
                spl_data_ordered = [sanitize_field(item_spl_dict.get(field, "")) for field in spl_header_fields]
                iif_lines.append("SPL\t" + "\t".join(spl_data_ordered))

            shipping_memo = "Shipping Charges"
            order_shipping_method_raw = getattr(order_row, 'customer_shipping_method', "")
            if order_shipping_method_raw:
                shipping_method_to_use = order_shipping_method_raw
                match = re.search(r'\(([^)]+)\)$', order_shipping_method_raw.strip())
                if match: shipping_method_to_use = match.group(1).strip()
                if "free shipping" in shipping_method_to_use.lower(): shipping_memo = "UPS Ground"
                else: shipping_memo = sanitize_field(shipping_method_to_use, 4095)
            shipping_cost = Decimal(order_row.customer_shipping_cost if order_row.customer_shipping_cost is not None else '0.00')
            if shipping_cost > 0:
                shipping_spl_dict = {"TRNSTYPE": "INVOICE", "DATE": order_date_formatted, "ACCNT": QUICKBOOKS_SALES_INCOME_SHIPPING, "INVITEM": QUICKBOOKS_ITEM_SHIPPING_CHARGES, "AMOUNT": str(shipping_cost * -1), "MEMO": shipping_memo, "DOCNUM": bc_order_id_str, "NAME": QUICKBOOKS_CUSTOMER_WEBSITE, "TAXABLE": "N"}
                spl_data_ordered = [sanitize_field(shipping_spl_dict.get(field, "")) for field in spl_header_fields]
                iif_lines.append("SPL\t" + "\t".join(spl_data_ordered))

            tax_amount = Decimal(order_row.bigcommerce_order_tax if order_row.bigcommerce_order_tax is not None else '0.00')
            if tax_amount > 0:
                tax_spl_dict = {"TRNSTYPE": "INVOICE", "DATE": order_date_formatted, "ACCNT": QUICKBOOKS_OTHER_INCOME_FOR_SALES_TAX_ITEM, "INVITEM": QUICKBOOKS_ITEM_SALES_TAX, "AMOUNT": str(tax_amount * -1), "MEMO": "", "DOCNUM": bc_order_id_str, "NAME": QUICKBOOKS_CUSTOMER_WEBSITE, "TAXABLE": "N"}
                spl_data_ordered = [sanitize_field(tax_spl_dict.get(field, "")) for field in spl_header_fields]
                iif_lines.append("SPL\t" + "\t".join(spl_data_ordered))
            iif_lines.append("ENDTRNS")

            payment_amount = invoice_total_amount
            iif_payment_method = "Credit Card"
            payment_trns_dict = {"TRNSTYPE": "PAYMENT", "DATE": order_date_formatted, "ACCNT": QUICKBOOKS_UNDEPOSITED_FUNDS, "NAME": QUICKBOOKS_CUSTOMER_WEBSITE, "AMOUNT": str(payment_amount), "DOCNUM": bc_order_id_str, "PAYMETH": iif_payment_method, "MEMO": f"Payment for Order #{bc_order_id_str}"}
            trns_data_ordered = [sanitize_field(payment_trns_dict.get(field, "")) for field in trns_header_fields]
            iif_lines.append("TRNS\t" + "\t".join(trns_data_ordered))
            payment_spl_dict = {"TRNSTYPE": "PAYMENT", "DATE": order_date_formatted, "ACCNT": QUICKBOOKS_ACCOUNTS_RECEIVABLE, "NAME": QUICKBOOKS_CUSTOMER_WEBSITE, "AMOUNT": str(payment_amount * -1), "DOCNUM": bc_order_id_str, "MEMO": f"Applied to Invoice #{bc_order_id_str}"}
            spl_data_ordered = [sanitize_field(payment_spl_dict.get(field, "")) for field in spl_header_fields]
            iif_lines.append("SPL\t" + "\t".join(spl_data_ordered))
            iif_lines.append("ENDTRNS")

            processed_sales_order_db_ids.append(order_row.app_order_id) 

        print(f"INFO IIF_SALES_GEN: Finished Sales IIF. Processed IDs: {len(processed_sales_order_db_ids)}. Failures: {len(sales_item_mapping_failures)}.")
        return "\r\n".join(iif_lines) + "\r\n", sales_item_mapping_failures, processed_sales_order_db_ids

    except sqlalchemy.exc.SQLAlchemyError as db_e:
        print(f"CRITICAL IIF_SALES_GEN: DB error: {db_e}"); traceback.print_exc()
        return None, sales_item_mapping_failures, [] 
    except Exception as e:
        print(f"CRITICAL IIF_SALES_GEN: Unexpected error: {e}"); traceback.print_exc()
        return None, sales_item_mapping_failures, [] 
    finally:
        if conn: conn.close()
        print(f"INFO IIF_SALES_GEN: DB connection closed for {log_message_date_part}")


# --- Top-Level Functions for POs ---
def create_and_email_daily_iif_batch(db_engine_ref): # Renamed to be more generic, as it's called by the scheduler for POs
    # This function specifically targets POs from yesterday for the daily scheduled task
    target_date_for_production = datetime.now(timezone.utc).date() - timedelta(days=1)
    batch_date_str = target_date_for_production.strftime("%Y-%m-%d")
    print(f"INFO IIF_PO_BATCH (Daily POs): Generating PO IIF for date: {batch_date_str}")
    
    iif_content, mapping_failures, processed_ids = generate_po_iif_content_for_date(
        db_engine_ref, 
        target_date_str=batch_date_str, 
        process_all_pending=False # Explicitly ensure it's for a specific date
    )
    
    email_warning_html = None
    if mapping_failures:
        warning_lines = ['<p><strong><span style="color: red; font-size: 1.2em;">WARNING: QuickBooks Item Mapping Failures (Daily Purchase Orders)</span></strong></p>', '<p>Review `qb_product_mapping` or add items in QuickBooks:</p><ul>']
        unique_failures = set(); [warning_lines.append(f"<li>PO: <strong>{html.escape(f['po_number'])}</strong>, Failed SKU (used as INVITEM): <strong>{html.escape(f['failed_sku'])}</strong> (Desc: {html.escape(f['description'] or '')})</li>") for f in mapping_failures if (f['po_number'], f['failed_sku']) not in unique_failures and unique_failures.add((f['po_number'], f['failed_sku'])) is None]
        warning_lines.append('</ul><hr>'); email_warning_html = "\n".join(warning_lines)
    
    if iif_content and processed_ids: # Only email if there was actual content with processed items
        if email_service:
            email_sent = email_service.send_iif_batch_email(
                iif_content_string=iif_content, 
                batch_date_str=batch_date_str, 
                warning_message_html=email_warning_html, 
                filename_prefix="PurchaseOrders_Daily_"
            )
            print(f"IIF_PO_BATCH (Daily POs): Email for {batch_date_str} {'sent' if email_sent else 'failed'}.")
            # Update database status for processed POs
            try:
                with db_engine_ref.connect() as conn_update:
                    with conn_update.begin():
                        update_stmt = text("UPDATE purchase_orders SET qb_po_sync_status = 'synced', qb_po_synced_at = :now, qb_po_last_error = NULL WHERE id = ANY(:ids)")
                        conn_update.execute(update_stmt, {"now": datetime.now(timezone.utc), "ids": processed_ids})
                        print(f"INFO IIF_PO_BATCH (Daily POs): Updated sync status for {len(processed_ids)} POs in database.")
            except Exception as e_db:
                print(f"ERROR IIF_PO_BATCH (Daily POs): Failed to update DB status for POs {processed_ids}: {e_db}")
                traceback.print_exc()
        else:
            print(f"WARN IIF_PO_BATCH (Daily POs): Email service not available. IIF for {batch_date_str} generated but not sent. DB status NOT updated.")
    elif not iif_content: 
        print(f"INFO IIF_PO_BATCH (Daily POs): No PO IIF content generated for {batch_date_str} (no new POs or error).")
    elif iif_content and not processed_ids:
         print(f"INFO IIF_PO_BATCH (Daily POs): IIF content generated for {batch_date_str} but no POs were actually processed (e.g. only header/footer). No email sent, no DB update.")


def create_and_email_iif_for_today(db_engine_ref): # Renamed for clarity - For POs from today by user
    target_date_for_today = datetime.now(timezone.utc).date()
    batch_date_str = target_date_for_today.strftime("%Y-%m-%d")
    print(f"INFO IIF_PO_BATCH (Today's POs - User): Generating PO IIF for date: {batch_date_str}")
    
    iif_content, mapping_failures, processed_ids = generate_po_iif_content_for_date(
        db_engine_ref, 
        target_date_str=batch_date_str, 
        process_all_pending=False # For today's date specifically
    )
    
    email_warning_html = None
    if mapping_failures: 
        warning_lines_today = ['<p><strong><span style="color: red; font-size: 1.2em;">WARNING: QuickBooks Item Mapping Failures (Today\'s Purchase Orders)</span></strong></p><ul>']
        # ... (similar formatting for failures as daily batch) ...
        unique_failures_today = set()
        for f_today in mapping_failures:
            key_today = (f_today['po_number'], f_today['failed_sku'])
            if key_today not in unique_failures_today:
                warning_lines_today.append(f"<li>PO: {html.escape(f_today['po_number'])}, SKU: {html.escape(f_today['failed_sku'])}</li>")
                unique_failures_today.add(key_today)
        warning_lines_today.append("</ul>")
        email_warning_html = "\n".join(warning_lines_today)

    if iif_content and processed_ids:
        if email_service:
            email_subject = f"Today's Purchase Orders IIF Batch - {batch_date_str}"
            email_sent = email_service.send_iif_batch_email( 
                iif_content_string=iif_content, 
                batch_date_str=batch_date_str, 
                warning_message_html=email_warning_html, 
                custom_subject=email_subject, 
                filename_prefix="PurchaseOrders_Today_"
            )
            print(f"IIF_PO_BATCH (Today's POs - User): Email {'sent' if email_sent else 'failed'}.")
            # Update database status for processed POs
            try:
                with db_engine_ref.connect() as conn_update_today:
                    with conn_update_today.begin():
                        update_stmt_today = text("UPDATE purchase_orders SET qb_po_sync_status = 'synced', qb_po_synced_at = :now, qb_po_last_error = NULL WHERE id = ANY(:ids)")
                        conn_update_today.execute(update_stmt_today, {"now": datetime.now(timezone.utc), "ids": processed_ids})
                        print(f"INFO IIF_PO_BATCH (Today's POs - User): Updated sync status for {len(processed_ids)} POs in database.")
            except Exception as e_db_today:
                print(f"ERROR IIF_PO_BATCH (Today's POs - User): Failed to update DB status for POs {processed_ids}: {e_db_today}")
                traceback.print_exc()

            return True, f"IIF for today's POs generated ({len(processed_ids)} items) and email sent."
        else:
            print(f"WARN IIF_PO_BATCH (Today's POs - User): Email service not available. IIF generated but not sent. DB status NOT updated.")
            return True, f"IIF for today's POs generated ({len(processed_ids)} items), but email service unavailable. DB status NOT updated."
            
    elif not iif_content: 
        print(f"INFO IIF_PO_BATCH (Today's POs - User): No PO IIF content for {batch_date_str} (no new POs or error).")
        return True, "No new Purchase Orders found for today to generate IIF." # Still a success if no items
    elif iif_content and not processed_ids:
        print(f"INFO IIF_PO_BATCH (Today's POs - User): IIF content generated for {batch_date_str} but no POs were actually processed. No email sent, no DB update.")
        return True, "IIF for today's POs generated but no items met criteria for inclusion (e.g., empty POs). No email sent, no DB update."

    return False, "IIF generation for today's POs failed or no items processed."


# --- Functions for Sales IIF (Daily and Today - though not explicitly requested for scheduler/user button yet) ---
# These are here for completeness if you want to add routes for them in quickbooks.py

def create_and_email_daily_sales_iif_batch(db_engine_ref): # Example: could be called by a scheduler
    date_str = (datetime.now(timezone.utc).date() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"INFO IIF_SALES_BATCH (Daily Sales): Generating Sales IIF for date: {date_str}")
    content, failures, processed_ids_sales = generate_sales_iif_content_for_date(
        db_engine_ref, 
        target_date_str=date_str,
        process_all_pending=False # For specific date
    )
    warn_html = None
    if failures:
        warn_lines = ['<p><strong><span style="color: red; font-size: 1.2em;">WARNING: QuickBooks Item Mapping Failures (Daily Sales Orders)</span></strong></p>', '<p>Review mappings or add items in QuickBooks:</p><ul>']
        unique_fails = set()
        for f_item in failures:
            key = (f_item.get('original_sku', 'N/A'), f_item.get('option_pn', 'N/A'))
            if key not in unique_fails:
                opt_pn_part = f", OptionPN: {html.escape(str(f_item['option_pn']))}" if 'option_pn' in f_item and f_item['option_pn'] else ""
                msg = f"Order: <strong>{html.escape(str(f_item.get('bc_order_id','N/A')))}</strong>, Step: {html.escape(str(f_item.get('failed_step','N/A')))}, SKU: <strong>{html.escape(str(f_item.get('original_sku','N/A')))}</strong>{opt_pn_part} (Name: {html.escape(str(f_item.get('product_name','N/A')))})"
                warn_lines.append(f"<li>{msg}</li>"); unique_fails.add(key)
        warn_lines.append('</ul><hr>'); warn_html = "\n".join(warn_lines)
    
    if content and processed_ids_sales:
        if email_service:
            subject = f"Daily Sales Orders & Payments IIF Batch - {date_str}"
            sent = email_service.send_iif_batch_email(iif_content_string=content, batch_date_str=date_str, warning_message_html=warn_html, custom_subject=subject, filename_prefix="SalesInvoicesPayments_Daily_")
            print(f"IIF_SALES_BATCH (Daily Sales): Email for {date_str} {'sent' if sent else 'failed'}.")
            # Update database status for processed Sales Orders
            try:
                with db_engine_ref.connect() as conn_update_sales_daily:
                    with conn_update_sales_daily.begin():
                        update_sales_stmt_daily = text("UPDATE orders SET qb_sales_order_sync_status = 'synced', qb_sales_order_synced_at = :now, qb_sales_order_last_error = NULL WHERE id = ANY(:ids)")
                        conn_update_sales_daily.execute(update_sales_stmt_daily, {"now": datetime.now(timezone.utc), "ids": processed_ids_sales})
                        print(f"INFO IIF_SALES_BATCH (Daily Sales): Updated sync status for {len(processed_ids_sales)} Sales Orders in database.")
            except Exception as e_db_sales_daily:
                print(f"ERROR IIF_SALES_BATCH (Daily Sales): Failed to update DB status for Sales Orders {processed_ids_sales}: {e_db_sales_daily}")
                traceback.print_exc()
        else:
            print(f"WARN IIF_SALES_BATCH (Daily Sales): Email service not available. Sales IIF for {date_str} generated but not sent. DB status NOT updated.")
    elif not content: 
        print(f"INFO IIF_SALES_BATCH (Daily Sales): No Sales IIF content generated for {date_str} (no new sales orders or error).")
    elif content and not processed_ids_sales:
        print(f"INFO IIF_SALES_BATCH (Daily Sales): Sales IIF content generated for {date_str} but no Sales Orders were actually processed. No email sent, no DB update.")


# --- Standalone Test ---
if __name__ == '__main__':
    print("--- Running IIF Generator Standalone Test ---")
    from dotenv import load_dotenv
    load_dotenv() # Ensure .env is loaded if running standalone
    
    # Determine which engine to use (imported 'engine' or create a new one for test)
    test_engine = engine # Prefer imported engine if available
    connector_instance_for_cleanup = None

    if not test_engine:
        print("INFO IIF_TEST: 'engine' not imported from app. Attempting to create a new engine for testing.")
        try:
            # Simplified connection string for local testing if needed
            db_user = os.getenv("DB_USER")
            db_pass = os.getenv("DB_PASSWORD") # Corrected from DB_PASS
            db_name = os.getenv("DB_NAME")
            instance_conn_name = os.getenv("DB_CONNECTION_NAME") # For Cloud SQL
            db_host = os.getenv("DB_HOST", "127.0.0.1") # For direct connection
            db_port = os.getenv("DB_PORT", "5432")     # For direct connection

            if not all([db_user, db_pass, db_name]):
                raise ValueError("Missing DB_USER, DB_PASSWORD, or DB_NAME in environment variables.")

            if instance_conn_name: # Cloud SQL Connector preferred
                from google.cloud.sql.connector import Connector
                connector = Connector()
                connector_instance_for_cleanup = connector # Store to close later
                def getconn(): # type: ignore
                    conn_gcp = connector.connect(
                        instance_conn_name,
                        "pg8000",
                        user=db_user,
                        password=db_pass,
                        db=db_name
                    )
                    return conn_gcp
                test_engine = create_engine("postgresql+pg8000://", creator=getconn, echo=False)
                print("INFO IIF_TEST: Cloud SQL Connector engine created for standalone test.")
            elif db_host : # Fallback to direct connection if DB_HOST is set
                db_url = f"postgresql+pg8000://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
                test_engine = create_engine(db_url, echo=False)
                print(f"INFO IIF_TEST: Direct connection engine created for standalone test to {db_host}.")
            else:
                raise ValueError("DB_CONNECTION_NAME (for Cloud SQL) or DB_HOST (for direct) must be set for standalone test.")
        except Exception as e_engine_create:
            print(f"CRITICAL IIF_TEST: Failed to create test DB engine: {e_engine_create}")
            test_engine = None # Ensure it's None if creation failed
            if connector_instance_for_cleanup:
                 try: connector_instance_for_cleanup.close() # type: ignore
                 except Exception as e_close_conn: print(f"WARN IIF_TEST: Error closing connector instance on engine creation fail: {e_close_conn}")


    if test_engine:
        print("INFO IIF_TEST: Database engine available. Proceeding with test execution.")
        try:
            print("\n--- Generating PO IIF for ALL PENDING Purchase Orders ---")
            all_pending_po_iif_content, all_pending_po_failures, po_ids = generate_po_iif_content_for_date(test_engine, process_all_pending=True)
            if all_pending_po_iif_content:
                print(f"SUCCESS: Generated PO IIF for ALL PENDING. Length: {len(all_pending_po_iif_content)}. Processed {len(po_ids)} POs.")
                print(f"PO Item Mapping Failures: {len(all_pending_po_failures)}")
                if all_pending_po_failures:
                    print("Failures Details (POs):"); [print(f"  - {f}") for f in all_pending_po_failures]
                output_filename_po = "debug_ALL_PENDING_POs.iif"
                try:
                    with open(output_filename_po, "w", encoding="utf-8", newline='\r\n') as f: f.write(all_pending_po_iif_content)
                    print(f"PO IIF content saved to: {output_filename_po}")
                except Exception as e_save: print(f"ERROR saving PO IIF: {e_save}")
            else: print("FAILURE: No PO IIF content generated for ALL PENDING, or error occurred.")

            print("\n--- Generating Sales IIF for ALL PENDING Sales Orders ---")
            all_pending_sales_iif_content, all_pending_sales_failures, sales_ids = generate_sales_iif_content_for_date(test_engine, process_all_pending=True)
            if all_pending_sales_iif_content:
                print(f"SUCCESS: Generated Sales IIF for ALL PENDING. Length: {len(all_pending_sales_iif_content)}. Processed {len(sales_ids)} Sales Orders.")
                print(f"Sales Item Mapping Failures: {len(all_pending_sales_failures)}")
                if all_pending_sales_failures:
                    print("Failures Details (Sales):"); [print(f"  - {f}") for f in all_pending_sales_failures]
                output_filename_sales = "debug_ALL_PENDING_Sales.iif"
                try:
                    with open(output_filename_sales, "w", encoding="utf-8", newline='\r\n') as f: f.write(all_pending_sales_iif_content)
                    print(f"Sales IIF content saved to: {output_filename_sales}")
                except Exception as e_save: print(f"ERROR saving Sales IIF: {e_save}")
            else: print("FAILURE: No Sales IIF content generated for ALL PENDING, or error occurred.")

        finally:
            if connector_instance_for_cleanup: # If a new connector was created for this test run
                try: 
                    connector_instance_for_cleanup.close() # type: ignore
                    print("INFO IIF_TEST: Cloud SQL Connector (created for test) closed.")
                except Exception as e_close_conn_final: print(f"WARN IIF_TEST: Error closing Cloud SQL Connector (created for test): {e_close_conn_final}")
            
            # Dispose the engine only if it was created locally for this test and is not the imported 'engine'
            if test_engine and (engine is None or test_engine != engine) : 
                 try: 
                     test_engine.dispose()
                     print("INFO IIF_TEST: Local test engine (created for test) disposed.")
                 except Exception as e_dispose_final: print(f"WARN IIF_TEST: Error disposing local test engine (created for test): {e_dispose_final}")
            elif engine and test_engine == engine: # If it's the imported engine
                print("INFO IIF_TEST: Using imported engine from app.py, not disposing in this standalone test.")
    else:
        print("CRITICAL IIF_TEST: Database engine not available. Cannot run IIF generation test.")
    print("--- Finished IIF Generator Standalone Test ---")