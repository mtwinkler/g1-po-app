# order-processing-app/blueprints/reports.py

import traceback
from flask import Blueprint, jsonify, request, g, current_app
from sqlalchemy import text
from datetime import datetime, timezone, timedelta
from decimal import Decimal # Though not directly used, good to have if other reports are added

# Imports from the main app.py
from app import (
    engine, verify_firebase_token,
    convert_row_to_dict, make_json_safe
)
# No specific service modules are directly used by this report route

reports_bp = Blueprint('reports_bp', __name__)

@reports_bp.route('/reports/daily-revenue', methods=['GET'])
@verify_firebase_token
def get_daily_revenue_report():
    print("DEBUG DAILY_REVENUE_BP: Received request for daily revenue report.")
    db_conn = None
    try:
        if engine is None:
            print("ERROR DAILY_REVENUE_BP: Database engine not available.")
            return jsonify({"error": "Database engine not available."}), 500
        db_conn = engine.connect()
        print("DEBUG DAILY_REVENUE_BP: DB connection established.")
        
        today_utc = datetime.now(timezone.utc).date()
        start_date_utc = today_utc - timedelta(days=13) # For the last 14 days including today
        
        sql_query = text("""
            SELECT DATE(order_date AT TIME ZONE 'UTC') AS sale_date, SUM(total_sale_price) AS daily_revenue
            FROM orders WHERE DATE(order_date AT TIME ZONE 'UTC') >= :start_date
            GROUP BY sale_date ORDER BY sale_date DESC LIMIT 14;
        """)
        
        records = db_conn.execute(sql_query, {"start_date": start_date_utc}).fetchall()
        
        # Convert records to a dictionary for easier lookup
        revenue_map = {}
        for row in records:
            row_dict = convert_row_to_dict(row) # Use your helper
            if row_dict and row_dict.get('sale_date') is not None:
                # Ensure sale_date is a string in 'YYYY-MM-DD' format for the map key
                sale_date_str = row_dict['sale_date'].strftime('%Y-%m-%d') if isinstance(row_dict['sale_date'], datetime) else str(row_dict['sale_date'])
                revenue_map[sale_date_str] = float(row_dict.get('daily_revenue', 0.0))

        # Prepare the final list for the last 14 days, filling in zeros for days with no sales
        complete_daily_revenue = []
        for i in range(14): # Iterate 0 to 13
            current_date = today_utc - timedelta(days=i)
            current_date_str = current_date.strftime('%Y-%m-%d')
            complete_daily_revenue.append({
                "sale_date": current_date_str,
                "daily_revenue": revenue_map.get(current_date_str, 0.0)
            })
        
        # The report should be in chronological order for the frontend usually
        complete_daily_revenue.reverse() # Reverse to have oldest day first, newest day last

        print(f"DEBUG DAILY_REVENUE_BP: Fetched daily revenue for last 14 days. Count: {len(complete_daily_revenue)}")
        return jsonify(make_json_safe(complete_daily_revenue)), 200
    except Exception as e:
        print(f"ERROR DAILY_REVENUE_BP: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to fetch daily revenue report", "details": str(e)}), 500
    finally:
        if db_conn and not db_conn.closed:
            db_conn.close()
            print("DEBUG DAILY_REVENUE_BP: DB connection closed.")