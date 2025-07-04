from flask import Blueprint, request, jsonify, g, current_app
import re
from infrastructure.token_validator import verify_token, handle_all_errors
from infrastructure.logger import get_logger
from services.user_service import update_user_profile, get_user, get_selected_spurs, update_spur_preferences, update_user, update_user_using_trending_topics, update_user_model_temp_preference

user_management_bp = Blueprint("user_management", __name__)
logger = get_logger(__name__)


EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

def validate_email(email: str) -> bool:
    """Validate email format"""
    return bool(EMAIL_REGEX.match(email))

@user_management_bp.route("/user", methods=["POST"])
@handle_all_errors
@verify_token
def update_user_bp():
    try:
        data = request.get_json()
        user_id = getattr(g, "user_id", None)

        age = data.get("age")
        if age and (not isinstance(age, int) or not (18 <= age <= 99)):
            err_point = __package__ or __name__
            logger.error(f"Error: {err_point}")
            return jsonify({"error": f"[{err_point}] - Error"}), 400
        
        if user_id != data.get("user_id"):
            err_point = f"User ID mismatch {user_id} != {data.get('user_id')} in {__package__ or __name__}"
            logger.error(f"Error: {err_point}")
            return jsonify({"error": f"[{err_point}] - Error"}), 400

        json_user_profile = update_user_profile(**data)

        return jsonify({
            "user_id": json_user_profile.user_id,
            "email": json_user_profile.email,
            "name": json_user_profile.name,
        }), 200
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return jsonify({"error": f"[{err_point}] - Error"}), 401

@user_management_bp.route("/user", methods=["GET"])
@handle_all_errors
@verify_token
def get_user_bp():
    try:
        user_id = getattr(g, "user_id", None)
        if user_id is None:
            err_point = __package__ or __name__
            logger.error(f"Error: User ID is None in {err_point}")
            return jsonify({"error": f"[{err_point}] - Error"}), 400
        profile = get_user(user_id)
        return jsonify(profile), 200
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return jsonify({'error': f"[{err_point}] - Error: {str(e)}"}), 500
    
@user_management_bp.route("/get-selected-spurs", methods=["GET"])
@handle_all_errors
@verify_token
def fetch_selected_spurs_bp():
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = current_app.config.get("user_id", None)
            if not user_id:
                err_point = __package__ or __name__
                logger.error(f"Error: User ID is None in {err_point}")
                return jsonify({"error": f"[{err_point}] - Error"}), 400


        spurs_list = get_selected_spurs(user_id)

        return jsonify(spurs_list), 200
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return jsonify({'error': f"[{err_point}] - Error: {str(e)}"}), 500

@user_management_bp.route("/update-selected-spurs", methods=["POST"])
@handle_all_errors
@verify_token
def update_selected_spurs_bp():
    
    if request.is_json:
        form_data = request.get_json()
    else:
        form_data = request.form.to_dict()
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = form_data.get("user_id", None)
            if not user_id:
                user_id = current_app.config.get("user_id", None)
                if not user_id:
                    err_point = __package__ or __name__
                    logger.error(f"Error: User ID is None in {err_point}")
                    return jsonify({"error": f"[{err_point}] - Error"}), 400
        
        selected_spurs = []
        if "selected_spurs" in form_data and isinstance(form_data.get("selected_spurs"), list):
            selected_spurs = form_data.get("selected_spurs", [])
            
        if len(selected_spurs) > 0:
            # Ensure all items in selected_spurs are strings
            selected_spurs_validated = [str(spur) for spur in selected_spurs if spur is not None]
            updated_user_profile = update_spur_preferences(user_id, selected_spurs_validated)
            
            return jsonify({
                "user_id": updated_user_profile.user_id,
                "selected_spurs:": updated_user_profile.selected_spurs,
            }), 200
        
        return jsonify({"message": "No spurs selected"}), 200
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return jsonify({'error': f"[{err_point}] - Error: {str(e)}"}), 500

@user_management_bp.route("/update-email", methods=["POST"])
@handle_all_errors
@verify_token
def update_email_bp():
    
    if request.is_json:
        form_data = request.get_json()
    else:
        form_data = request.form.to_dict()
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = form_data.get("user_id", None)
            if not user_id:
                user_id = current_app.config.get("user_id", None)
                if not user_id:
                    err_point = __package__ or __name__
                    logger.error(f"Error: User ID is None in {err_point}")
                    return jsonify({"error": f"[{err_point}] - Error"}), 400
        
        updated_email = ""
        if "updated_email" in form_data and isinstance(form_data.get("updated_email"), str):
            updated_email = form_data.get("updated_email", "")
            
        if validate_email(updated_email):
            updated_user_profile = update_user(user_id=user_id, email=updated_email)
            setattr(g, "email", updated_email)
            
            return jsonify({
                "user_id": updated_user_profile.user_id,
                "email:": updated_user_profile.email,
            }), 200
        
        return jsonify({"message": "updated email not provided"}), 200
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return jsonify({'error': f"[{err_point}] - Error: {str(e)}"}), 500

