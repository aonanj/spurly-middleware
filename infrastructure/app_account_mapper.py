import hashlib
import uuid
from google.cloud import firestore
from .clients import get_firestore_db
from .logger import get_logger

logger = get_logger(__name__)

_NAMESPACE = uuid.UUID("9e336bb4-6d07-4e5d-9d10-3da8e7460f42")   # same constant as in Swift

def make_app_account_token(firebase_uid: str) -> str:
    """
    Deterministic UUID generator – byte‑for‑byte identical to Swift.
    """
    ns_string = str(_NAMESPACE).upper()          # 1) "9E336BB4-6D07-4E5D-9D10-3DA8E7460F42"
    name_bytes = (ns_string + firebase_uid.lower()).encode("utf‑8")

    digest = hashlib.sha256(name_bytes).digest() # 2) SHA‑256
    b = bytearray(digest[:16])                   # take first 16 bytes

    b[6] = (b[6] & 0x0F) | 0x50                 # 3) set version 5 bits
    b[8] = (b[8] & 0x3F) | 0x80                 #    set RFC variant bits

    return str(uuid.UUID(bytes=bytes(b)))        # 4) RFC‑4122 UUID string



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


