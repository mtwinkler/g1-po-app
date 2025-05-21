# order-processing-app/blueprints/notifications.py
import os
import json
import traceback
from flask import Blueprint, request, jsonify, g, current_app
from sqlalchemy import text
from app import engine, verify_firebase_token # Assuming app.py has these
from pywebpush import webpush, WebPushException

notifications_bp = Blueprint('notifications_bp', __name__)

# --- Endpoint to Store Push Subscriptions ---
@notifications_bp.route('/notifications/subscribe', methods=['POST'])
@verify_firebase_token # Ensure only authenticated users can subscribe
def subscribe():
    """
    Receives a push subscription object from the frontend and stores it.
    """
    subscription_data = request.json
    if not subscription_data or 'endpoint' not in subscription_data:
        return jsonify({"error": "Invalid subscription data"}), 400

    # Potentially get user_id if you want to associate subscriptions with users
    # user_id = g.user_uid # From verify_firebase_token

    # For simplicity, we'll store the whole JSON.
    # Consider adding logic to prevent duplicate subscriptions for the same endpoint.
    try:
        with engine.connect() as conn:
            # Check if subscription endpoint already exists to avoid duplicates
            # This is a simple check; a more robust solution might involve a unique constraint
            # on the endpoint part of the JSON if your DB supports JSONB queries well,
            # or by extracting the endpoint into its own column.
            existing_sub_query = text("SELECT id FROM push_subscriptions WHERE subscription_json ->> 'endpoint' = :endpoint")
            existing = conn.execute(existing_sub_query, {"endpoint": subscription_data.get('endpoint')}).fetchone()

            if existing:
                print(f"Subscription for endpoint {subscription_data.get('endpoint')} already exists.")
                return jsonify({"message": "Subscription already exists"}), 200 # Or 200 if you treat it as success

            # If using user_id:
            # conn.execute(
            #     text("INSERT INTO push_subscriptions (user_id, subscription_json) VALUES (:user_id, :sub_json)"),
            #     {"user_id": user_id, "sub_json": json.dumps(subscription_data)}
            # )
            conn.execute(
                text("INSERT INTO push_subscriptions (subscription_json) VALUES (:sub_json)"),
                {"sub_json": json.dumps(subscription_data)} # Store as JSON string
            )
            conn.commit()
        return jsonify({"message": "Subscription saved successfully"}), 201
    except Exception as e:
        print(f"Error saving subscription: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to save subscription"}), 500

