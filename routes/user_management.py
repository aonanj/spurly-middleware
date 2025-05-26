from flask import Blueprint, request, jsonify, g
from infrastructure.auth import require_auth
from infrastructure.logger import get_logger
from services.user_service import update_user_profile, get_user_profile, delete_user_profile

user_management_bp = Blueprint("user_management", __name__)
logger = get_logger(__name__)

@user_management_bp.route("/user", methods=["POST"])
@require_auth
def update_user_bp():
    try:
        data = request.get_json()
        user_id = g.user['user_id']

        age = data.get("age")
        if age and (not isinstance(age, int) or not (18 <= age <= 99)):
            err_point = __package__ or __name__
            logger.error(f"Error: {err_point}")
            return jsonify({"error": f"[{err_point}] - Error"}), 400

        json_user_profile = update_user_profile(user_id, data)

        return json_user_profile
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return jsonify({"error": f"[{err_point}] - Error"}), 401

@user_management_bp.route("/user", methods=["GET"])
@require_auth
def get_user_bp():
    try:
        user_id = g.user['user_id']
        profile = get_user_profile(user_id)
        return jsonify(profile), 200
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return jsonify({'error': f"[{err_point}] - Error: {str(e)}"}), 500

@user_management_bp.route("/user", methods=["DELETE"])
@require_auth
def delete_user_bp():
    try:
        user_id = g.user['user_id']
        if delete_user_profile(user_id):
            return jsonify({"message": "User profile deleted successfully."}), 200
        else:
            return jsonify({"message": "ERROR - user profile not deleted."}), 200
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return jsonify({'error': f"[{err_point}] - Error: {str(e)}"}), 500