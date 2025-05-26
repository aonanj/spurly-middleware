from flask import Blueprint, request, jsonify
from infrastructure.auth import require_auth
from infrastructure.context import (
    set_current_connection,
    get_current_connection,
    clear_current_connection,
    get_current_user
)
from services.connection_service import get_connection_profile

context_bp = Blueprint("context", __name__)

@context_bp.route("/connection", methods=["POST"])
@require_auth
def set_connection_context():
    user = get_current_user()
    if not user:
        return jsonify({"error": "User context not loaded"}), 401

    data = request.get_json(silent=True)
    connection_id = data.get("connection_id") if isinstance(data, dict) else None
    if not connection_id:
        return jsonify({"error": "Missing connection_id"}), 400

    profile = get_connection_profile(user.user_id, connection_id)
    if not profile:
        return jsonify({"error": "Connection profile not found"}), 404

    set_current_connection(profile)
    return jsonify({"message": "Connection context set successfully."})

@context_bp.route("/connection", methods=["DELETE"])
@require_auth
def clear_connection_context():
    clear_current_connection()
    return jsonify({"message": "Connection context cleared."})

@context_bp.route("/", methods=["GET"])
@require_auth
def get_context():
    user = get_current_user()
    connection = get_current_connection()

    return jsonify({
        "user_profile": user.to_dict() if user else None,
        "connection_profile": connection.to_dict() if connection else None
    })
