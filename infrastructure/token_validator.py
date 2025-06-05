import jwt
from functools import wraps
from flask import request, g, jsonify, current_app
import logging
from typing import Dict, Any
from infrastructure.logger import get_logger
from routes.profile_routes import AuthError  
import os

logger = get_logger(__name__)

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
            
            # Store user info in g for use in route
            g.user_id = payload.get('user_id')
            g.user_email = payload.get('email')
            
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