# --- Endpoint for Scheduled Task to Send "Capture Funds" Reminder ---
@notifications_bp.route('/tasks/send-capture-funds-reminder', methods=['POST'])
def send_capture_funds_reminder():
    """
    Called by Cloud Scheduler to send the "Capture Funds" reminder.
    Sends notification to all stored push subscriptions.
    """
    # IMPORTANT: Secure this endpoint!
    # Cloud Scheduler can be configured to send an OIDC token or a custom header.
    # Example: Check for a specific header if not using OIDC.
    # expected_scheduler_header = os.getenv("CLOUD_SCHEDULER_SECRET_HEADER")
    # if not request.headers.get("X-CloudScheduler-JobName") and \
    #    (not expected_scheduler_header or request.headers.get("X-Your-Custom-Header") != expected_scheduler_header):
    #     if not current_app.debug: # Allow bypass in debug mode if needed
    #         print("Unauthorized attempt to trigger scheduled task.")
    #         return jsonify({"error": "Unauthorized"}), 403

    print("INFO: Received request to send 'Capture Funds' reminder.")

    try:
        subscriptions_to_notify = []
        with engine.connect() as conn:
            result = conn.execute(text("SELECT id, subscription_json FROM push_subscriptions")) # Fetch ID too for deletion
            for row_id, sub_json_str in result:
                try:
                    subscriptions_to_notify.append({"id": row_id, "subscription": json.loads(sub_json_str)})
                except json.JSONDecodeError:
                    print(f"Warning: Could not parse subscription JSON for ID {row_id}: {sub_json_str[:100]}...")


        if not subscriptions_to_notify:
            print("No push subscriptions found to send reminder.")
            return jsonify({"message": "No subscriptions to notify."}), 200

        notification_title = "G1 PO App Reminder"
        notification_body = "Capture Funds for Shipped Orders"
        notification_url = "https://store-g6oxherh18.mybigcommerce.com/manage/orders?viewId=8"
        # You can host an icon in your frontend's public folder or a GCS bucket
        # Ensure the path is absolute if hosted, or relative to your service worker's scope
        notification_icon = "/logo192.png" # Example: if logo192.png is in your frontend's public root

        notification_payload = {
            "notification": {
                "title": notification_title,
                "body": notification_body,
                "icon": notification_icon,
                "data": { # Custom data payload
                    "url": notification_url,
                    "message": notification_body # Can be useful for the service worker
                }
            }
        }

        vapid_private_key = os.getenv("VAPID_PRIVATE_KEY")
        vapid_admin_email = os.getenv("VAPID_ADMIN_EMAIL")

        if not vapid_private_key or not vapid_admin_email:
            print("ERROR: VAPID_PRIVATE_KEY or VAPID_ADMIN_EMAIL not configured in environment.")
            return jsonify({"error": "VAPID keys/email not configured on server."}), 500

        vapid_claims = {
            "sub": f"mailto:{vapid_admin_email}"
        }

        success_count = 0
        failure_count = 0
        expired_subscription_ids = []

        for item in subscriptions_to_notify:
            sub_info = item["subscription"]
            sub_db_id = item["id"]
            try:
                print(f"Attempting to send push to endpoint: {sub_info.get('endpoint', 'N/A')[:50]}...")
                webpush(
                    subscription_info=sub_info,
                    data=json.dumps(notification_payload), # Payload must be a string
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims.copy() # Send a copy
                )
                success_count += 1
                print(f"Successfully sent push to: {sub_info.get('endpoint', 'N/A')[:50]}")
            except WebPushException as ex:
                print(f"WebPushException for endpoint {sub_info.get('endpoint', 'N/A')[:50]}: {ex}")
                failure_count += 1
                # If the subscription is expired or invalid (e.g., 404, 410 Gone), mark it for deletion
                if ex.response and ex.response.status_code in [404, 410]:
                    print(f"Subscription {sub_db_id} (endpoint: {sub_info.get('endpoint')[:50]}) is GONE or NOT FOUND. Marking for deletion.")
                    expired_subscription_ids.append(sub_db_id)
            except Exception as e_push:
                print(f"Generic error sending push to {sub_info.get('endpoint', 'N/A')[:50]}: {e_push}")
                failure_count += 1
        
        # Delete expired subscriptions
        if expired_subscription_ids:
            try:
                with engine.connect() as conn:
                    delete_stmt = text("DELETE FROM push_subscriptions WHERE id = ANY(:ids_array)")
                    conn.execute(delete_stmt, {"ids_array": expired_subscription_ids})
                    conn.commit()
                    print(f"Deleted {len(expired_subscription_ids)} expired/invalid subscriptions.")
            except Exception as e_delete:
                print(f"Error deleting expired subscriptions: {e_delete}")
                traceback.print_exc()
        
        summary_message = f"Capture funds reminder push process completed. Successful: {success_count}, Failed: {failure_count}."
        print(summary_message)
        return jsonify({
            "message": summary_message,
            "successful_sends": success_count,
            "failed_sends": failure_count
        }), 200

    except Exception as e:
        print(f"Critical error in send_capture_funds_reminder task: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to process capture funds reminder due to an internal error"}), 500

# --- Optional: Endpoint to provide VAPID Public Key to Frontend ---
@notifications_bp.route('/notifications/vapid-public-key', methods=['GET'])
def get_vapid_public_key():
    """
    Provides the VAPID public key to the frontend.
    This endpoint should be unauthenticated if your frontend needs to fetch it before user login,
    or it can be authenticated if subscription happens only post-login.
    """
    vapid_public_key = os.getenv("VAPID_PUBLIC_KEY")
    if not vapid_public_key:
        print("ERROR: VAPID_PUBLIC_KEY not configured in environment.")
        return jsonify({"error": "VAPID public key not configured on server."}), 500
    return jsonify({"publicKey": vapid_public_key}), 200