from flask import Blueprint, request, jsonify, g
from infrastructure.token_validator import verify_token, handle_errors
from infrastructure.logger import get_logger
from services.user_service import update_user_profile, get_user

user_management_bp = Blueprint("user_management", __name__)
logger = get_logger(__name__)

@user_management_bp.route("/user", methods=["POST"])
@verify_token
@handle_errors
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
@verify_token
@handle_errors
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

