from flask import Blueprint, request, jsonify, g
from infrastructure.token_validator import verify_token, handle_errors
from infrastructure.token_validator import verify_token, handle_errors
from .connections import set_active_connection, clear_active_connection
from services.connection_service import get_connection_profile
from services.user_service import get_user

context_bp = Blueprint("context", __name__)



@context_bp.route("/connection", methods=["DELETE"])
@verify_token
@handle_errors
def clear_connection_context():
    clear_active_connection()
    return jsonify({"message": "Connection context cleared."})


