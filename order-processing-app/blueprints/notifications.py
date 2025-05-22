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

