import os
import re
import logging
from datetime import datetime, timezone
from typing import Dict, Any

import firebase_admin
from firebase_admin import auth as firebase_admin_auth
from flask import Blueprint, request, jsonify, current_app, g
import jwt
from infrastructure.token_validator import verify_token, handle_all_errors, create_jwt_token, get_formatted_auth_provider, AuthError, ValidationError
from services.user_service import get_user, update_user, create_user, get_user_by_email 
from services.connection_service import clear_active_connection_firestore
from class_defs.profile_def import UserProfile

# Create blueprint
auth_bp = Blueprint('auth_bp', __name__, url_prefix='/api/auth')

logger = logging.getLogger(__name__)


# Email validation regex
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

def validate_email(email: str) -> bool:
    """Validate email format"""
    return bool(EMAIL_REGEX.match(email))


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
        
        json_dict = { 'user_id': user_id }
        
        user_email = ""
        if 'email' in decoded_token:
            user_email = decoded_token.get('email')
        elif 'user_email' in decoded_token:
            user_email = decoded_token.get('user_email')
        
        if user_email != "":
            setattr(g, "email", user_email)
            json_dict['email'] = user_email
            
        name = ""
        if 'name' in decoded_token:
            name = decoded_token.get('name')
        elif 'user_name' in decoded_token:
            name = decoded_token.get('user_name')
        
        if name != "":
            setattr(g, "name", name)
            json_dict['name'] = name
        
        auth_provider = ""    
        if 'auth_claims' in decoded_token:
            auth_provider = decoded_token.get('auth_claims', {}).get('auth_provider')
            setattr(g, 'auth_provider', auth_provider)
            json_dict['auth_provider'] = auth_provider

        return json_dict

    
    except firebase_admin_auth.ExpiredIdTokenError as e:
        logger.error(f"Firebase token has expired: {str(e)}")
        raise AuthError("Firebase token has expired", 401)
    except firebase_admin_auth.RevokedIdTokenError as e:
        logger.error(f"Firebase token has been revoked: {str(e)}")
        raise AuthError("Firebase token has been revoked", 401)
    except firebase_admin_auth.InvalidIdTokenError as e: 
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
    
    auth_provider = firebase_user.get('auth_provider', 'password')
    
    if user:
        user_data = {}
        user_data['user_id'] = getattr(g, "user_id")
        if firebase_user.get('name') and firebase_user.get('name') != user.name:
            user_data['name'] = firebase_user['name']
        user_data['auth_provider'] = auth_provider
        user_data['auth_provider_id'] = getattr(g, "user_id")
        if firebase_user.get('email') and firebase_user.get('email') != user.email:
            user_data['email'] = firebase_user['email']
        user_profile = update_user(**user_data)
    else:
        # Create new user
        user_profile = create_user(
            user_id=getattr(g, "user_id"),
            email=firebase_user['email'],
            auth_provider=auth_provider,
            auth_provider_id=getattr(g, "user_id"),  # Use Firebase UID as auth_provider ID
            name=firebase_user.get('name', ''),# Use Firebase UID as auth_provider ID
        )
    
    return user_profile.to_dict()  # Convert to dict for response
# Routes

