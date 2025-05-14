# fetch_bc_order_details.py

import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
BIGCOMMERCE_STORE_HASH = os.getenv("BIGCOMMERCE_STORE_HASH")
BIGCOMMERCE_ACCESS_TOKEN = os.getenv("BIGCOMMERCE_ACCESS_TOKEN")
ORDER_ID = "106157134"  # Your test order ID

# --- Helper Function to Make API Calls ---
def fetch_bigcommerce_data(endpoint_url):
    """Fetches data from a BigCommerce API V2 endpoint."""
    headers = {
        "X-Auth-Token": BIGCOMMERCE_ACCESS_TOKEN,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(endpoint_url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from {endpoint_url}: {e}")
        if e.response is not None:
            print(f"Response Status: {e.response.status_code}")
            print(f"Response Text: {e.response.text}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from {endpoint_url}: {e}")
        if response is not None:
            print(f"Response Text: {response.text}")
        return None

# --- Main Script ---
if __name__ == "__main__":
    if not all([BIGCOMMERCE_STORE_HASH, BIGCOMMERCE_ACCESS_TOKEN]):
        print("Error: BIGCOMMERCE_STORE_HASH or BIGCOMMERCE_ACCESS_TOKEN not found in .env file.")
        exit()

    print(f"Fetching details for BigCommerce Order ID: {ORDER_ID}\n")

    base_api_url_v2 = f"https://api.bigcommerce.com/stores/{BIGCOMMERCE_STORE_HASH}/v2"

    # 1. Fetch Main Order Details
    order_details_url = f"{base_api_url_v2}/orders/{ORDER_ID}"
    print(f"--- Fetching Main Order Details from {order_details_url} ---")
    order_data = fetch_bigcommerce_data(order_details_url)
    if order_data:
        print(json.dumps(order_data, indent=2))
        # Key fields to look for:
        # - id (the order ID itself)
        # - status, status_id
        # - customer_id
        # - billing_address object
        # - shipping_addresses_count (if > 0, then fetch shipping addresses)
        # - items_total, items_shipped
        # - payment_method, payment_status
        # - date_created, date_modified
        print("\nKey fields from main order data to note:")
        print(f"  Order ID: {order_data.get('id')}")
        print(f"  Status: {order_data.get('status')}")
        print(f"  Status ID: {order_data.get('status_id')}")
        print(f"  Customer ID: {order_data.get('customer_id')}")
        print(f"  Date Created: {order_data.get('date_created')}")
        print(f"  Billing Address City: {order_data.get('billing_address', {}).get('city')}")
        print(f"  Shipping Addresses Count: {order_data.get('shipping_addresses_count')}") # V2 specific
    else:
        print("Could not fetch main order details.")
    print("-" * 50 + "\n")

    # 2. Fetch Shipping Addresses for the Order
    # The `order_address_id` needed for creating a shipment is the `id` of one of these shipping address objects.
    shipping_addresses_url = f"{base_api_url_v2}/orders/{ORDER_ID}/shippingaddresses"
    print(f"--- Fetching Shipping Addresses from {shipping_addresses_url} ---")
    shipping_addresses_data = fetch_bigcommerce_data(shipping_addresses_url)
    if shipping_addresses_data:
        print(json.dumps(shipping_addresses_data, indent=2))
        if isinstance(shipping_addresses_data, list) and len(shipping_addresses_data) > 0:
            print("\nKey fields from shipping addresses to note (especially the 'id' for each address):")
            for i, addr in enumerate(shipping_addresses_data):
                print(f"  Shipping Address #{i+1}:")
                print(f"    Order Address ID (order_address_id): {addr.get('id')}") # This is crucial!
                print(f"    First Name: {addr.get('first_name')}")
                print(f"    Last Name: {addr.get('last_name')}")
                print(f"    Street 1: {addr.get('street_1')}")
                print(f"    City: {addr.get('city')}")
                print(f"    State: {addr.get('state')}")
                print(f"    Zip: {addr.get('zip')}")
                print(f"    Country ISO2: {addr.get('country_iso2')}")
                print(f"    Shipping Method: {addr.get('shipping_method')}") # Useful for UPS mapping
        else:
            print("No shipping addresses found for this order, or data is not a list.")
    else:
        print("Could not fetch shipping addresses.")
    print("-" * 50 + "\n")

    # 3. Fetch Products for the Order
    # The `order_product_id` needed for the 'items' array in the shipment payload is the `id` from these product entries.
    order_products_url = f"{base_api_url_v2}/orders/{ORDER_ID}/products"
    print(f"--- Fetching Order Products from {order_products_url} ---")
    order_products_data = fetch_bigcommerce_data(order_products_url)
    if order_products_data:
        print(json.dumps(order_products_data, indent=2))
        if isinstance(order_products_data, list) and len(order_products_data) > 0:
            print("\nKey fields from order products to note (especially the 'id' for each item):")
            for i, item in enumerate(order_products_data):
                print(f"  Product #{i+1}:")
                print(f"    Order Product ID (order_product_id): {item.get('id')}") # This is crucial!
                print(f"    Product ID (catalog): {item.get('product_id')}")
                print(f"    Name: {item.get('name')}")
                print(f"    SKU: {item.get('sku')}")
                print(f"    Quantity: {item.get('quantity')}")
                print(f"    Price (ex tax): {item.get('price_ex_tax')}")
        else:
            print("No products found for this order, or data is not a list.")
    else:
        print("Could not fetch order products.")
    print("-" * 50 + "\n")

    print("Script finished.")