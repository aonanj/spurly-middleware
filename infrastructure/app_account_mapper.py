import hashlib
import uuid
from google.cloud import firestore
from .clients import get_firestore_db

_NAMESPACE = uuid.UUID("9e336bb4-6d07-4e5d-9d10-3da8e7460f42")

def make_app_account_token(firebase_uid: str) -> str:
    """
    Deterministically derive the appAccountToken UUID from a Firebase UID.
    Matches the Swift implementation in SubscriptionManager.swift.
    """
    name_bytes = (_NAMESPACE.hex + firebase_uid.lower()).encode("utf‑8")
    digest = hashlib.sha256(name_bytes).digest()

    # Build a RFC 4122 v5‑compatible UUID (set version & variant bits)
    b = bytearray(digest[:16])
    b[6] = (b[6] & 0x0F) | 0x50        # version 5
    b[8] = (b[8] & 0x3F) | 0x80        # variant
    return str(uuid.UUID(bytes=bytes(b)))

# Cloud Function / backend endpoint when the user signs in
def ensure_token_mapping(firebase_uid: str):
    
    fs = get_firestore_db()
    token = make_app_account_token(firebase_uid)
    fs.collection("user_tokens").document(token).set({
        "firebase_uid": firebase_uid,
        "created_at": firestore.SERVER_TIMESTAMP,
    })

def uid_from_token(token: str) -> str | None:
    fs = get_firestore_db()
    snap = fs.collection("user_tokens").document(token).get()
    return snap.get("firebase_uid") if snap.exists else None


