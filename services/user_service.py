from class_defs.profile_def import BaseProfile, UserProfile
from dataclasses import fields
from firebase_admin import auth
from flask import jsonify, current_app, g
from infrastructure.clients import db
from infrastructure.logger import get_logger

logger = get_logger(__name__)

def format_user_profile(profile: UserProfile) -> str:
    """
    
    Converts the user profile information to formatted text to be passed to the frontend.
    
    Args
        profile: Current user's profile
            UserProfile 
        
    Return
        formatted string including user's profile information.
    
    """
    user_id = g.user['user_id']
    if not user_id:
        logger.error("Error: Missing user ID - format user profile failed")
        raise ValueError("Format user profile failed: Missing user ID")

    if not isinstance(profile, UserProfile):
        logger.error("Error: Type mismatch - format user profile failed")
        raise TypeError("Format user profile failed: Type mismatch")
  
    lines = [f"user_id: {user_id}"]

    for field in fields(UserProfile):
        key = field.name
        value = getattr(profile, key)

        if key == "user_id" or value is None:
            continue

        if isinstance(value, list):
            if value:
                label = "Greenlight Topics" if key == "greenlights" else (
                        "Redlight Topics" if key == "redlights" else key.capitalize())
                lines.append(f"{label}: {', '.join(value)}")
        else:
            lines.append(f"{key.capitalize()}: {value}")
    default_log_level = current_app.config['DEFAULT_LOG_LEVEL']      
    logger.log(default_log_level, "Formatting user profile as text for UX/UI use.")
    return "\n".join(lines)

def save_user_profile(user_id: str, data: UserProfile) -> dict:
    """
    
    Saves the current user's profile information to persistent memory (e.g., Firestore).
    
    Args:
        data: A UserProfile object including all of the user's current profile information
    
    Return:
        str:    String indicating that user profile is saved.
    
    """
    
    if not user_id: # Check passed user_id
        logger.error("Error: Missing user ID - save user profile failed")
        raise ValueError("Save user profile failed: Missing user ID")

    if not isinstance(data, dict):
         logger.error("Error: Type mismatch (expected dict) - save user profile failed")
         raise TypeError("Save user profile failed: Input data must be a dictionary")

    try:
        # Ensure 'user_id' and default 'selected_spurs' are in the dict
        data['user_id'] = user_id
        if 'selected_spurs' not in data:
             data['selected_spurs'] = list(current_app.config['SPUR_VARIANTS'])

        # Add missing Optional BaseProfile fields as None if not present
        # This helps UserProfile.from_dict if it expects all fields
        base_fields = {f.name for f in fields(BaseProfile)}
        for field_name in base_fields:
            if field_name not in data:
                data[field_name] = None # Add missing optional fields as None

        # Ensure all required fields for UserProfile are present before creating object
        required_user_fields = {'user_id', 'selected_spurs'} # Add others if any become non-optional
        missing_req = required_user_fields - data.keys()
        if missing_req:
             logger.error(f"Missing required fields for UserProfile: {missing_req}")
             raise ValueError(f"Missing required UserProfile fields: {missing_req}")


        profile = UserProfile.from_dict(data) # Create object from dict
        profile_doc_string = format_user_profile(profile) # Format the object for Firestore string field

        user_ref = db.collection("users").document(user_id)
        user_ref.set({
            "user_id": user_id,
            "profile_entries": profile_doc_string, # Save the formatted string
            "fields": profile.to_dict() # Save the structured data
        })
        logger.log(current_app.config['DEFAULT_LOG_LEVEL'], "User profile successfully saved.")
        # Return a success dictionary, matching what the route might expect
        return {"status": "user profile successfully saved"}
    except Exception as e:
        logger.error("[%s] Error: %s save user profile failed", __name__, e, exc_info=True)
        # Propagate or return an error dict
        # raise ValueError(f"Save user profile failed: {e}") from e
        return {"error": f"Save user profile failed: {str(e)}"}

def get_user_profile(user_id) -> UserProfile:
    """
    
    Gets a current user's profile information from persistent memory (e.g., Firestore).
    
    Args:
        user_id: A user ID of the user profile to be returned. 
    
    Return:
        UserProfile object: The user profile (as a UserProfile object) corresponding to the user_id     
    """
    
    if not user_id:
        logger.error("Error: Missing user ID - get user profile failed")
        raise ValueError("Error: Missing user ID - get user profile failed")

    try:
        user_ref = db.collection("users").document(user_id)
        doc = user_ref.get()

        if not doc.exists:
            logger.error("Error: No user profile - get user profile failed")
            raise ValueError("Error: No user profile - get user profile failed")

        data = doc.to_dict()
        user_profile = UserProfile.from_dict(data)
        return user_profile
    except Exception as e:
        logger.error("[%s] Error: %s get user profile failed", __name__, e)
        raise ValueError(f"Get user profile failed: {e}") from e

