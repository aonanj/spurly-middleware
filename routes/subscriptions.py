# subscriptions.py ― Flask version
import os
from flask import Blueprint, request, jsonify, abort
from google.cloud import firestore
from appstoreserverlibrary.signed_data_verifier import (
    SignedDataVerifier,
    VerificationException,
)
from appstoreserverlibrary.models import Environment
ROOT_CERT_PATH = os.environ.get("APPLE_ROOT_CA_PATH", "resources/AppleRootCA-G3.cer")
BUNDLE_ID = os.getenv("APPLE_BUNDLE_ID", "com.phaeton-order.spurly")        # safety guard
ENV_MODE  = os.getenv("ENV", "development")                # prod | staging | dev

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
        abort(400, "Missing signedPayload")

    # -- Verify JWS signature & basic bundle‑id guardrail --------------------
    try:
        decoded = verifier.verify_and_decode_notification(
            signed_payload=signed
        )
    except VerificationException as exc:
        abort(400, f"Signature verification failed: {exc}")
        
    uid = None
    env = None
    renew = None
    notif_id = None
    tx = None
    if decoded and decoded.data:
        env         = decoded.data.environment                      # Sandbox | Production
        notif_id    = decoded.notificationUUID
        
        if not decoded.data.signedTransactionInfo or not decoded.data.signedRenewalInfo:
            abort(400, "Missing signedTransactionInfo")
            
        tx          = verifier.verify_and_decode_signed_transaction(decoded.data.signedTransactionInfo)
        renew       = verifier.verify_and_decode_renewal_info(decoded.data.signedRenewalInfo)
        uid         = tx.appAccountToken             # set on‑device at purchase

    if not uid:
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
    doc_ref = fs.collection("subscriptions").document(uid)

    @firestore.transactional
    def _update_if_new(txn):
        snap = doc_ref.get(transaction=txn)
        seen = snap.get("lastNotifs", []) if snap.exists else []
        if notif_id in seen:                       # already processed
            return

        txn.set(
            doc_ref,
            {
                "status": new_status,
                "expiresDateMs": tx.expiresDate if tx else None,
                "lastNotifs": seen + [notif_id],
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

    _update_if_new(fs.transaction())
    return jsonify(ok=True)
