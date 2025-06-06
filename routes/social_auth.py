import os
import time
import json
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps, lru_cache
from typing import Dict, Optional, Tuple, Any

import jwt
import jwt.algorithms
import requests
from flask import Blueprint, request, jsonify, current_app, g
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate

from services.user_service import get_user, update_user, create_user

# Create blueprint
social_auth_bp = Blueprint('social_auth_bp', __name__, url_prefix='/api/social_auth')

# Constants
APPLE_AUTH_URL = "https://appleid.apple.com/auth/keys"
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
FACEBOOK_DEBUG_TOKEN_URL = "https://graph.facebook.com/debug_token"
FACEBOOK_USER_URL = "https://graph.facebook.com/v12.0/me"

# Cache TTL for public keys (1 hour)
KEYS_CACHE_TTL = 3600

## TODO: If user deauthorizes app on Apple, Google, or Facebook, we should handle that gracefully



logger = logging.getLogger(__name__)

def _jwk_to_rsa_public_key(jwk: Dict[str, str]) -> RSAPublicKey:
    """
    Convert an Apple JWK entry to an `RSAPublicKey`.

    Apple’s keys never include the private exponent “d”, so
    `RSAAlgorithm.from_jwk()` returns a public key.  We still
    guard with `isinstance` so we crash loudly if Apple’s format
    changes in the future.
    """
    key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
    if not isinstance(key, RSAPublicKey):
        raise ValueError("Expected an RSA *public* key, got a private key.")
    return key

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