@auth_bp.route('/firebase/register', methods=['POST'])
@handle_all_errors
def firebase_register():
    """Register new user with Firebase ID token"""
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    
    data = request.get_json()
    if not data:
        logger.error(f"Request JSON body is empty. Request data: {data}")
        raise ValidationError("Request body is required")
    
    firebase_id_token_1 = data.get('firebase_id_token')
    if not firebase_id_token_1:
        firebase_id_token = data.get('access_token', '').strip()
    else:
        firebase_id_token = firebase_id_token_1.strip()
    if not firebase_id_token:
        logger.error(f"NO firebase ID token. Request data: {data}")
        raise ValidationError("Firebase ID token is required")
    
    try:
        firebase_user = verify_firebase_token(firebase_id_token)
        setattr(g, "user_id", firebase_user['user_id']) 
        # Validate that this is a new registration (not a social login)
        if firebase_user.get('auth_provider'):
            auth_provider = firebase_user['auth_provider']
        elif data.get('auth_provider'):
            auth_provider = data.get('auth_provider')
        elif data.get('auth_provider'):
            auth_provider = data.get('auth_provider')
        else:
            auth_provider = "password"


        email = firebase_user.get('email', '').strip().lower()
        existing_user = get_user_by_email(email)

        if existing_user:
            raise ValidationError("User already registered")

        # Create or update user in your database
        ##user_data = create_or_update_user_from_firebase(firebase_user, firebase_id_token)
        user_data = get_user(firebase_user['user_id'])
        
        if not user_data:
            raise ValidationError("User not found")
        
        # Convert to dict if it's a UserProfile object
        user_dict = user_data.to_dict() if isinstance(user_data, UserProfile) else user_data
        user_id = user_dict['user_id']
        
        # Create your own JWT tokens
        access_token, refresh_token = create_jwt_token(
            user_id=user_id,
            email=user_dict['email'],
            provider=auth_provider
        )
        
        firebase_custom_token = None
        try:
            firebase_custom_token = firebase_admin_auth.create_custom_token(user_id)
            if(isinstance(firebase_custom_token, bytes)):
                firebase_custom_token = firebase_custom_token.decode('utf-8')
        except Exception as e:
            logger.error(f"Error creating Firebase custom token: {e}")
        
        json_response = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "user_id": user_id,
            "email": email
        }
        
        if user_dict.get('name'):
            json_response['name'] = user_dict['name']
        
        if firebase_custom_token:
            json_response['firebase_custom_token'] = firebase_custom_token
            
        if auth_provider and auth_provider != "":
            json_response['auth_provider'] = get_formatted_auth_provider(auth_provider)

        return json_response, 200
        
    except ValidationError:
        logger.error("Firebase registration validation error", exc_info=True)
        raise
    except AuthError:
        logger.error("Firebase registration token authentication error", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Firebase registration error: {str(e)}")
        raise AuthError("Unable to create account", 500)

@auth_bp.route('/firebase/login', methods=['POST'])
@handle_all_errors
def firebase_login():
    """Login with Firebase ID token"""
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required")
    
    if data.get('firebase_id_token'):
        firebase_id_token = data.get('firebase_id_token', '').strip()
    elif data.get('access_token'):
        firebase_id_token = data.get('access_token', '').strip()
    else:
        raise ValidationError("Firebase ID token is required")
    
    try:
        # Verify Firebase token
        firebase_user = verify_firebase_token(firebase_id_token)
        user_id = ""
        if firebase_user.get('user_id'):
            user_id = firebase_user.get('user_id', '').strip()
        elif data.get('user_id'):
            user_id = data.get('user_id', '').strip()
        elif getattr(g, "user_id", None):
            user_id = getattr(g, "user_id", None)
        else:
            raise ValidationError("User ID is required")
        
        setattr(g, "user_id", user_id)
        current_app.config['user_id'] = user_id
        
        email = ""
        if firebase_user.get('email'):
            email = firebase_user.get('email', '').strip().lower()
            setattr(g, "email", email)
        elif data.get('email'):
            email = data.get('email', '').strip().lower()  
            setattr(g, "email", email)
        elif getattr(g, "user_email", None):
            email = getattr(g, "user_email", None)
            
        auth_provider = firebase_user.get('auth_provider', 'password')
        setattr(g, "auth_provider", auth_provider)
        
                      
        # Create or update user in your database
        user_data = get_user(firebase_user['user_id'])
        if user_data and user_data.auth_provider and 'password' not in user_data.auth_provider:
            logger.error(f"LOG.ERROR: User {user_data.user_id} (email {user_data.email}) attempted to sign in with password but is registered with {user_data.auth_provider}")
            raise AuthError("email registered with different provider. sign in using: " + user_data.auth_provider)

        if not user_data:
            user_data = create_or_update_user_from_firebase(firebase_user, firebase_id_token)
        
        user_dict = user_data.to_dict() if isinstance(user_data, UserProfile) else user_data

        if not user_id:
            raise ValidationError("User ID is required for token creation")

        if not email:
            raise ValidationError("Email is required for token creation")
        

        access_token, refresh_token = create_jwt_token(
            user_id=user_id,
            email=email,
            provider=auth_provider
        )
        
        clear_active_connection = clear_active_connection_firestore(user_id)
        setattr(g, "active_connection_id", clear_active_connection.get("connection_id"))
        
        
        
        if user_dict.get('name') and user_dict['name'] != '':
            setattr(g, "name", user_dict['name'])
            name = user_dict['name']
    
        json_response = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "user_id": user_id,
            "email": email
        }
        if user_dict.get('name'):
            json_response['name'] = user_dict['name']

        json_response['auth_provider'] = get_formatted_auth_provider(auth_provider)


        # Log successful login
        logger.error(f"User logged in via Firebase: {user_id}")


        return json_response, 200
        
    except AuthError:
        raise
    except Exception as e:
        logger.error(f"Firebase login error: {str(e)}")
        raise AuthError("Unable to authenticate", 500)

