from infrastructure.logger import get_logger

logger = get_logger(__name__)




# context_bp = Blueprint("context", __name__)

# @context_bp.route("/context/connection", methods=["POST"])
# @verify_token
# def set_connection_context():
#     """
#     Sets a connection as active in the current context. 
    
#     Args
#         N/A
    
#     Return
#         status: JSON-like structure indicating that a connection is active in the current context 

#     """
#     user_profile = get_active_user()
#     if not user_profile:
#         return jsonify({"error": "User context not loaded"}), 401

#     connection_id = request.get_json().get("connection_id")
#     if not connection_id:
#         return jsonify({"error": "Missing connection_id"}), 400

#     connection_profile = get_connection_profile(user_profile.user_id, connection_id)
#     if not connection_profile:
#         logger.error("Failed to load connection profile for active user profile")
#         return jsonify({"error": "Connection profile not found"}), 404

#     set_active_connection(connection_profile)
#     return jsonify({"message": "Connection context set successfully."})

# @context_bp.route("/context/connection", methods=["DELETE"])
# @verify_token
# def clear_connection_context():
#     """
#     Removes an active connection from the current context. 
    
#     Args
#         N/A
    
#     Return
#         status: JSON-like structure indicating that active connection cleared from current context 
#     """
    
#     clear_active_connection()
#     return jsonify({"message": "Connection context cleared."})

# @context_bp.route("/context", methods=["GET"])
# @verify_token
# def get_context():
#     """
#     Gets active user and connection profiles from the current context.
    
#     Args
#         N/A
    
#     Return
#         status: JSON-like structure representing user and connections profiles as dict objects 
#     """
#     user_profile = get_active_user()
#     connection_profile = get_active_connection()

#     return jsonify({
#         "user_profile": user_profile.to_dict if user_profile else None,
#         "connection_profile": connection_profile.to_dict() if connection_profile else None
#     })