@user_management_bp.route("/using-trending-topics", methods=["GET"])
@handle_all_errors
@verify_token
def is_using_trending_topics_bp():

    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = current_app.config.get("user_id", None)
            if not user_id:
                err_point = __package__ or __name__
                logger.error(f"Error: User ID is None in {err_point}")
                return jsonify({"error": f"[{err_point}] - Error"}), 400
        
        user_profile = get_user(user_id)
        return jsonify({"user_id": user_profile.user_id if user_profile else None, "using_trending_topics": user_profile.using_trending_topics if user_profile else False}), 200
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] user_management:is_using_trending_topics Error: %s", err_point, e)
        return jsonify({'error': f"[{err_point}] - Error: {str(e)}"}), 500

@user_management_bp.route("/set-using-trending-topics", methods=["POST"])
@handle_all_errors
@verify_token
def set_using_trending_topics_bp():

    if request.is_json:
        form_data = request.get_json()
    else:
        form_data = request.form.to_dict()
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = form_data.get("user_id", None)
            if not user_id:
                user_id = current_app.config.get("user_id", None)
                if not user_id:
                    err_point = __package__ or __name__
                    logger.error(f"Error: User ID is None in {err_point}")
                    return jsonify({"error": f"[{err_point}] - Error"}), 400
        using_trending_topics = form_data.get("use_trending_topics", None)

        if using_trending_topics is not None:
            # Convert string to boolean
            using_trending_topics_bool = using_trending_topics if isinstance(using_trending_topics, bool) else str(using_trending_topics).lower() in ('true', '1', 'yes', 'on')
            updated_user_profile = update_user_using_trending_topics(user_id=user_id, using_trending_topics=using_trending_topics_bool)
            return jsonify({
                "user_id": updated_user_profile.get("user_id", user_id),
                "using_trending_topics": updated_user_profile.get("using_trending_topics", False),
            }), 200

            
            return jsonify({
                "user_id": updated_user_profile.user_id,
                "selected_spurs:": updated_user_profile.selected_spurs,
            }), 200
        
        return jsonify({"message": "No spurs selected"}), 200
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return jsonify({'error': f"[{err_point}] - Error: {str(e)}"}), 500

@user_management_bp.route("/get-model-temp-preference", methods=["GET"])
@handle_all_errors
@verify_token
def get_model_temp_preference_bp():

    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = current_app.config.get("user_id", None)
            if not user_id:
                err_point = __package__ or __name__
                logger.error(f"Error: User ID is None in {err_point}")
                return jsonify({"error": f"[{err_point}] - Error"}), 400
        
        user_profile = get_user(user_id)
        return jsonify({"user_id": user_profile.user_id if user_profile else None, "model_temp_preference": user_profile.model_temp_preference if user_profile else 1.0}), 200
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] user_management:get_model_temp_preference Error: %s", err_point, e)
        return jsonify({'error': f"[{err_point}] - Error: {str(e)}"}), 500

@user_management_bp.route("/set-model-temp-preference", methods=["POST"])
@handle_all_errors
@verify_token
def set_model_temp_preference_bp():

    if request.is_json:
        form_data = request.get_json()
    else:
        form_data = request.form.to_dict()
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = form_data.get("user_id", None)
            if not user_id:
                user_id = current_app.config.get("user_id", None)
                if not user_id:
                    err_point = __package__ or __name__
                    logger.error(f"Error: User ID is None in {err_point}")
                    return jsonify({"error": f"[{err_point}] - Error"}), 400
        model_temp_preference = form_data.get("model_temp_preference", None)

        if model_temp_preference is not None:
            # Convert to float
            model_temp_preference_float = float(model_temp_preference)
            updated_user_profile = update_user_model_temp_preference(user_id=user_id, model_temp_preference=model_temp_preference_float)
            return jsonify({
                "user_id": updated_user_profile.get("user_id", user_id),
                "model_temp_preference": updated_user_profile.get("model_temp_preference", 1.0),
            }), 200

            
            return jsonify({
                "user_id": updated_user_profile.user_id,
                "selected_spurs:": updated_user_profile.selected_spurs,
            }), 200
        
        return jsonify({"message": "No spurs selected"}), 200
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return jsonify({'error': f"[{err_point}] - Error: {str(e)}"}), 500


