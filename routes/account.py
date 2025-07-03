from flask import Blueprint, request, jsonify, g
from infrastructure.token_validator import verify_token, handle_all_errors
from infrastructure.logger import get_logger
from services.user_service import delete_user

account_bp = Blueprint("account", __name__, url_prefix='/api/account')
logger = get_logger(__name__)

@account_bp.route("/delete", methods=["DELETE"])
@handle_all_errors
@verify_token
def delete_account():
    """
    Deletes a registered user's account and all associated data.
    """
    user_id = getattr(g, "user_id", None)
    if not user_id:
        return jsonify({"error": "Authentication error"}), 401
        
    try:
        result = delete_user(user_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"Error deleting account for user {user_id}: {e}", exc_info=True)
        return jsonify({"error": "Failed to delete account"}), 500