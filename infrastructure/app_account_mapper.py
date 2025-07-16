import hashlib
import uuid
from google.cloud import firestore
from .clients import get_firestore_db
from .logger import get_logger

logger = get_logger(__name__)

import hashlib
import uuid

def make_app_account_token(user_id: str) -> str:
    # Use the same fixed namespace UUID
    namespace = uuid.UUID('9e336bb4-6d07-4e5d-9d10-3da8e7460f42')
    
    # Get the namespace UUID bytes (16 bytes)
    ns_bytes = namespace.bytes
    
    # Get the user ID as UTF-8 bytes
    id_bytes = user_id.encode('utf-8')
    
    # Create SHA256 hash
    hasher = hashlib.sha256()
    hasher.update(ns_bytes)
    hasher.update(id_bytes)
    digest = hasher.digest()
    
    # Take first 16 bytes
    bytes_list = list(digest[:16])
    
    # Set version 5 and variant bits (same as Swift)
    bytes_list[6] = (bytes_list[6] & 0x0F) | 0x50  # version 5
    bytes_list[8] = (bytes_list[8] & 0x3F) | 0x80  # variant bits
    
    # Create UUID from bytes
    result_uuid = uuid.UUID(bytes=bytes(bytes_list))
    
    return str(result_uuid)



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


