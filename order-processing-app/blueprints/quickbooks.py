# order-processing-app/blueprints/quickbooks.py

import traceback
from flask import Blueprint, jsonify, request, g, current_app
from sqlalchemy import text # Not directly used here but can be if needed for status checks
from datetime import datetime, timezone
import sys # For traceback
import html # For email formatting in trigger_quickbooks_sync_on_demand

# Imports from the main app.py or other modules
from app import (
    engine, verify_firebase_token, app as main_app_for_debug_check # app for app.debug
)

# Import service modules
import iif_generator # This blueprint heavily uses iif_generator
import email_service # iif_generator uses this, but trigger_sync also calls it

quickbooks_bp = Blueprint('quickbooks_bp', __name__)

# SCHEDULER ROUTE FOR THE MAIN DAILY BATCH (YESTERDAY'S POs) - POs only
@quickbooks_bp.route('/tasks/scheduler/trigger-daily-iif-batch', methods=['POST'])
def scheduler_trigger_daily_iif_batch():
    print("INFO QB_BP (DAILY IIF BATCH): Received request for DAILY IIF BATCH (Yesterday's POs) from scheduler.", flush=True)
    # Optional: Add Cloud Scheduler header verification here
    # if not request.headers.get("X-CloudScheduler") and not main_app_for_debug_check.debug: # Use main_app_for_debug_check
    # print("WARN QB_BP (DAILY IIF BATCH): Missing X-CloudScheduler header.")
    # return jsonify({"error": "Forbidden - Invalid Caller"}), 403

    if iif_generator is None:
        print("ERROR QB_BP (DAILY IIF BATCH): iif_generator module not loaded.", flush=True)
        return jsonify({"error": "IIF generation module not available."}), 500
    if engine is None:
        print("ERROR QB_BP (DAILY IIF BATCH): Database engine not initialized.", flush=True)
        return jsonify({"error": "Database engine not available."}), 500
    try:
        print("INFO QB_BP (DAILY IIF BATCH): Calling iif_generator.create_and_email_daily_iif_batch...", flush=True)
        # This function was designed for POs from yesterday
        iif_generator.create_and_email_daily_iif_batch(engine) # Passes engine

        print(f"INFO QB_BP (DAILY IIF BATCH): Daily IIF batch (yesterday's POs) task triggered successfully.", flush=True)
        return jsonify({"message": "Daily IIF batch (yesterday's POs) task triggered."}), 200
    except Exception as e:
        print(f"ERROR QB_BP (DAILY IIF BATCH): Unhandled exception in route: {e}", flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return jsonify({"error": "An error occurred during scheduled daily IIF batch generation.", "details": str(e)}), 500

# USER-TRIGGERED ROUTE FOR TODAY'S POs - POs only
@quickbooks_bp.route('/tasks/trigger-iif-for-today-user', methods=['POST'])
@verify_firebase_token # User triggered, so needs auth
def user_trigger_iif_for_today():
    print("INFO QB_BP (TODAY IIF USER): Received request for TODAY'S IIF by user.", flush=True)
    if iif_generator is None:
        print("ERROR QB_BP (TODAY IIF USER): iif_generator module not loaded.", flush=True)
        return jsonify({"error": "IIF generation module not available."}), 500
    if engine is None:
        print("ERROR QB_BP (TODAY IIF USER): Database engine not initialized.", flush=True)
        return jsonify({"error": "Database engine not available."}), 500
    try:
        print("INFO QB_BP (TODAY IIF USER): Calling iif_generator.create_and_email_iif_for_today...", flush=True)
        # This function was designed for POs from today
        success, result_message_or_content = iif_generator.create_and_email_iif_for_today(engine) # Passes engine

        if success:
            # Avoid printing potentially large IIF content to log
            log_result = result_message_or_content
            if isinstance(result_message_or_content, str) and len(result_message_or_content) > 200:
                log_result = f"IIF content generated (length: {len(result_message_or_content)})"
            print(f"INFO QB_BP (TODAY IIF USER): Today's IIF task completed. Success: {success}, Result: {log_result}", flush=True)
            return jsonify({"message": "IIF generation for today's POs triggered and email sent (if configured)."}), 200
        else:
            print(f"ERROR QB_BP (TODAY IIF USER): Today's IIF task failed. Success: {success}, Message: {result_message_or_content}", flush=True)
            return jsonify({"error": result_message_or_content or "IIF generation for today failed. Check logs."}), 500
    except Exception as e:
        print(f"ERROR QB_BP (TODAY IIF USER): Unhandled exception in route: {e}", flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return jsonify({"error": "An error occurred during user-triggered IIF generation.", "details": str(e)}), 500

@quickbooks_bp.route('/quickbooks/trigger-sync', methods=['POST'])
@verify_firebase_token
def trigger_quickbooks_sync_on_demand():
    print("INFO QB_BP (ON-DEMAND SYNC): Received request to trigger on-demand QuickBooks IIF generation.", flush=True)
    try:
        if iif_generator is None:
            print("ERROR QB_BP (ON-DEMAND SYNC): iif_generator module not loaded.", flush=True)
            return jsonify({"error": "IIF generation module not available at the server.", "details": "iif_generator is None"}), 500
        if engine is None:
            print("ERROR QB_BP (ON-DEMAND SYNC): Database engine not initialized.", flush=True)
            return jsonify({"error": "Database engine not available at the server.", "details": "engine is None"}), 500

        po_sync_success = False
        po_sync_message = "PO sync not initiated."
        sales_sync_success = False
        sales_sync_message = "Sales sync not initiated."
        
        processed_po_db_ids_for_db_update = []
        processed_sales_order_db_ids_for_db_update = []
        db_update_error_message = None

        current_time_for_sync = datetime.now(timezone.utc) # Used for email subject and db update

        # --- Process Purchase Orders ---
        try:
            print("INFO QB_BP (ON-DEMAND SYNC): Generating IIF for ALL PENDING Purchase Orders...", flush=True)
            # The `generate_po_iif_content_for_date` in iif_generator.py will handle filtering for pending
            po_iif_content, po_mapping_failures, po_ids_in_batch = iif_generator.generate_po_iif_content_for_date(engine, process_all_pending=True) # Pass engine
            
            if po_iif_content:
                if po_ids_in_batch: # Only email if there's content AND items were processed
                    if email_service: # Check if email_service itself is available
                        po_email_warning_html = None
                        if po_mapping_failures: # Format mapping failures for email
                            po_warn_lines = ['<p><strong><span style="color: red; font-size: 1.2em;">WARNING: QuickBooks Item Mapping Failures (Purchase Orders - On Demand)</span></strong></p><ul>']
                            unique_po_fails = set()
                            for f_po in po_mapping_failures:
                                key_po = (f_po.get('po_number', 'N/A'), f_po.get('failed_sku', 'N/A'))
                                if key_po not in unique_po_fails:
                                    po_warn_lines.append(f"<li>PO: {html.escape(str(f_po.get('po_number','N/A')))}, SKU: {html.escape(str(f_po.get('failed_sku','N/A')))} (Desc: {html.escape(str(f_po.get('description','N/A')))})</li>")
                                    unique_po_fails.add(key_po)
                            po_warn_lines.append("</ul><hr>")
                            po_email_warning_html = "\n".join(po_warn_lines)
                        
                        # Use the send_iif_batch_email from the imported email_service module
                        email_sent_po = email_service.send_iif_batch_email(
                            iif_content_string=po_iif_content,
                            batch_date_str=f"OnDemand_AllPendingPOs_{current_time_for_sync.strftime('%Y%m%d_%H%M%S')}",
                            warning_message_html=po_email_warning_html, # Pass formatted warnings
                            custom_subject=f"On-Demand All Pending POs IIF Batch - {current_time_for_sync.strftime('%Y-%m-%d %H:%M')}"
                        )
                        if email_sent_po:
                            po_sync_success = True
                            processed_po_db_ids_for_db_update = po_ids_in_batch # Store IDs for DB update
                            po_sync_message = f"Purchase Order IIF generation for {len(po_ids_in_batch)} pending item(s) successful and emailed."
                        else:
                            po_sync_success = False # Email failed
                            po_sync_message = f"Purchase Order IIF generated for {len(po_ids_in_batch)} items, but email FAILED."
                    else:
                        print("WARN QB_BP (ON-DEMAND SYNC): Email service not available for POs. IIF not emailed.", flush=True)
                        po_sync_success = True # IIF generated, just not emailed
                        processed_po_db_ids_for_db_update = po_ids_in_batch
                        po_sync_message = f"Purchase Order IIF generated for {len(po_ids_in_batch)} items, but email service unavailable."
                else: # Content generated, but no specific PO IDs (e.g., only header/footer, no actual POs)
                     po_sync_success = True # No pending POs found is a "successful" outcome for this part
                     po_sync_message = "No pending Purchase Orders found to process for IIF."
            else: # No IIF content at all (e.g., function returned None or empty string)
                 # This might also mean no pending POs, depends on iif_generator's behavior
                 if not po_mapping_failures and not po_ids_in_batch: # Check if it was because no items
                    po_sync_success = True
                    po_sync_message = "No pending Purchase Orders to generate IIF for."
                 else:
                    po_sync_success = False
                    po_sync_message = "Purchase Order IIF generation for all pending items failed (no IIF content returned)."
        except Exception as e_po:
            print(f"ERROR QB_BP (ON-DEMAND SYNC): Error during PO IIF processing block: {e_po}", flush=True)
            traceback.print_exc(file=sys.stderr)
            po_sync_success = False
            po_sync_message = f"Error generating/processing PO IIF: {str(e_po)}"

        # --- Process Sales Orders ---
        try:
            print("INFO QB_BP (ON-DEMAND SYNC): Generating IIF for ALL PENDING Sales Orders/Invoices...", flush=True)
            sales_iif_content, sales_mapping_failures, sales_ids_in_batch = iif_generator.generate_sales_iif_content_for_date(engine, process_all_pending=True) # Pass engine
            
            if sales_iif_content:
                if sales_ids_in_batch:
                    if email_service:
                        sales_email_warning_html = None
                        if sales_mapping_failures:
                            sales_warn_lines = ['<p><strong><span style="color: red; font-size: 1.2em;">WARNING: QuickBooks Item Mapping Failures (Sales Orders - On Demand)</span></strong></p><ul>']
                            unique_sales_fails = set()
                            for f_sales in sales_mapping_failures:
                                key_sales = (f_sales.get('original_sku', 'N/A_SKU'), f_sales.get('option_pn', 'N/A_PN'))
                                if key_sales not in unique_sales_fails:
                                    opt_pn_part_sales = f", OptionPN: {html.escape(str(f_sales.get('option_pn','N/A')))}" if 'option_pn' in f_sales and f_sales.get('option_pn') else ""
                                    msg_sales = (f"Order: <strong>{html.escape(str(f_sales.get('bc_order_id','N/A')))}</strong>, Step: {html.escape(str(f_sales.get('failed_step','N/A')))}, SKU: <strong>{html.escape(str(f_sales.get('original_sku','N/A')))}</strong>{opt_pn_part_sales} (Name: {html.escape(str(f_sales.get('product_name','N/A')))})")
                                    sales_warn_lines.append(f"<li>{msg_sales}</li>")
                                    unique_sales_fails.add(key_sales)
                            sales_warn_lines.append("</ul><hr>")
                            sales_email_warning_html = "\n".join(sales_warn_lines)
                        
                        email_sent_sales = email_service.send_iif_batch_email(
                            iif_content_string=sales_iif_content,
                            batch_date_str=f"OnDemand_AllPendingSales_{current_time_for_sync.strftime('%Y%m%d_%H%M%S')}",
                            warning_message_html=sales_email_warning_html,
                            custom_subject=f"On-Demand All Pending Sales Orders IIF Batch - {current_time_for_sync.strftime('%Y-%m-%d %H:%M')}"
                        )
                        if email_sent_sales:
                            processed_sales_order_db_ids_for_db_update = sales_ids_in_batch
                            sales_sync_success = True
                            sales_sync_message = f"Sales Order IIF generation for {len(sales_ids_in_batch)} pending item(s) successful and emailed."
                        else:
                            sales_sync_success = False
                            sales_sync_message = f"Sales Order IIF generated for {len(sales_ids_in_batch)} items, but email FAILED."
                    else:
                        print("WARN QB_BP (ON-DEMAND SYNC): Email service not available for Sales. IIF not emailed.", flush=True)
                        sales_sync_success = True
                        processed_sales_order_db_ids_for_db_update = sales_ids_in_batch
                        sales_sync_message = f"Sales Order IIF generated for {len(sales_ids_in_batch)} items, but email service unavailable."
                else: # Content generated, but no specific Sales IDs
                    sales_sync_success = True
                    sales_sync_message = "No pending Sales Orders found to process for IIF."
            else: # No IIF content
                if not sales_mapping_failures and not sales_ids_in_batch:
                    sales_sync_success = True
                    sales_sync_message = "No pending Sales Orders to generate IIF for."
                else:
                    sales_sync_success = False
                    sales_sync_message = "Sales Order IIF generation for all pending items failed (no IIF content returned)."
        except Exception as e_sales:
            print(f"ERROR QB_BP (ON-DEMAND SYNC): Error during Sales IIF processing block: {e_sales}", flush=True)
            traceback.print_exc(file=sys.stderr)
            sales_sync_success = False
            sales_sync_message = f"Error generating/processing Sales IIF: {str(e_sales)}"

        # --- Database Status Updates ---
        try:
            with engine.connect() as conn: # Use 'conn' as the variable name for the connection
                with conn.begin(): # Start a transaction on this connection
                    if po_sync_success and processed_po_db_ids_for_db_update:
                        print(f"INFO QB_BP (ON-DEMAND SYNC): Updating status for {len(processed_po_db_ids_for_db_update)} POs.", flush=True)
                        update_po_stmt = text("UPDATE purchase_orders SET qb_po_sync_status = 'synced', qb_po_synced_at = :now, qb_po_last_error = NULL WHERE id = ANY(:ids_array)")
                        conn.execute(update_po_stmt, {"now": current_time_for_sync, "ids_array": processed_po_db_ids_for_db_update})
                    
                    if sales_sync_success and processed_sales_order_db_ids_for_db_update:
                        print(f"INFO QB_BP (ON-DEMAND SYNC): Updating status for {len(processed_sales_order_db_ids_for_db_update)} Sales Orders.", flush=True)
                        update_sales_stmt = text("UPDATE orders SET qb_sales_order_sync_status = 'synced', qb_sales_order_synced_at = :now, qb_sales_order_last_error = NULL WHERE id = ANY(:ids_array)")
                        conn.execute(update_sales_stmt, {"now": current_time_for_sync, "ids_array": processed_sales_order_db_ids_for_db_update})
                # Transaction is committed here if no exceptions within the 'with conn.begin()'
                print("INFO QB_BP (ON-DEMAND SYNC): Database status updates transaction committed (if any updates were made).", flush=True)
        except Exception as e_db_update:
            print(f"ERROR QB_BP (ON-DEMAND SYNC): Error during database status updates: {e_db_update}", flush=True)
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush() # Ensure traceback is written
            db_update_error_message = f"IIFs may have been generated/emailed, BUT FAILED to update database sync statuses: {str(e_db_update)}"
            
        final_status_message = f"PO Sync: {po_sync_message} | Sales Sync: {sales_sync_message}"
        if db_update_error_message:
            final_status_message += f" | DB Update Status: {db_update_error_message}"
        
        # Determine overall success based on whether IIFs were meant to be generated and if DB updates were okay
        # If no items were pending, it's still a "successful" run in a sense.
        overall_success = (po_sync_success or "No pending Purchase Orders" in po_sync_message) and \
                          (sales_sync_success or "No pending Sales Orders" in sales_sync_message) and \
                          (db_update_error_message is None)

        print(f"INFO QB_BP (ON-DEMAND SYNC): Finalizing response. Overall success: {overall_success}. Message: {final_status_message}", flush=True)
        if overall_success:
            return jsonify({"message": final_status_message, "po_status": po_sync_message, "sales_status": sales_sync_message, "db_update_info": db_update_error_message or "DB status updates successful (if any)."}), 200
        else:
            # Be more specific in the top-level error message if possible
            error_summary = "One or more operations had issues."
            if not po_sync_success and "No pending Purchase Orders" not in po_sync_message : error_summary += " PO sync failed."
            if not sales_sync_success and "No pending Sales Orders" not in sales_sync_message : error_summary += " Sales sync failed."
            if db_update_error_message: error_summary += " DB update failed."

            return jsonify({"error": error_summary.strip(), "details": final_status_message, "po_status": po_sync_message, "sales_status": sales_sync_message, "db_update_info": db_update_error_message}), 500

    except Exception as e: # Catch-all for the entire route
        print(f"CRITICAL ERROR QB_BP (ON-DEMAND SYNC): Unhandled exception in main route try-block: {e}", flush=True)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        return jsonify({"error": "A critical unexpected error occurred during the sync process.", "details": str(e)}), 500