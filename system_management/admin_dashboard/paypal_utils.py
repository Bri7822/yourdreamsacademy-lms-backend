import requests
from django.conf import settings
from decimal import Decimal

def get_paypal_access_token():
    """Get PayPal API access token"""
    auth = (settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET)
    headers = {"Accept": "application/json", "Accept-Language": "en_US"}
    data = {"grant_type": "client_credentials"}
    
    response = requests.post(
        f"{settings.PAYPAL_BASE_URL}/v1/oauth2/token",
        auth=auth,
        headers=headers,
        data=data
    )
    
    response.raise_for_status()
    return response.json()["access_token"]

def create_paypal_order(amount, currency, course_name, transaction_id):
    """Create a PayPal order"""
    access_token = get_paypal_access_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Prefer": "return=representation"
    }
    
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": transaction_id,
            "description": course_name,
            "amount": {
                "currency_code": currency,
                "value": str(amount)
            }
        }]
    }
    
    response = requests.post(
        f"{settings.PAYPAL_BASE_URL}/v2/checkout/orders",
        headers=headers,
        json=payload
    )
    
    response.raise_for_status()
    return response.json()

def capture_paypal_order(order_id):
    """Capture a PayPal payment"""
    access_token = get_paypal_access_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Prefer": "return=representation"
    }
    
    response = requests.post(
        f"{settings.PAYPAL_BASE_URL}/v2/checkout/orders/{order_id}/capture",
        headers=headers
    )
    
    response.raise_for_status()
    return response.json()