# generate_vapid.py
import traceback
try:
    from pywebpush.vapid import generate_vapid_keys

    # Generate a new VAPID key pair
    # The generate_vapid_keys() function returns a tuple: (private_key_bytes, public_key_bytes)
    # These keys are URL-safe base64 encoded strings, but the library handles bytes internally first.
    # The string representation is what you'll store.
    private_key, public_key = generate_vapid_keys()

    print("VAPID Private Key (Keep this SECRET and store securely):")
    print(private_key) # This will be a URL-safe base64 encoded string
    print("\n--------------------------------------------------\n")
    print("VAPID Public Key (This can be shared with the client-side):")
    print(public_key)  # This will be a URL-safe base64 encoded string
    print("\n--------------------------------------------------\n")
    print("Reminder: Store these keys securely, typically as environment variables or secrets.")
    print("The keys printed are URL-safe base64 encoded strings.")

except ImportError:
    print("ERROR: Could not import 'generate_vapid_keys' from 'pywebpush.vapid'.")
    print("Please ensure 'pywebpush' is installed correctly in your virtual environment.")
    print("Try running: python -m pip install pywebpush")
except Exception as e:
    print(f"An error occurred during VAPID key generation: {e}")
    traceback.print_exc()