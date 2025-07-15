# routes/onboarding.py
from flask import Blueprint, request, jsonify, current_app, g
from functools import wraps

from infrastructure.logger import get_logger
from infrastructure.token_validator import verify_token, handle_all_errors, verify_app_check_token
from services.user_service import update_user_profile, get_user, update_spur_preferences

onboarding_bp = Blueprint("onboarding", __name__)
logger = get_logger(__name__)


@onboarding_bp.route("/api/onboarding", methods=["POST"])
@handle_all_errors
@verify_token
@verify_app_check_token
def onboarding():
    """
    Complete user onboarding by updating their profile with additional information.
    
    Expected JSON payload:
    {
        "name": "User Name",
        "age": 25,
        "user_context_block": "Context about the user...",
        "selected_spurs": ["spur1", "spur2"] (optional)
    }
    
    Returns:
        JSON response with success status
    """
    # Get request data
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    
    # Extract user_id from the verified token
    user_id = getattr(g, "user_id", None)
    if not user_id:
        logger.error("User ID not found in token")
        return jsonify({"error": "Invalid authentication state"}), 401
    
    # Validate required fields
    name = data.get('name', '').strip()
    age = data.get('age')
    user_context_block = data.get('user_context_block', '').strip()
    
    # Validation
    errors = []
    
    if not name:
        errors.append("Name is required")
    
    if age is None:
        errors.append("Age is required")
    elif not isinstance(age, int) or age < 18 or age > 150:
        errors.append("Age must be a number between 18 and 150")
    
    
    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400
    
    # Get selected spurs or use defaults
    selected_spurs = data.get('selected_spurs')
    if selected_spurs is not None:
        if not isinstance(selected_spurs, list):
            return jsonify({"error": "selected_spurs must be a list"}), 400
        # Validate spur variants against config
        valid_spurs = set(current_app.config.get('SPUR_VARIANTS', []))
        invalid_spurs = [s for s in selected_spurs if s not in valid_spurs]
        if invalid_spurs:
            return jsonify({
                "error": "Invalid spur variants",
                "details": f"Invalid spurs: {invalid_spurs}"
            }), 400
    
    try:
        # Check if user exists
        user = get_user(user_id)
        if not user:
            logger.error(f"User not found during onboarding: {user_id}")
            return jsonify({"error": "User not found"}), 404
        
        # Update user profile with onboarding data
        updated_user = update_user_profile(
            user_id=user_id,
            name=name,
            age=age,
            user_context_block=user_context_block,
            selected_spurs=selected_spurs,
            email=user.email
        )
        
        using_trending_topics = user.using_trending_topics
        if using_trending_topics is None:
            # Default to False if not set
            using_trending_topics = False
        
        model_temp_preference = user.model_temp_preference
        if model_temp_preference is None:
            # Default to 1.05 if not set
            model_temp_preference = 1.05
        
        # Update spur preferences if provided
        if selected_spurs is not None:
            update_spur_preferences(user_id, selected_spurs, 
                                    using_trending_topics, model_temp_preference)
        
        logger.error(f"LOG.INFO: Onboarding completed for user: {user_id}")
        
        # Return success response
        # Note: We don't return new tokens here because the user already has valid tokens
        return jsonify({
            "success": True,
            "message": "Onboarding completed successfully",
            "user_id": updated_user.user_id,
            "email": updated_user.email,
            "name": updated_user.name
        }), 200
        
    except ValueError as e:
        logger.error(f"Onboarding error for user {user_id}: {str(e)}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Unexpected error during onboarding for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to complete onboarding"}), 500

@onboarding_bp.route("/api/onboarding/status", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def onboarding_status():
    """
    Check if the current user has completed onboarding.
    
    Returns:
        JSON response with onboarding completion status
    """
    user_id = getattr(g, "user_id", None)
    if not user_id:
        return jsonify({"error": "Invalid authentication state"}), 401
    
    try:
        user = get_user(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Check if onboarding is complete
        # User has completed onboarding if they have name, age, and user_context_block
        is_complete = all([
            user.name is not None,
            user.age is not None,
            user.user_context_block is not None
        ])
        
        return jsonify({
            "onboarding_completed": is_complete,
            "user_id": user_id,
            "name": user.name is not None,
            "age": user.age is not None,
            "user_context_block": user.user_context_block is not None
        }), 200
        
    except Exception as e:
        logger.error(f"Error checking onboarding status for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to check onboarding status"}), 500