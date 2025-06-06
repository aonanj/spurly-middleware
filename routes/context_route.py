from flask import Blueprint, request, jsonify
from infrastructure.token_validator import verify_token, handle_errors
from infrastructure.token_validator import verify_token, handle_errors
from infrastructure.context import (
    set_active_connection,
    get_active_connection,
    clear_active_connection,
    get_active_user
)
from services.connection_service import get_connection_profile

context_bp = Blueprint("context", __name__)

@context_bp.route("/connection", methods=["POST"])
@verify_token
@handle_errors
def set_connection_context():
    user = get_active_user()
    if not user:
        return jsonify({"error": "User context not loaded"}), 401

    data = request.get_json(silent=True)
    connection_id = data.get("connection_id") if isinstance(data, dict) else None
    if not connection_id:
        return jsonify({"error": "Missing connection_id"}), 400

    profile = get_connection_profile(user.user_id, connection_id)
    if not profile:
        return jsonify({"error": "Connection profile not found"}), 404

    set_active_connection(profile)
    return jsonify({"message": "Connection context set successfully."})

@context_bp.route("/connection", methods=["DELETE"])
@verify_token
@handle_errors
def clear_connection_context():
    clear_active_connection()
    return jsonify({"message": "Connection context cleared."})

@context_bp.route("/get_context", methods=["GET"])
@verify_token
@handle_errors
def get_context():
    user = get_active_user()
    connection = get_active_connection()

    return jsonify({
        "user_profile": user.to_dict() if user else None,
        "connection_profile": connection.to_dict() if connection else None
    })
