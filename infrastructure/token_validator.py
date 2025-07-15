import jwt
from functools import wraps
from flask import request, g, jsonify, current_app
from infrastructure.logger import get_logger
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from firebase_admin import auth as firebase_admin_auth
from firebase_admin import app_check


logger = get_logger(__name__)

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
    
    setattr(g, "user_id", user_id)
    current_app.config['user_id'] = user_id
    setattr(g, "email", email)
    
    return access_token, refresh_token

def get_user_id_from_token(id_token):
    decoded_token = firebase_admin_auth.verify_id_token(id_token)
    return decoded_token['uid']

def get_formatted_auth_provider(provider: str) -> str:
    """
    Format the auth provider string to match Firebase conventions.
    Converts 'google.com' to 'google', 'apple.com' to 'apple', etc.
    """
    if "apple" in provider.lower():
        return "apple.com"
    elif "google" in provider.lower():
        return "google.com"
    elif "facebook" in provider.lower():
        return "facebook.com"
    else:
        return provider.lower().strip()
    
        
def handle_all_errors(f):
    """
    Unified error handler that properly handles both auth and general errors.
    Must be the outermost decorator (listed last) to catch all exceptions.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except AuthError as e:
            # Log auth errors for monitoring
            logger.error(f"AuthError in {f.__name__}: {e.message} (status: {e.status_code})")
            
            # Return proper auth error response
            return jsonify({
                "error": e.message,
                "error_code": "AUTH_ERROR",
                "requires_login": True
            }), e.status_code
            
        except ValidationError as e:
            # Return validation error response
            return jsonify({
                "error": e.message,
                "error_code": "VALIDATION_ERROR"
            }), e.status_code
            
        except jwt.ExpiredSignatureError:
            # Explicit handling for expired tokens
            logger.error(f"Expired token in {f.__name__}")
            return jsonify({
                "error": "Token has expired",
                "error_code": "TOKEN_EXPIRED",
                "requires_login": True,
                "refresh_required": True
            }), 401
            
        except jwt.InvalidTokenError as e:
            # Handle other JWT errors
            logger.error(f"Invalid token in {f.__name__}: {str(e)}")
            return jsonify({
                "error": "Invalid token",
                "error_code": "INVALID_TOKEN",
                "requires_login": True
            }), 401
            
        except Exception as e:
            # Log unexpected errors with full traceback
            logger.error(f"Unexpected error in {f.__name__}: {str(e)}", exc_info=True)
            
            # Don't expose internal error details to client
            return jsonify({
                "error": "Internal server error",
                "error_code": "INTERNAL_ERROR"
            }), 500
    
    return decorated_function

def verify_token(f):
    """Decorator to verify JWT token and check expiration"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            raise AuthError("Authorization header is required", 401)
        
        parts = auth_header.split()
        if parts[0].lower() != 'bearer' or len(parts) != 2:
            raise AuthError("Invalid authorization header format", 401)
        
        token = parts[1]
        secret_key = os.environ.get('JWT_SECRET_KEY')

        if not secret_key:
            raise AuthError("JWT configuration missing", 500)
        
        try:
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])
            
            # Verify token type
            if payload.get('type') != 'access':
                raise AuthError("Invalid token type", 401)
            
            # Extract user_id
            user_id = payload.get('user_id') or payload.get('sub') or payload.get('uid')
            if not user_id:
                raise AuthError("Invalid token: missing user ID", 401)
                
            setattr(g, "user_id", user_id)
            current_app.config['user_id'] = user_id
            
            # Execute the wrapped function
            response = f(*args, **kwargs)
            
            # Add token expiration headers
            if 'exp' in payload:
                exp_timestamp = payload['exp']
                current_timestamp = datetime.now(timezone.utc).timestamp()
                time_until_expiry = exp_timestamp - current_timestamp
                
                # Prepare response with headers
                if isinstance(response, tuple):
                    if len(response) == 2:
                        response_data, status_code = response
                        headers = {}
                    else:
                        response_data, status_code, headers = response
                else:
                    response_data = response
                    status_code = 200
                    headers = {}
                
                # Add expiration info headers
                headers['X-Token-Expires-In'] = str(int(time_until_expiry))
                
                # Add warning if token expires soon (< 5 minutes)
                if time_until_expiry < 300:
                    headers['X-Token-Expires-Soon'] = 'true'
                
                return response_data, status_code, headers
            
            return response
            
        except jwt.ExpiredSignatureError:
            raise AuthError("Token has expired", 401)
        except jwt.InvalidTokenError as e:
            raise AuthError(f"Invalid token: {str(e)}", 401)
            
    return decorated_function

def verify_app_check_token(f):
    """Decorator to verify Firebase App Check token"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        app_check_token = request.headers.get('X-Firebase-AppCheck')
        
        if not app_check_token:
            logger.error("Firebase App Check Error: missing App Check token")
            raise AuthError("App Check token is required", 401)
        
        try:
            # Verify the App Check token
            verified_token = app_check.verify_token(app_check_token)
            setattr(g, "app_check_token", verified_token)
             
            return f(*args, **kwargs)
        except app_check.InvalidTokenError as e:
            logger.error(f"Firebase App Check Error: Invalid App Check token: {str(e)}")
            raise AuthError(f"Invalid App Check token: {str(e)}", 401)

    
    return decorated_function
