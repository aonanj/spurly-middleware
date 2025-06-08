import os
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple, Any

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from flask import Blueprint, request, jsonify, current_app, g
from functools import wraps
from services.user_service import get_user, update_user, create_user, get_user_by_email 
from infrastructure.id_generator import generate_user_id

# Create blueprint
auth_bp = Blueprint('auth_bp', __name__, url_prefix='/api/auth')

logger = logging.getLogger(__name__)

# Import shared functions from social_auth.py
from .social_auth import (
    AuthError,
    ValidationError,
    handle_auth_errors,
    create_jwt_token,
)

# Initialize Firebase Admin SDK (do this once in your app initialization)
# Make sure to set the path to your service account key file
# cred = credentials.Certificate('path/to/your/firebase-service-account-key.json')
# firebase_admin.initialize_app(cred)

# Email validation regex
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

def validate_email(email: str) -> bool:
    """Validate email format"""
    return bool(EMAIL_REGEX.match(email))

def _get_user_id_from_token(id_token):
    decoded_token = firebase_auth.verify_id_token(id_token)
    return decoded_token['uid']

def verify_firebase_token(id_token: str) -> Dict[str, Any]:
    """
    Verify Firebase ID token and extract user information
    
    Args:
        id_token: Firebase ID token from client
        
    Returns:
        Decoded token with user information
        
    Raises:
        AuthError: If token is invalid or expired
    """

    try:

        admin_app = firebase_admin.get_app() # Get the default initialized Firebase app
        if not admin_app:
            raise AuthError("Firebase Admin SDK is not initialized", 500)

        decoded_token = firebase_auth.verify_id_token(id_token, check_revoked=True, app=admin_app)
        setattr(g, "user_id", decoded_token['uid'])  # Store token in Flask global for later use
        return {
            'user_id': decoded_token['uid'],
            'email': decoded_token.get('email'),
            'name': decoded_token.get('name'),
            'provider': decoded_token.get('firebase', {}).get('sign_in_provider', 'password')
        }
    except firebase_auth.ExpiredIdTokenError as e:
        logger.error(f"Firebase token has expired: {str(e)}")
        raise AuthError("Firebase token has expired", 401)
    except firebase_auth.RevokedIdTokenError as e:
        logger.error(f"Firebase token has been revoked: {str(e)}")
        raise AuthError("Firebase token has been revoked", 401)
    except firebase_auth.InvalidIdTokenError as e: 
        # This is the key exception for "invalid token" issues.
        # The error message 'e' often contains the specific reason.
        logger.error(f"FIREBASE_TOKEN_IS_INVALID: {str(e)}") 
        raise AuthError(f"Invalid Firebase token: {str(e)}", 401)
    except Exception as e: # Catch any other unexpected errors during verification
        logger.error(f"UNEXPECTED_FIREBASE_TOKEN_VERIFICATION_ERROR: {str(e)}", exc_info=True) # Log with stack trace
        raise AuthError(f"Unable to verify authentication token due to an unexpected error: {str(e)}", 401)


def create_or_update_user_from_firebase(firebase_user: Dict[str, Any], firebase_id_token) -> Dict[str, Any]:
    """
    Create or update user from Firebase authentication data
    
    Args:
        firebase_user: Decoded Firebase token data
        
    Returns:
        User data dictionary
    """

    if not getattr(g, "user_id", None):
        setattr(g, "user_id", generate_user_id(firebase_id_token))
    current_app.config['user_id'] = getattr(g, "user_id")

    user = get_user(getattr(g, "user_id"))
    if user:
        user_data = {}
        user_data['user_id'] = getattr(g, "user_id")
        if firebase_user['name'] and firebase_user['name'] != user.name:
            user_data['name'] = firebase_user['name']
        user_data['auth_provider'] = "password"
        user_data['auth_provider_id'] = getattr(g, "user_id")  # Use Firebase UID as provider ID
        if firebase_user['email'] and firebase_user['email'] != user.email:
            user_data['email'] = firebase_user['email']
        user_profile = update_user(**user_data)
    else:
        # Create new user
        user_profile = create_user(
            email=firebase_user['email'],
            auth_provider='password',
            auth_provider_id=getattr(g, "user_id"),  # Use Firebase UID as provider ID
            name=firebase_user.get('name', ''),# Use Firebase UID as provider ID
        )
    
    return user_profile.to_dict_alt()  # Convert to dict for response
# Routes

