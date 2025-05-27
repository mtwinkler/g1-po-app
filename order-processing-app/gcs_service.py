# gcs_service.py

import os
from google.cloud import storage
from flask import current_app

# Configuration - Ensure your GCS_BUCKET_NAME is set in your .env file or app config
# The Handover Report mentions a bucket gs://g1-po-app-documents/ for the logo,
# so your labels might go into the same bucket or a similar one.
# For example: GCS_BUCKET_NAME = "g1-po-app-documents"

def _get_gcs_client():
    """Initializes and returns a GCS client."""
    try:
        # GOOGLE_APPLICATION_CREDENTIALS environment variable should be set
        # for this to work automatically in local development and Cloud Run.
        client = storage.Client()
        print("DEBUG GCS_SERVICE: Google Cloud Storage client initialized successfully.")
        return client
    except Exception as e:
        current_app.logger.error(f"Failed to initialize Google Cloud Storage client: {e}", exc_info=True)
        print(f"ERROR GCS_SERVICE: Failed to initialize Google Cloud Storage client: {e}")
        return None

def get_gcs_bucket_name():
    """Gets the GCS bucket name from Flask app config or environment variable."""
    bucket_name = current_app.config.get('GCS_BUCKET_NAME')
    if not bucket_name:
        bucket_name = os.environ.get('GCS_BUCKET_NAME')
    
    if not bucket_name:
        current_app.logger.error("GCS_BUCKET_NAME is not configured in app config or environment variables.")
        print("ERROR GCS_SERVICE: GCS_BUCKET_NAME is not configured.")
    else:
        print(f"DEBUG GCS_SERVICE: Using GCS Bucket: {bucket_name}")
    return bucket_name


def upload_file_bytes(file_bytes, destination_blob_name, content_type='application/pdf'):
    """
    Uploads a file (from bytes) to a GCS bucket.

    For buckets with Uniform access control, public access must be granted via IAM
    at the bucket level (e.g., granting 'Storage Object Viewer' to 'allUsers'),
    not on a per-object basis.

    Args:
        file_bytes (bytes): The bytes of the file to upload.
        destination_blob_name (str): The desired path and filename in the GCS bucket
                                     (e.g., "shipping_labels/order_123/label.pdf").
        content_type (str): The content type of the file (e.g., "application/pdf").

    Returns:
        str: The public URL of the uploaded file, or None if upload failed.
    """
    storage_client = _get_gcs_client()
    bucket_name = get_gcs_bucket_name()

    if not storage_client or not bucket_name:
        current_app.logger.error("GCS client or bucket name not available. Cannot upload file.")
        return None

    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)

        print(f"DEBUG GCS_SERVICE: Uploading to gs://{bucket_name}/{destination_blob_name} with content type {content_type}")
        
        # Upload the file bytes
        blob.upload_from_string(file_bytes, content_type=content_type)
        
        # The blob.make_public() call has been removed.
        # Access control is now managed by the bucket's IAM settings (Uniform access).
        
        # The public_url attribute provides the publicly accessible URL format.
        # Actual accessibility depends on the bucket's permissions.
        public_url = blob.public_url
        print(f"DEBUG GCS_SERVICE: File uploaded successfully. Public URL: {public_url}")
        return public_url
    except Exception as e:
        # The previous error was a 'BadRequest: 400 ... Cannot get legacy ACL'
        # which this change is intended to fix.
        current_app.logger.error(f"Failed to upload file to GCS bucket '{bucket_name}' at '{destination_blob_name}': {e}", exc_info=True)
        print(f"ERROR GCS_SERVICE: Failed to upload to gs://{bucket_name}/{destination_blob_name}: {e}")
        return None

if __name__ == '__main__':
    # This is for standalone testing if you run `python gcs_service.py`
    # You would need to set up a mock Flask app context or load .env directly for GCS_BUCKET_NAME
    print("INFO GCS_SERVICE: Running in standalone mode (for testing).")
    # To test, you would typically do:
    # 1. Ensure GOOGLE_APPLICATION_CREDENTIALS is set.
    # 2. Set GCS_BUCKET_NAME environment variable.
    # 3. Create mock Flask app context or adjust get_gcs_bucket_name for standalone execution.
    # Example:
    # from dotenv import load_dotenv
    # load_dotenv()
    # GCS_BUCKET_NAME_TEST = os.getenv("GCS_BUCKET_NAME")
    # if GCS_BUCKET_NAME_TEST:
    #     print(f"Attempting to use bucket: {GCS_BUCKET_NAME_TEST}")
    #     # You'd need to mock current_app.config or pass bucket_name directly for a real test.
    #     # test_bytes = b"This is a test PDF content."
    #     # test_url = upload_file_bytes(test_bytes, "test_uploads/test_label.pdf", "application/pdf") # This call would need app context
    #     # if test_url:
    #     #     print(f"Test upload successful: {test_url}")
    #     # else:
    #     #     print("Test upload failed.")
    # else:
    #     print("GCS_BUCKET_NAME not set in .env for standalone test.")
    pass