@auth_bp.route('/logout', methods=['POST'])
@handle_all_errors
@verify_token
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
        
        return jsonify({
            "success": True,
            "message": "Successfully logged out"}), 200
        
    except Exception as e:
        logger.error(f"Logout error for user {user_id}: {str(e)}")
        logger.error(f"Active connection ID not cleared for user {user_id}")
        return jsonify({
            "success": False,
            "message": f"Failed to clear active connection for user {user_id}"
        }), 500

@auth_bp.route('/refresh', methods=['POST'])
@handle_all_errors
def refresh_token():
    """Refresh an expired access token using a refresh token"""
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required")
    
    refresh_token = data.get('refresh_token')
    if not refresh_token:
        raise ValidationError("refresh_token is required")
    
    secret_key = os.environ.get('JWT_SECRET_KEY')
    if not secret_key:
        raise AuthError("JWT configuration missing", 500)
    
    try:
        # Decode refresh token
        payload = jwt.decode(refresh_token, secret_key, algorithms=['HS256'])
        
        # Verify token type
        if payload.get('type') != 'refresh':
            raise AuthError("Invalid token type - refresh token required", 401)
        
        # Get user to ensure they still exist
        user_id = payload.get('user_id')
        user = get_user(user_id)
        if not user:
            raise AuthError("User account no longer exists", 401)
        
        # Create new access token (but not a new refresh token)
        new_access_token, _ = create_jwt_token(
            user_id=user.user_id,
            email=user.email,
            name=user.name,
            provider=user.auth_provider
        )
        
        return jsonify({
            "access_token": new_access_token,
            "token_type": "Bearer",
            "expires_in": 3600
        }), 200
        
    except jwt.ExpiredSignatureError:
        raise AuthError("Refresh token has expired - please login again", 401)
    except jwt.InvalidTokenError:
        raise AuthError("Invalid refresh token", 401)
        
@auth_bp.route('/check-email', methods=['POST'])
@handle_all_errors
def check_email_availability():
    """Check if an email is already registered"""
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email:
        raise ValidationError("Email is required")
    
    if not validate_email(email):
        raise ValidationError("Invalid email format")
    
    # Check if user exists with this email
    existing_user = get_user_by_email(email)
    
    return jsonify({
        "available": existing_user is None,
        "email": email
    }), 200


# DEPRECATED: Legacy routes (keep for backward compatibility during migration)

@auth_bp.route('/register', methods=['POST'])
@handle_all_errors
def register():
    """[DEPRECATED] Register new user with email and password - Use /firebase/register instead"""
    return jsonify({
        "error": "This endpoint is deprecated. Please use Firebase authentication.",
        "message": "Use POST /api/auth/firebase/register with a Firebase ID token instead"
    }), 410  # 410 Gone

@auth_bp.route('/login', methods=['POST'])
@handle_all_errors
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