# subscriptions.py ― Flask version
import os
from flask import Blueprint, request, jsonify, abort
from google.cloud import firestore
from appstoreserverlibrary.signed_data_verifier import (
    SignedDataVerifier,
    VerificationException,
)
from appstoreserverlibrary.models import Environment
from infrastructure.email_service import email_service 
from infrastructure.logger import get_logger
from infrastructure.app_account_mapper import uid_from_token

logger = get_logger(__name__)

ROOT_CERT_PATH = os.environ.get("APPLE_ROOT_CA_PATH", "resources/AppleRootCA-G3.cer")
BUNDLE_ID = os.getenv("APPLE_BUNDLE_ID", "com.phaeton-order.spurly")        # safety guard
ENV_MODE  = os.getenv("ENV", "sandbox")                # prod | staging | dev

# Convert string environment to Environment enum
if ENV_MODE == "production":
    ENVIRONMENT = Environment.Environment.PRODUCTION
else:
    ENVIRONMENT = Environment.Environment.SANDBOX

with open(ROOT_CERT_PATH, 'rb') as f:
    ROOT_CERT = f.read()
    
verifier = SignedDataVerifier(root_certificates=[ROOT_CERT], 
                              enable_online_checks=False,
                             bundle_id=BUNDLE_ID, 
                             environment=ENVIRONMENT)


fs       = firestore.Client()

# Canonical status mapping for your Firestore docs
PLAN_MAP = {
    "free": {"tier": "free", "token_allowance": 0},
    "com.phaeton.order.spurly.subscription.basic":   {"tier": "com.phaeton.order.spurly.subscription.basic",   "token_allowance": 25000},
    "com.phaeton.order.spurly.subscription.premium": {"tier": "com.phaeton.order.spurly.subscription.premium", "token_allowance": 100000},
}


STATUS_MAP = {
    1: "active",
    2: "expired",
    3: "in_retry",
    4: "in_grace",
    5: "revoked",
}

# ---------------------------------------------------------------------------
subscriptions_bp = Blueprint("apple_subscriptions", __name__)

@subscriptions_bp.route("/apple/subscription-webhook", methods=["POST"])
def apple_subscription_webhook():
    payload = request.get_json(silent=True) or {}
    signed  = payload.get("signedPayload")
    if not signed:
        logger.error("Missing signedPayload in request")
        abort(400, "Missing signedPayload")
        


    # -- Verify JWS signature & basic bundle‑id guardrail --------------------
    try:
        decoded = verifier.verify_and_decode_notification(
            signed_payload=signed
        )
        logger.error(f"LOG.INFO: Decoded Apple subscription notification: {decoded}")
    except VerificationException as exc:
        logger.error(f"Signature verification failed: {exc}")
        abort(400, f"Signature verification failed: {exc}")
        
    uid = None
    env = None
    renew = None
    notif_id = None
    tx = None
    notification_type = None
    token = None
    firebase_uid = None
    plan = PLAN_MAP["free"]  # Initialize with default plan
    if decoded and decoded.data:
        env         = decoded.data.environment                      # Sandbox | Production
        notif_id    = decoded.notificationUUID
        notification_type = decoded.rawNotificationType
        subtype = decoded.rawSubtype
        
        message = f"Received Apple subscription notification:\n\n{decoded}"
        subject = f"💰 Apple Subscription Notification: {notification_type} ({subtype})"

        email_service.send_email(
            to_email="admin@spurly.io",
            subject=subject,
            html_content=message
        )
        
        if not decoded.data.signedTransactionInfo or not decoded.data.signedRenewalInfo:
            logger.error("Missing signedTransactionInfo or signedRenewalInfo in notification")
            abort(400, "Missing signedTransactionInfo")
            
        tx          = verifier.verify_and_decode_signed_transaction(decoded.data.signedTransactionInfo)
        renew       = verifier.verify_and_decode_renewal_info(decoded.data.signedRenewalInfo)
        uid         = tx.appAccountToken             # set on‑device at purchase
        
        if tx and tx.appAccountToken:
            token = tx.appAccountToken
            firebase_uid = uid_from_token(token)
            if not firebase_uid:
                logger.error(f"Cannot map appAccountToken {token} to firebase UID")
                abort(422, "Cannot map appAccountToken to firebase UID")

        logger.error(f"LOG.INFO: Apple subscription webhook received for user {firebase_uid} in {env} environment")

        tx_pid = tx.productId
        next_pid = renew.autoRenewProductId or tx_pid
        
        if tx_pid:
            plan = PLAN_MAP.get(tx_pid) or PLAN_MAP["free"]
        else:
            plan = PLAN_MAP["free"]
        
        if next_pid:
            next_plan = PLAN_MAP.get(next_pid) or PLAN_MAP["free"]
        else:
            next_plan = PLAN_MAP["free"]

    if not uid:
        logger.error("No appAccountToken in transaction; cannot map to user")
        abort(422, "No appAccountToken; cannot map to user")

    # Ignore sandbox traffic when running in production (and vice‑versa)
    if (env == "Sandbox" and ENV_MODE == "production") or (
        env == "Production" and ENV_MODE != "production"
    ):
        return "", 204

    # Handle potential None values and convert enum to int
    auto_renew_status = renew.autoRenewStatus if renew and renew.autoRenewStatus else None
    status_key = int(auto_renew_status) if auto_renew_status is not None else None
    new_status = STATUS_MAP.get(status_key, "unknown") if status_key is not None else "unknown"

    # ----------------- Firestore idempotent update -------------------------
    doc_ref = fs.collection("users").document(firebase_uid).collection("billing").document("profile")
    logger.error(f"LOG.INFO: Updating subscription status for user {firebase_uid} to {new_status} with plan {plan['tier']}")

    @firestore.transactional
    def _update_if_new(txn):
        snap = doc_ref.get(transaction=txn)
        seen = snap.get("lastNotifs", []) if snap.exists else []
        if notif_id in seen:                       # already processed
            return

        txn.set(
            doc_ref,
            {
                "subscription_status": new_status,
                "subscription_tier": plan["tier"],
                "expiresDateMs": tx.expiresDate if tx else None,
                "lastNotifs": seen + [notif_id],
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

        logger.error(f"LOG.INFO: Updated subscription status for user {firebase_uid} to {new_status} with plan {plan['tier']}")

    _update_if_new(fs.transaction())
    return jsonify(ok=True)