@lru_cache(maxsize=128)
def get_google_public_keys() -> Dict[str, Any]:
    """Fetch and cache Google's public keys"""
    try:
        response = requests.get(GOOGLE_CERTS_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch Google public keys: {str(e)}")
        raise AuthError("Unable to verify token at this time", 503)

@lru_cache(maxsize=128)
def get_apple_public_keys() -> Dict[str, Any]:
    """Fetch and cache Apple's public keys"""
    try:
        response = requests.get(APPLE_AUTH_URL, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch Apple public keys: {str(e)}")
        raise AuthError("Unable to verify token at this time", 503)

def verify_google_token(id_token: str) -> Dict[str, Any]:
    """Verify Google ID token with proper signature validation"""
    try:
        # Get unverified header to find key ID
        unverified_header = jwt.get_unverified_header(id_token)
        if 'kid' not in unverified_header:
            raise AuthError("Invalid token header")
        
        # Get Google's public keys
        public_keys = get_google_public_keys()
        
        # Find the key that matches
        key_id = unverified_header['kid']
        if key_id not in public_keys:
            # Clear cache and retry once
            get_google_public_keys.cache_clear()
            public_keys = get_google_public_keys()
            if key_id not in public_keys:
                raise AuthError("Token signing key not found")
        
        # Get the public key
        public_key = public_keys[key_id]
        
        # Decode and verify the token
        decoded_token = jwt.decode(
            id_token,
            public_key,
            algorithms=['RS256'],
            audience=current_app.config.get('GOOGLE_CLIENT_ID'),
            options={"verify_exp": True}
        )
        
        # Additional validation
        if decoded_token.get('iss') not in ['accounts.google.com', 'https://accounts.google.com']:
            raise AuthError("Invalid token issuer")
        
       
        return decoded_token
        
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidAudienceError:
        raise AuthError("Token was not issued for this application")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {str(e)}")

def verify_apple_token(identity_token: str) -> Dict[str, Any]:
    """Verify Apple identity token with proper signature validation"""
    try:
        # Get unverified header to find key ID
        unverified_header = jwt.get_unverified_header(identity_token)
        if 'kid' not in unverified_header:
            raise AuthError("Invalid token header")
        
        # Get Apple's public keys
        keys_response = get_apple_public_keys()
        apple_keys = keys_response.get('keys', [])
        
        # Find the matching key
        key_id = unverified_header['kid']
        matching_key = None
        for key in apple_keys:
            if key['kid'] == key_id:
                matching_key = key
                break
        
        if not matching_key:
            # Clear cache and retry once
            get_apple_public_keys.cache_clear()
            keys_response = get_apple_public_keys()
            apple_keys = keys_response.get('keys', [])
            for key in apple_keys:
                if key['kid'] == key_id:
                    matching_key = key
                    break
        
        if not matching_key:
            raise AuthError("Token signing key not found")
        
        # Convert JWK to PEM format
        rsa_public_key: RSAPublicKey = _jwk_to_rsa_public_key(matching_key)
        # Convert the RSA key to PEM format for jwt.decode()
        public_key_pem = rsa_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        # Decode and verify the token
        decoded_token = jwt.decode(
            identity_token,
            public_key_pem,
            algorithms=['RS256'],
            audience=current_app.config.get('APPLE_BUNDLE_ID'),
            options={"verify_exp": True}
        )
        
        # Additional validation
        if decoded_token.get('iss') != 'https://appleid.apple.com':
            raise AuthError("Invalid token issuer")
        
        # Verify token is not too old (Apple tokens are short-lived)
        auth_time = decoded_token.get('auth_time', 0)
        if time.time() - auth_time > 86400:  # 24 hours
            raise AuthError("Token is too old")
        
        return decoded_token
        
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidAudienceError:
        raise AuthError("Token was not issued for this application")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {str(e)}")

def verify_facebook_token(access_token: str) -> Tuple[Dict[str, Any], bool]:
    """Verify Facebook access token and get user info"""
    app_id = current_app.config.get('FACEBOOK_APP_ID')
    app_secret = current_app.config.get('FACEBOOK_APP_SECRET')
    
    if not app_id or not app_secret:
        raise AuthError("Facebook authentication not configured", 500)
    
    # Verify token with Facebook
    verify_params = {
        'input_token': access_token,
        'access_token': f"{app_id}|{app_secret}"
    }
    
    verify_response = requests.get(FACEBOOK_DEBUG_TOKEN_URL, params=verify_params, timeout=10)
    verify_response.raise_for_status()
    
    debug_data = verify_response.json().get('data', {})
    
    # Validate token
    if not debug_data.get('is_valid'):
        raise AuthError("Invalid Facebook token")
    
    if str(debug_data.get('app_id')) != str(app_id):
        raise AuthError("Token was not issued for this application")
    
    # Check token expiration
    expires_at = debug_data.get('expires_at', 0)
    if expires_at > 0 and expires_at < time.time():
        raise AuthError("Token has expired")
    
    # Get user info
    user_params = {
        'access_token': access_token,
        'fields': 'id,name,email,picture.type(large)'
    }
    
    user_response = requests.get(FACEBOOK_USER_URL, params=user_params, timeout=10)
    user_response.raise_for_status()
    
    user_data = user_response.json()
    
    # Check if we have email permission
    has_email = 'email' in debug_data.get('scopes', [])
    
    return user_data, has_email

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

def get_or_create_user(provider: str, provider_user_id: str, email: str, 
                      name: Optional[str] = None) -> Dict[str, Any]:
    """Get or create user in database"""
    # Import your user model/service here
    # from models.user import User
    # from services.user_service import UserService

    setattr(g, "provider_user_id", provider_user_id)
    current_app.config['user_id'] = getattr(g, "user_id", None)

    user = get_user(provider_user_id)
    if user:
        user_data = {}
        user_data['user_id'] = getattr(g, "user_id", None)
        if name and name != user.name:
            user_data['name'] = name
        user_data['auth_provider'] = provider
        user_data['auth_provider_id'] = getattr(g, "user_id", None)  # Use Firebase UID as provider ID
        if email and email != user.email:
            user_data['email'] = email
        user_profile = update_user(**user_data)
    else:
        # Create new user
        user_profile = create_user(
            email=email,
            auth_provider=provider,
            auth_provider_id=getattr(g, "user_id"),
            name=name,
        )
    
    return user_profile.to_dict_alt() 

# Routes

@social_auth_bp.route('/google', methods=['POST'])
@handle_auth_errors
def google_auth():
    """Authenticate user with Google ID token"""
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required")
    
    id_token = data.get('id_token')
    if not id_token:
        raise ValidationError("id_token is required")
    
    # Verify token
    token_data = verify_google_token(id_token)
    
    # Extract user information
    email = token_data.get('email')
    name = token_data.get('name')
    google_user_id = token_data.get('sub')
    
    # Validate required fields
    if not google_user_id:
        raise ValidationError("Google user ID not found in token")
    if not email:
        raise ValidationError("Email not found in token")
    
    # Get or create user
    user_data = get_or_create_user(
        provider='google',
        provider_user_id=google_user_id,
        email=email,
        name=name,
       )
    
    # Create tokens
    access_token, refresh_token = create_jwt_token(
        user_id=user_data['user_id'],
        email=user_data['email'],
        name=user_data['name'],
        provider='google'
    )
    
    # Log successful authentication
    logger.info(f"Successful Google authentication for user: {user_data['user_id']}")
    
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "user_id": user_data['user_id'],
        "email": user_data['email'],
        "name": user_data['name']
    }), 200

@social_auth_bp.route('/apple', methods=['POST'])
@handle_auth_errors
def apple_auth():
    """Authenticate user with Apple Sign In"""
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required")
    
    identity_token = data.get('identity_token')
    authorization_code = data.get('authorization_code')
    
    if not identity_token:
        raise ValidationError("identity_token is required")
    if not authorization_code:
        raise ValidationError("authorization_code is required")
    
    # Verify token
    token_data = verify_apple_token(identity_token)
    
    # Extract user information
    apple_user_id = token_data.get('sub')
    email = token_data.get('email') or data.get('email')
    
    # Validate required fields
    if not apple_user_id:
        raise ValidationError("Apple user ID not found in token")
    if not email:
        raise ValidationError("Email is required but not provided")
    
    # Build name from provided data
    full_name = data.get('full_name', {})
    name_parts = []
    if full_name.get('given_name'):
        name_parts.append(full_name['given_name'])
    if full_name.get('family_name'):
        name_parts.append(full_name['family_name'])
    name = ' '.join(name_parts) if name_parts else None
    
    # Get or create user
    user_data = get_or_create_user(
        provider='apple',
        provider_user_id=apple_user_id,
        email=email,
        name=name
    )
    
    # Create tokens
    access_token, refresh_token = create_jwt_token(
        user_id=user_data['user_id'],
        email=user_data['email'],
        name=user_data['name'],
        provider='apple'
    )
    
    # Log successful authentication
    logger.info(f"Successful Apple authentication for user: {user_data['user_id']}")
    
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "user_id": user_data['user_id'],
        "email": user_data['email'],
        "name": user_data['name'],
    }), 200

