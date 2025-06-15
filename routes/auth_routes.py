import os
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple, Any

import firebase_admin
from firebase_admin import auth as firebase_admin_auth
from flask import Blueprint, request, jsonify, current_app, g
from functools import wraps
import requests
import jwt
from services.user_service import get_user, update_user, create_user, get_user_by_email 
from services.connection_service import clear_active_connection_firestore

# Create blueprint
auth_bp = Blueprint('auth_bp', __name__, url_prefix='/api/auth')

logger = logging.getLogger(__name__)

# Import shared functions from social_auth.py

# Initialize Firebase Admin SDK (do this once in your app initialization)
# Make sure to set the path to your service account key file
# cred = credentials.Certificate('path/to/your/firebase-service-account-key.json')
# firebase_admin.initialize_app(cred)

# Email validation regex
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


class AuthError(Exception):
    """Custom authentication error"""
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class ValidationError(Exception):
    """Custom validation error"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

def verify_token(f):
    """Decorator to verify JWT token"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            raise AuthError("Authorization header is required")
        
        parts = auth_header.split()
        if parts[0].lower() != 'bearer' or len(parts) != 2:
            raise AuthError("Invalid authorization header format")
        
        token = parts[1]
        secret_key = os.environ.get('JWT_SECRET_KEY')

        if not secret_key:
            raise AuthError("JWT configuration missing", 500)
        
        try:
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])
            
            # Verify token type
            if payload.get('type') != 'access':
                raise AuthError("Invalid token type")
            
            user_id = ""
            if 'user_id' in payload:
                user_id = payload.get('user_id')
            elif 'sub' in payload:
                user_id = payload.get('sub')
            elif 'uid' in payload:
                user_id = payload.get('uid')
            setattr(g, "user_id", user_id)
            current_app.config['user_id'] = user_id

            return f(*args, **kwargs)
            
        except jwt.ExpiredSignatureError:
            raise AuthError("Token has expired")
        except jwt.InvalidTokenError:
            raise AuthError("Invalid token")
            
    return decorated_function

