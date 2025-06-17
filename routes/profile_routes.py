import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Dict, Optional, Any
import os
from services.user_service import get_user  # Import your user service

import jwt
from flask import Blueprint, request, jsonify, current_app, g

# Create blueprint
profile_bp = Blueprint('profile', __name__, url_prefix='/api/profile')

logger = logging.getLogger(__name__)

class AuthError(Exception):
    """Custom authentication error"""
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

def handle_errors(f):
    """Decorator to handle errors"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except AuthError as e:
            logger.error(f"Auth error in {f.__name__}: {e.message}")
            return jsonify({"error": e.message}), e.status_code
        except Exception as e:
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
            # Store user info in g for use in route
            user_id = ""
            if 'user_id' in payload:
                user_id = payload.get('user_id')
            elif 'sub' in payload:
                user_id = payload.get('sub')
            elif 'uid' in payload:
                user_id = payload.get('uid')
            setattr(g, "user_id", user_id)
            setattr(g, "user_email", payload.get('email'))

            return f(*args, **kwargs)

        except jwt.ExpiredSignatureError:
            raise AuthError("Token has expired")
        except jwt.InvalidTokenError:
            raise AuthError("Invalid token")
            
    return decorated_function

def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user profile from database"""
    user = get_user(user_id)
    if not user:
        return None
    else:
        return user.to_dict()

@profile_bp.route('/<user_id>', methods=['GET'])
@handle_errors
@verify_token
def get_profile(user_id: str):
    """Get user profile by ID"""
    # Verify user is accessing their own profile or has permission
    if getattr(g, "user_id", None) != user_id:
        # You might want to allow admins or implement other permission logic
        raise AuthError("Unauthorized to access this profile", 403)
    
    # Get profile from database
    profile_data = get_user_profile(user_id)
    
    if profile_data is None:
        # User exists (they're authenticated) but profile not found
        # Return 404 to indicate profile doesn't exist
        return jsonify({"error": "Profile not found"}), 404
    
    # Return profile data
    return jsonify({
        "user_id": profile_data.get('user_id'),
        "name": profile_data.get('name', ""),
        "email": profile_data.get('email', ""),
        "age": profile_data.get('age', None),
        "user_context_block": profile_data.get('user_context_block', ""),
        "selected_spurs": profile_data.get('selected_spurs', []),
        "created_at": profile_data.get('created_at', ""),
        "updated_at": profile_data.get('updated_at', "")
    }), 200

# Health check
@profile_bp.route('/health', methods=['GET'])
def profile_health():
    """Check if profile service is healthy"""
    return jsonify({
        "status": "healthy",
        "service": "profile",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200