# In routes/onboarding.py
from flask import Blueprint, request, jsonify, current_app, g # Add g
from infrastructure.firebase_auth import require_firebase_auth
from infrastructure.id_generator import generate_user_id
from infrastructure.logger import get_logger
# Import necessary functions and classes
from services.user_service import update_user_profile
from class_defs.profile_def import UserProfile # Import UserProfile/BaseProfile
from dataclasses import fields # Import fields
from infrastructure.firebase_auth import require_firebase_auth # Import auth decorator
import jwt
import logging
from functools import wraps
from profile_routes import handle_errors, verify_token

onboarding_bp = Blueprint("onboarding", __name__)
logger = get_logger(__name__)

@onboarding_bp.route("/onboarding", methods=["POST"])
@handle_errors
@verify_token
def onboarding(): # Removed type hint for simplicity during debug
    """
    
    Onboarding route for initial login. User information stored in persisntent memory. User ID generated. 
    
    Args:
        none
        
    Return: 
        Dictionary, key is user ID and entry is user profile. 
    
    """
    try:
        data = request.get_json()
        if not data or 'age' not in data:
             logger.error("Missing age or data in onboarding request.")
             return jsonify({"error": "Missing age in request data"}), 400 # More specific error

        age = data.get("age")
        if not isinstance(age, int) or not (18 <= age):
                # err_point = __package__ or __name__ # Not defined, use module name
                logger.error("[routes.onboarding] Error: Invalid age provided: %s", age)
                # Return 400 for bad request data, not 401 (unauthorized)
                return jsonify({"error": "[routes.onboarding] - Error: Age must be an integer between 18 and 99"}), 400

        if not g.user.user_id:
            user_id = generate_user_id()
            g.user = {'user_id': user_id} # Set in g for current request context
        else:
            user_id = g.user.user_id

        # Determine selected spurs, default to list from config
        selected_spurs = data.get("selected_spurs", list(current_app.config['SPUR_VARIANTS']))
        # Ensure it's a list
        if not isinstance(selected_spurs, list):
             selected_spurs = list(current_app.config['SPUR_VARIANTS'])


        # 1. Create the profile data dictionary
        profile_data_dict = {
            "user_id": user_id, # Added user_id
            "selected_spurs": selected_spurs,
            "age": age
        }
        # Add optional fields from request data if they exist
        optional_fields = [f.name for f in fields(UserProfile) if f.name not in ['user_id', 'selected_spurs']] # Get all optional field names
        for field_name in optional_fields:
             request_key = field_name

             if request_key in data:
                  profile_data_dict[field_name] = data[request_key]
             # No need to add None here, save_user_profile handles adding missing Nones


        # 2. Save the structured data using the modified service function
        save_result = update_user_profile(**profile_data_dict) # Pass user_id and dict

        # Check if save was successful (optional, depends on return value)
        if isinstance(save_result, tuple) or (isinstance(save_result, dict) and "error" in save_result):
             # Handle save error
             logger.error("Failed to save user profile during onboarding for user %s", user_id)
             error_msg = save_result[0].get("error") if isinstance(save_result, tuple) else save_result.get("error", "Unknown save error")
             status_code = save_result[1] if isinstance(save_result, tuple) else save_result.get("status_code", 500)
             return jsonify({"error": f"Profile save failed: {error_msg}"}), status_code


        # 3. Format the profile string for the response
        try:
            # Need to create the UserProfile object to format it
            # Add potentially missing fields as None before creating object
            full_profile_data = profile_data_dict.copy()
            # all_fields = {f.name for f in fields(UserProfile)}
            # for field_name in all_fields:
            #      if field_name not in full_profile_data:
            #           full_profile_data[field_name] = None # Add Nones for fields not in request

            profile_obj_for_formatting = UserProfile(**full_profile_data)
            
        except Exception as format_exc:
             logger.error("Error formatting profile object for response: %s", format_exc, exc_info=True)
             return jsonify({"error": f"[routes.onboarding] - Error: {str(format_exc)}"}), 500


        return jsonify({
            "user_id": user_id,
            "success": True,
            "message": "Onboarding successful",
        })

    except Exception as e:
        # err_point = __package__ or __name__ # Not defined
        logger.error("[routes.onboarding] Error: %s", e, exc_info=True)
        # Return 500 for unexpected server errors
        return jsonify({"error": f"[routes.onboarding] - Error: {str(e)}"}), 500

    
 