# firebase_auth.py
import os
from functools import wraps
from flask import request, g, jsonify
import firebase_admin
from firebase_admin import auth as fb_auth, credentials

def init_firebase(app):
    """
    Call once at startup (e.g. from create_app()).
    Uses GOOGLE_APPLICATION_CREDENTIALS or explicit path.
    """
    if not firebase_admin._apps:
        cred_path = os.environ.get("GOOGLE_CLOUD_FIREBASE_CREDS")
        cred = credentials.Certificate(cred_path) if cred_path else credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)

def require_firebase_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # 1. Extract bearer token
        auth_header = request.headers.get("Authorization", "")
        scheme, _, id_token = auth_header.partition(" ")
        if scheme.lower() != "bearer" or not id_token:
            return jsonify({"error": "Missing or invalid auth header"}), 401

        # 2. Verify & decode
        try:
            decoded = fb_auth.verify_id_token(id_token, check_revoked=True)
        except fb_auth.RevokedIdTokenError:
            return jsonify({"error": "Token revoked"}), 401
        except fb_auth.ExpiredIdTokenError:
            return jsonify({"error": "Token expired"}), 401
        except fb_auth.InvalidIdTokenError:
            return jsonify({"error": "Invalid ID token"}), 401

        # 3. Stash in request context
        setattr(g, "user_id", decoded["user_id"])
        setattr(g, "auth_claims", decoded)
        return fn(*args, **kwargs)
    return wrapper
