import os
from flask import Blueprint, request, jsonify
import requests
from infrastructure.logger import get_logger

mailerlite_webhook_bp = Blueprint("mailerlite_webhook", __name__)
logger = get_logger(__name__)

MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")  # e.g., "mg.spurly.io"
ADMIN_EMAIL = os.getenv("SUPPORT_FROM_EMAIL")        # e.g., "admin@spurly.io"
NOTIFY_TO = os.getenv("SUPPORT_TO_EMAIL")            # your personal address for alerts

@mailerlite_webhook_bp.route("/mailerlite-webhook", methods=["POST"])
def mailerlite_webhook():
    try:
        data = request.get_json()
        email = data.get('email', '')
        if not email or email == '':
            email = request.form.get('email', '')
        source = data.get('source', '')
        if not source or source == '':
            source = request.form.get('source', '')
        signup_time = data.get('subscribed_at', '')
        if not signup_time or signup_time == '':
            signup_time = request.form.get('subscribed_at', '')

        subject = "📬 New Spurly Email Subscriber"
        text = f"New subscriber joined the Spurly mailing list:\n\n" \
               f"Email: {email}\n" \
               f"Source: {source or 'unknown'}\n" \
               f"Signup time: {signup_time or 'unknown'}"

        send_mailgun_email(subject, text)
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"error": "Webhook processing failed"}), 500


def send_mailgun_email(subject, text):
    if not MAILGUN_API_KEY:
        raise ValueError("MAILGUN_API_KEY environment variable not set")
    
    return requests.post(
        f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
        auth=("api", MAILGUN_API_KEY),
        data={
            "from": f"Spurly Alerts <{ADMIN_EMAIL}>",
            "to": [NOTIFY_TO],
            "subject": subject,
            "text": text
        }
    )
