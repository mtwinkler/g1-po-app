import os
import pycountry
from dotenv import load_dotenv

load_dotenv()

# Load SHIPPER_EIN from environment variables
SHIPPER_EIN = os.getenv('SHIPPER_EIN')

def get_country_name_from_iso(iso_code):
    """
    Converts a 2-letter ISO country code to its full name.
    """
    if not iso_code or len(iso_code) != 2:
        return "Unknown"
    try:
        country = pycountry.countries.get(alpha_2=iso_code.upper())
        return country.name if country else "Unknown"
    except Exception as e:
        print(f"Error converting ISO code {iso_code}: {e}")
        return "Unknown"