@social_auth_bp.route('/facebook', methods=['POST'])
@handle_auth_errors
def facebook_auth():
    """Authenticate user with Facebook access token"""
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required")
    
    access_token = data.get('access_token')
    if not access_token:
        raise ValidationError("access_token is required")
    
    # Verify token and get user info
    fb_user, has_email = verify_facebook_token(access_token)
    
    # Extract user information
    facebook_user_id = fb_user.get('id')
    email = fb_user.get('email')
    name = fb_user.get('name')

    # Validate required fields
    if not facebook_user_id:
        raise ValidationError("Facebook user ID not found")
    
    if not email and has_email:
        raise AuthError("Unable to retrieve email from Facebook")
    elif not email:
        raise ValidationError("Email permission is required for authentication")
    
    # Get or create user
    user_data = get_or_create_user(
        provider='facebook',
        provider_user_id=facebook_user_id,
        email=email,
        name=name,
    )
    
    # Create tokens
    access_token, refresh_token = create_jwt_token(
        user_id=user_data['user_id'],
        email=user_data['email'],
        name=user_data['name'],
        provider='facebook'
    )
    
    # Log successful authentication
    logger.info(f"Successful Facebook authentication for user: {user_data['user_id']}")
    
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "user_id": user_data['user_id'],
        "email": user_data['email'],
        "name": user_data['name'],
    }), 200

@social_auth_bp.route('/refresh', methods=['POST'])
@handle_auth_errors
def refresh_token():
    """Refresh access token using refresh token"""
    if not request.is_json:
        raise ValidationError("Content-Type must be application/json")
    
    data = request.get_json()
    if not data:
        raise ValidationError("Request body is required")
    
    refresh_token = data.get('refresh_token')
    if not refresh_token:
        raise ValidationError("refresh_token is required")
    
    secret_key =  os.environ.get('JWT_SECRET_KEY')
    if not secret_key:
        raise AuthError("JWT configuration missing", 500)
    
    try:
        # Decode refresh token
        payload = jwt.decode(refresh_token, secret_key, algorithms=['HS256'])
        
        # Verify token type
        if payload.get('type') != 'refresh':
            raise AuthError("Invalid token type")
        
        # TODO: Check if token is blacklisted
        # if is_token_blacklisted(payload.get('jti')):
        #     raise AuthError("Token has been revoked")
        
        # Create new access token
        user_id = payload.get('user_id')
        email = payload.get('email')

        user = get_user(user_id)
        if not user and user_id != getattr(g, "user_id", None):
            raise AuthError("User account is not active")

        # For now, create token with user_id
        access_token, _ = create_jwt_token(
            user_id=user_id,
            email=email,
            name=payload.get('name') if payload.get('name') else None,
            provider=payload.get('auth_provider') if payload.get('auth_provider') else None
        )
        
        return jsonify({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600
        }), 200
        
    except jwt.ExpiredSignatureError:
        raise AuthError("Refresh token has expired")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid refresh token")

@social_auth_bp.route('/logout', methods=['POST'])
@handle_auth_errors
def logout():
    """Logout user and invalidate tokens"""
    # Get token from Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        raise ValidationError("Authorization header is required")
    
    parts = auth_header.split()
    if parts[0].lower() != 'bearer' or len(parts) != 2:
        raise ValidationError("Invalid authorization header format")
    
    token = parts[1]
    secret_key = os.environ.get('JWT_SECRET_KEY')
    if not secret_key:
        raise AuthError("JWT configuration missing", 500)
    
    try:
        # Decode token to get JTI
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        jti = payload.get('jti')
        
        # TODO: Add token to blacklist
        # blacklist_token(jti, expires_at=payload.get('exp'))
        
        # Log logout
        user_id = payload.get('user_id')
        logger.info(f"User logged out: {user_id}")
        
        return jsonify({"message": "Successfully logged out"}), 200
        
    except jwt.InvalidTokenError:
        # Even if token is invalid, return success for logout
        return jsonify({"message": "Successfully logged out"}), 200

# Health check for auth endpoints
@social_auth_bp.route('/health', methods=['GET'])
def auth_health():
    """Check if auth service is healthy"""
    return jsonify({
        "status": "healthy",
        "service": "social_auth",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200