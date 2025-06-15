import jwt
from functools import wraps
from flask import request, g, jsonify, current_app
from infrastructure.logger import get_logger
import os
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import firebase_admin
from firebase_admin import auth as firebase_admin_auth

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
        
def handle_auth_errors(f):
    """Decorator to handle authentication errors"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        data = request.get_json(silent=True)
        #DEBUGSTART
        try:
            if not data:
                data = request.form.to_dict()
                logger.error(f"handle_auth_errors called for function: {f.__name__}, with data: {data}")
        except Exception as e:
            logger.error(f"Failed to parse request data: {e}")
        # DEBUG END
        
        
        try:
            logger.error("1st try block entered of handle_auth_errors")
            logger.error(f" Function: {f.__name__}, Args: {args}"); 
            logger.error(f" Kwargs: {kwargs}")
            return f(*args, **kwargs)
        except AuthError as e:
            #DEBUG: 
            logger.error("1st exception block entered of handle_auth_errors")
            logger.error(f" Auth error: {f.__name__}, e message: {e.message}, e status: {e.status_code}"); 

            logger.warning(f"Authentication error in {f.__name__}: {e.message}")
            return jsonify({"error": e.message}), e.status_code
        except ValidationError as e:
            #DEBUG: 
            logger.error("2nd exception block entered of handle_auth_errors")
            logger.error(f" Validation error: {f.__name__}, e message: {e.message}, e status: {e.status_code}"); 
            logger.warning(f"Validation error in {f.__name__}: {e.message}")
            return jsonify({"error": e.message}), e.status_code
        except jwt.ExpiredSignatureError:
            #DEBUG: 
            logger.error("3rd exception block entered of handle_auth_errors")
            logger.error(f" Expired token error"); 
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError as e:
            #DEBUG: 
            logger.error("4th exception block entered of handle_auth_errors")
            logger.warning(f"Invalid token in {f.__name__}: {str(e)}")
            return jsonify({"error": "Invalid token"}), 401
        except requests.RequestException as e:
            #DEBUG:
            logger.error("5th exception block entered of handle_auth_errors")
            logger.error(f"Requests.Requests exception in {f.__name__}: {str(e)}")
            return jsonify({"error": "External service temporarily unavailable"}), 503
        except Exception as e:
            #DEBUG:
            logger.error("6th exception block entered of handle_auth_errors")
            logger.error(f"Unexpected error in {f.__name__}: {str(e)}")
            logger.exception(f"Unexpected error in {f.__name__}: {str(e)}")
            return jsonify({"error": "Internal server error"}), 500
    return decorated_function

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


def handle_errors(f):
    """
    Decorator to handle exceptions in routes.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Unhandled error in {f.__name__}: {str(e)}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    return decorated_function