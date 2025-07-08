import os
import hashlib
import time
from flask import Blueprint, request, jsonify
import requests
from infrastructure.logger import get_logger
from infrastructure.clients import get_firestore_db
from datetime import datetime, timezone
import threading

mailerlite_webhook_bp = Blueprint("mailerlite_webhook", __name__)
logger = get_logger(__name__)

MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")
ADMIN_EMAIL = os.getenv("SUPPORT_FROM_EMAIL")
NOTIFY_TO = os.getenv("SUPPORT_TO_EMAIL")

# In-memory cache for deduplication (consider Redis for production)
processed_webhooks = {}
WEBHOOK_CACHE_TTL = 3600  # 1 hour

def send_mailgun_email_async(subject, text):
    """Send email in a background thread to avoid blocking the webhook response"""
    def _send():
        try:
            if not MAILGUN_API_KEY:
                logger.error("MAILGUN_API_KEY environment variable not set")
                return
            
            response = requests.post(
                f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
                auth=("api", MAILGUN_API_KEY),
                data={
                    "from": f"Spurly Alerts <{ADMIN_EMAIL}>",
                    "to": [NOTIFY_TO],
                    "subject": subject,
                    "text": text
                },
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Successfully sent email: {subject}")
            else:
                logger.error(f"Failed to send email. Status: {response.status_code}, Response: {response.text}")
                
        except Exception as e:
            logger.error(f"Error sending email: {e}")
    
    # Start background thread
    thread = threading.Thread(target=_send, daemon=True)
    thread.start()

def generate_webhook_id(data):
    """Generate a unique ID for the webhook based on its content"""
    # Create a hash of the essential webhook data
    webhook_str = f"{data.get('email', '')}:{data.get('subscribed_at', '')}:{data.get('source', '')}"
    return hashlib.sha256(webhook_str.encode()).hexdigest()

def is_duplicate_webhook(webhook_id):
    """Check if we've already processed this webhook"""
    current_time = time.time()
    
    # Clean up old entries
    expired_keys = [k for k, v in processed_webhooks.items() 
                    if current_time - v > WEBHOOK_CACHE_TTL]
    for key in expired_keys:
        del processed_webhooks[key]
    
    # Check if this webhook was already processed
    if webhook_id in processed_webhooks:
        return True
    
    # Mark as processed
    processed_webhooks[webhook_id] = current_time
    return False

@mailerlite_webhook_bp.route("/mailerlite-webhook", methods=["POST"])
def mailerlite_webhook():
    try:
        # Get data from both JSON and form data
        data = request.get_json() or {}
        form_data = request.form.to_dict()
        
        # Merge form data into data if JSON is empty
        if not data:
            data = form_data
        
        # Extract fields with fallback
        email = data.get('email') or form_data.get('email', '')
        source = data.get('source') or form_data.get('source', '')
        signup_time = data.get('subscribed_at') or form_data.get('subscribed_at', '')
        
        # Validate required fields
        if not email:
            logger.warning("Webhook received without email")
            return jsonify({"error": "Email is required"}), 400
        
        # Generate webhook ID and check for duplicates
        webhook_id = generate_webhook_id(data)
        if is_duplicate_webhook(webhook_id):
            logger.info(f"Duplicate webhook detected for email: {email}")
            return jsonify({"status": "ok", "message": "Already processed"}), 200
        
        # Log the webhook for debugging
        logger.info(f"Processing webhook - Email: {email}, Source: {source}, Time: {signup_time}")
        
        # Prepare email content
        subject = "📬 New Spurly Email Subscriber"
        text = f"New subscriber joined the Spurly mailing list:\n\n" \
               f"Email: {email}\n" \
               f"Source: {source or 'unknown'}\n" \
               f"Signup time: {signup_time or 'unknown'}\n" \
               f"Webhook ID: {webhook_id[:8]}..."  # Include partial ID for debugging
        
        # Send email asynchronously to respond quickly
        send_mailgun_email_async(subject, text)
        
        # Optionally store in Firestore for persistent deduplication
        try:
            db = get_firestore_db()
            webhook_ref = db.collection("webhook_logs").document(webhook_id)
            webhook_ref.set({
                "webhook_id": webhook_id,
                "email": email,
                "source": source,
                "signup_time": signup_time,
                "processed_at": datetime.now(timezone.utc),
                "type": "mailerlite_subscriber"
            })
        except Exception as e:
            logger.error(f"Failed to log webhook to Firestore: {e}")
            # Don't fail the webhook if logging fails
        
        # Return success immediately
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        # Still return 200 to prevent retries for malformed webhooks
        return jsonify({"status": "ok", "error": str(e)}), 200