def handle_auth_errors(f):
    """Decorator to handle authentication errors"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except AuthError as e:
            logger.warning(f"Authentication error in {f.__name__}: {e.message}")
            return jsonify({"error": e.message}), e.status_code
        except ValidationError as e:
            logger.warning(f"Validation error in {f.__name__}: {e.message}")
            return jsonify({"error": e.message}), e.status_code
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token in {f.__name__}: {str(e)}")
            return jsonify({"error": "Invalid token"}), 401
        except requests.RequestException as e:
            logger.error(f"External API error in {f.__name__}: {str(e)}")
            return jsonify({"error": "External service temporarily unavailable"}), 503
        except Exception as e:
            logger.exception(f"Unexpected error in {f.__name__}: {str(e)}")
            return jsonify({"error": "Internal server error"}), 500
    return decorated_function

def validate_email(email: str) -> bool:
    """Validate email format"""
    return bool(EMAIL_REGEX.match(email))

def _get_user_id_from_token(id_token):
    decoded_token = firebase_admin_auth.verify_id_token(id_token)
    return decoded_token['uid']

def create_jwt_token(user_id: str, email: str, name: Optional[str] = None, 
                    provider: Optional[str] = None) -> Tuple[str, str]:
    """Create JWT access and refresh tokens"""
    secret_key = os.environ.get('JWT_SECRET_KEY')
    if not secret_key:
       raise AuthError("JWT configuration missing", 500)
    
    now = datetime.now(timezone.utc)
    
    # Access token payload (short-lived)
    access_payload = {
        'user_id': user_id,
        'email': email,
        'name': name,
        'provider': provider,
        'type': 'access',
        'iat': now,
        'exp': now + timedelta(hours=3),
        'jti': os.urandom(16).hex()  # Unique token ID
    }
    
    # Refresh token payload (long-lived)
    refresh_payload = {
        'user_id': user_id,
        'type': 'refresh',
        'iat': now,
        'exp': now + timedelta(days=30),
        'jti': os.urandom(16).hex()
    }
    
    access_token = jwt.encode(access_payload, secret_key, algorithm='HS256')
    refresh_token = jwt.encode(refresh_payload, secret_key, algorithm='HS256')
    
    return access_token, refresh_token

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

        decoded_token = firebase_admin_auth.verify_id_token(id_token, check_revoked=True, app=admin_app)
        user_id = ""
        if 'user_id' in decoded_token:
            user_id = decoded_token.get('user_id')
        elif 'sub' in decoded_token:
            user_id = decoded_token.get('sub')
        elif 'uid' in decoded_token:
            user_id = decoded_token.get('uid')
        setattr(g, "user_id", user_id)
        
        user_email = ""
        if 'email' in decoded_token:
            user_email = decoded_token.get('email')
        elif 'user_email' in decoded_token:
            user_email = decoded_token.get('user_email')
        setattr(g, "user_email", user_email)
        setattr(g, "auth_claims", decoded_token)
        return {
            'user_id': user_id,
            'email': user_email,
            'name': decoded_token.get('name'),
            'auth_provider': decoded_token.get('firebase', {}).get('sign_in_provider', 'password')
        }
    except firebase_admin_auth.ExpiredIdTokenError as e:
        logger.error(f"Firebase token has expired: {str(e)}")
        raise AuthError("Firebase token has expired", 401)
    except firebase_admin_auth.RevokedIdTokenError as e:
        logger.error(f"Firebase token has been revoked: {str(e)}")
        raise AuthError("Firebase token has been revoked", 401)
    except firebase_admin_auth.InvalidIdTokenError as e: 
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
        setattr(g, "user_id", firebase_user['user_id'])  # Ensure user_id is set from token
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
            user_id=getattr(g, "user_id"),
            email=firebase_user['email'],
            auth_provider='password',
            auth_provider_id=getattr(g, "user_id"),  # Use Firebase UID as provider ID
            name=firebase_user.get('name', ''),# Use Firebase UID as provider ID
        )
    
    return user_profile.to_dict()  # Convert to dict for response
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
        setattr(g, "user_id", firebase_user['user_id']) 
        
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
        setattr(g, "user_id", firebase_user['user_id']) 
        
                      
        # Create or update user in your database
        user_data = get_user(firebase_user['user_id'])

        if not user_data:
            raise AuthError("User not found. Please register first.", 404)

        access_token, refresh_token = create_jwt_token(
            user_id=user_data.user_id,
            email=user_data.email,
            name=user_data.name if user_data.name else None
        )
        
        clear_active_connection = clear_active_connection_firestore(user_data.user_id)
        setattr(g, "active_connection_id", clear_active_connection.get("connection_id"))

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

@auth_bp.route('/logout', methods=['POST'])
@verify_token
@handle_auth_errors
def logout():
    """Logout user and invalidate tokens"""
    
    user_id = getattr(g, "user_id", None)
    if not user_id:
        if not user_id:
            user_id = current_app.config.get("user_id", None)
            if not user_id:
                data = request.get_json()
                user_id = data.get('user_id', None)
                if not user_id:
                    return jsonify({"error": "Authentication error"}), 401

    try:
        clear_active_connection_firestore(user_id)

        setattr(g, "user_id", None)
        setattr(g, "email", None)
        setattr(g, "name", None)
        setattr(g, "auth_provider", None)
        setattr(g, "auth_provider_id", None)
        setattr(g, "active_connection_id", None)
        
        return jsonify({"message": "Successfully logged out"}), 200
    except Exception as e:
        logger.error(f"Logout error for user {user_id}: {str(e)}")
        logger.error(f"Active connection ID not cleared for user {user_id}")
        raise AuthError("Unable to logout", 500)


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