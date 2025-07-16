import hashlib
import uuid
from google.cloud import firestore
from .clients import get_firestore_db
from .logger import get_logger

logger = get_logger(__name__)

_NAMESPACE = uuid.UUID("9e336bb4-6d07-4e5d-9d10-3da8e7460f42")  # ← same constant as in Swift

def make_app_account_token(firebase_uid: str) -> str:
    """
    Python port of the Swift helper in SubscriptionManager.swift.
    Produces the identical UUID (v‑5 style, SHA‑256‑based).
    """
    # 1) Upper‑case, dash‑separated namespace ‑ exactly what `uuidString` returns on iOS
    ns_string = str(_NAMESPACE).upper()          # e.g. "9E336BB4-6D07-4E5D-9D10-3DA8E7460F42"

    # 2) Lower‑case Firebase UID (Swift uses `lowercased()`)
    name_bytes = (ns_string + firebase_uid.lower()).encode("utf‑8")

    # 3) SHA‑256 ➞ take first 16 bytes
    digest = hashlib.sha256(name_bytes).digest()
    b = bytearray(digest[:16])

    # 4) RFC‑4122 tweaks: set version 5 and RFC variant bits
    b[6] = (b[6] & 0x0F) | 0x50      # version 5
    b[8] = (b[8] & 0x3F) | 0x80      # variant

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
    ##DEBUG
    logger.error(f"Looking up firebase_uid for appAccountToken {token}: found {snap.to_dict()}")
    logger.error(f"FIREBASE UID: {snap.get('firebase_uid') if snap.exists else 'NOT FOUND'}")
    return snap.get("firebase_uid") if snap.exists else None