@auth_bp.route('/firebase/register', methods=['POST'])
@handle_auth_errors
def firebase_register():
    """Register new user with Firebase ID token"""
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required")
    
    firebase_id_token_1 = data.get('firebase_id_token')
    if not firebase_id_token_1:
        firebase_id_token = data.get('access_token', '').strip()
    else:
        firebase_id_token = firebase_id_token_1.strip()
    if not firebase_id_token:
        raise ValidationError("Firebase ID token is required")
    
    try:
        # Verify Firebase token
        firebase_user = verify_firebase_token(firebase_id_token)
        setattr(g, "user_id", firebase_user['uid']) 
        
        # Validate that this is a new registration (not a social login)
        if firebase_user['provider'] != 'password':
            raise ValidationError("Please use the appropriate social login endpoint")
        
        # Check if user already exists in your database
        email = firebase_user.get('email', '').strip().lower()
        existing_user = get_user_by_email(email)

        if existing_user:
            raise ValidationError("User already registered")

        # Create or update user in your database
        user_data = create_or_update_user_from_firebase(firebase_user, firebase_id_token)
        
        # Create your own JWT tokens
        access_token, refresh_token = create_jwt_token(
            user_id=user_data['user_id'],
            email=user_data['email'],
        )
        
        # Log successful registration
        logger.info(f"New user registered via Firebase: {user_data['user_id']}")
        
        return jsonify({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "user_id": user_data['user_id'],
            "email": user_data['email']
        }), 201
        
    except ValidationError:
        raise
    except AuthError:
        raise
    except Exception as e:
        logger.error(f"Firebase registration error: {str(e)}")
        raise AuthError("Unable to create account", 500)

@auth_bp.route('/firebase/login', methods=['POST'])
@handle_auth_errors
def firebase_login():
    """Login with Firebase ID token"""
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required")
    
    firebase_id_token_1 = data.get('firebase_id_token')
    if not firebase_id_token_1:
        firebase_id_token = data.get('access_token', '').strip()
    else:
        firebase_id_token = firebase_id_token_1.strip()
        
    email = data.get('email', '').strip().lower()  # Optional, for reference
    
    if not firebase_id_token:
        raise ValidationError("Firebase ID token is required")
    
    try:
        # Verify Firebase token
        firebase_user = verify_firebase_token(firebase_id_token)
        setattr(g, "user_id", firebase_user['uid']) 
              
        # Create or update user in your database
        user_data = get_user(firebase_user['uid'])
 
        if not user_data:
            raise AuthError("User not found. Please register first.", 404)

        access_token, refresh_token = create_jwt_token(
            user_id=user_data.user_id,
            email=user_data.email,
            name=user_data.name if user_data.name else None
        )
        
        # Log successful login
        logger.info(f"User logged in via Firebase: {user_data.user_id}")

        name = user_data.name if user_data.name else ""

        return jsonify({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "user_id": user_data.user_id,
            "email": user_data.email,
            "name": name    
        }), 200
        
    except AuthError:
        raise
    except Exception as e:
        logger.error(f"Firebase login error: {str(e)}")
        raise AuthError("Unable to authenticate", 500)

# Legacy routes (keep for backward compatibility during migration)

@auth_bp.route('/register', methods=['POST'])
@handle_auth_errors
def register():
    """[DEPRECATED] Register new user with email and password - Use /firebase/register instead"""
    return jsonify({
        "error": "This endpoint is deprecated. Please use Firebase authentication.",
        "message": "Use POST /api/auth/firebase/register with a Firebase ID token instead"
    }), 410  # 410 Gone

@auth_bp.route('/login', methods=['POST'])
@handle_auth_errors
def login():
    """[DEPRECATED] Login with email and password - Use /firebase/login instead"""
    return jsonify({
        "error": "This endpoint is deprecated. Please use Firebase authentication.",
        "message": "Use POST /api/auth/firebase/login with a Firebase ID token instead"
    }), 410  # 410 Gone

# Health check
@auth_bp.route('/health', methods=['GET'])
def auth_health():
    """Check if auth service is healthy"""
    # Check Firebase Admin SDK status
    firebase_status = "healthy"
    try:
        # Try to get Firebase app instance
        firebase_admin.get_app()
    except ValueError:
        firebase_status = "not initialized"
    
    return jsonify({
        "status": "healthy",
        "service": "firebase_auth",
        "firebase_admin_sdk": firebase_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200