def update_user_profile(user_id: str, profile_data: UserProfile):
    """
    
    Adds or replaces information in the user's profile 
    
    Args:
        data: A UserProfile object including all of the user's current profile information
    
    Return:
        str:    String indicating user's profile is updated and saved.
    
    """
    if not user_id:
        logger.error("Error: Missing user ID - update user profile failed")
        raise ValueError("Error: Missing user ID - update user profile failed")
    
    try:
        data = profile_data.to_dict()
        profile = UserProfile.from_dict({"user_id": user_id, **data})
        user_ref = db.collection("users").document(user_id)
        user_ref.set({
            "user_id": user_id,
            "profile_entries": format_user_profile(profile),
            "fields": profile.to_dict()
        })
        logger.log
        return jsonify({
            "user_id": user_id,
            "user_profile": profile.to_dict()
        })
    except Exception as e:
        logger.error("[%s] Error: %s Update user profile failed", __name__, e)
        raise ValueError(f"Update user profile failed: {e}") from e

def delete_user_profile(user_id):
    """
    
    Deletes a user's profile and all related information (e.g., connections, spurs, conversations, etc.)
        from persistant memory. 
    
    Args:
        user_id: The user id corresponding to the data to be deleted. 
    
    Return:
        str:    String indicating user's profile and other information has been deleted.
    
    """
    if not user_id:
        logger.error("Error: Missing user ID - delete user profile failed")
        raise ValueError("Error: Missing user ID - delete user profile failed")
    try:
        user_ref = db.collection("users").document(user_id)

        # Optional: Load and log profile before deletion
        doc = user_ref.get()
        if doc.exists:
            profile_data = doc.to_dict().get("fields", {})
            profile = UserProfile.from_dict(profile_data)
            logger.info(f"Deleting user profile: {profile.to_dict()}")

        def delete_subcollections(parent_ref, subcollection_names):
            for name in subcollection_names:
                sub_ref = parent_ref.collection(name)
                docs = sub_ref.stream()
                for doc in docs:
                    doc.reference.delete()

        delete_subcollections(user_ref, ["connections", "messages", "conversations"])

        user_ref.delete()
        auth.delete_user(user_id)
        return {f"status" : "user profile successfully deleted"}
    except Exception as e:
        logger.error("[%s] Error: %s Delete user profile failed", __name__, e)
        raise ValueError(f"Delete user profile failed: {e}") from e
    
def update_spur_preferences(user_id: str, selected_spurs: list[str]) -> None:
    """
    
    Updates user setting for which spurs to generate, as configured by the user in the frontend settings menu.
    
    Args:
        user_id: The user id corresponding to the settings being updated. 
            string
        selected_spurs: The key names for each of the spur variants to be generated for the user.
            List[strings]
    
    Return:
        str:    String indicating spur variant settings for the user have been updated.
    
    """
    if not user_id:
        logger.error("Error: Missing user ID - update user spur preferences failed")
        raise ValueError("Error: Missing user ID - update user spur preferences failed")
    
    if not selected_spurs:
        logger.error("Error: Missing spur preferences - update user spur preferences failed")
        raise ValueError("Error: Missing spur preferences - update user spur preferences failed")
    
    try:
        db.collection("users").document(user_id).update({ "selected_spurs": selected_spurs})
    except Exception as e:
        logger.error("[%s] Error: %s Update user spur preferences failed", __name__, e)
        raise ValueError(f"Update user spur preferences failed: {e}") from e

def get_selected_spurs(user_id: str) -> list:
    """
    
    Gets list of spurs to generate for user, as configured by the user in the frontend settings menu.
    
    Args:
        user_id: The user id corresponding to the settings being updated. 
            string

    
    Return:
        selected_spurs: The key names for each of the spur variants to be generated for the user.
            List[strings]
    
    """
    if not user_id:
        logger.error("Error: Missing user ID - update user spur preferences failed")
        raise ValueError("Error: Missing user ID - update user spur preferences failed")

    user_profile = get_user_profile(user_id)
    selected_spurs = user_profile.to_dict()['selected_spurs']

    
    try:
        return db.collection("users").document(user_id).update({ "selected_spurs": selected_spurs})
    except Exception as e:
        logger.error("[%s] Error: %s Update user spur preferences failed", __name__, e)
        raise ValueError(f"Update user spur preferences failed: {e}") from e