import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Dict, Optional, Any
import os
from infrastructure.token_validator import verify_token, handle_all_errors, AuthError
from services.user_service import get_user  # Import your user service

from flask import Blueprint, jsonify, g

# Create blueprint
profile_bp = Blueprint('profile', __name__, url_prefix='/api/profile')

logger = logging.getLogger(__name__)

def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user profile from database"""
    user = get_user(user_id)
    if not user:
        return None
    else:
        return user.to_dict()

@profile_bp.route('/<user_id>', methods=['GET'])
@verify_token
@handle_all_errors
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