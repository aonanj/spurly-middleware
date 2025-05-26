from class_defs.profile_def import UserProfile, ConnectionProfile
from flask import request, jsonify, g
from infrastructure.logger import get_logger
from services.user_service import get_user_profile

logger = get_logger(__name__)

def set_current_user(user_profile: UserProfile):
    """
    Sets the app context global variable current_user to the user's profile

    Args
        user_profile: user profile of current user
            UserProfile object
    Return
        N/A
    """
    
    g.current_user = user_profile

def get_current_user() -> UserProfile:
    """
    Gets the app context global variable current_user

    Args
        N/A
    Return
        current_user: User profile of the current user
            UserProfile object
    """
    return getattr(g, "current_user")

def set_current_connection(connection_profile):
    """
    Sets the app context global variable current_connection to a connection profile selected or entered by user

    Args
        connection_profile: connection profile of current user
            ConnectionProfile object
    Return
        N/A
    """
    g.current_connection = connection_profile

def get_current_connection() -> ConnectionProfile:
    """
    Gets the app context global variable current_connection, if one is active

    Args
        N/A
    Return
        current_connection: Connection profile of a connection loaded by the current user
            ConnectionProfile object
    """
    return getattr(g, "current_connection")

def clear_current_connection():
    """
    Clear the app context global variable current_connection, so none is active

    Args
        N/A
    Return
        N/A
    """
    g.current_connection = None

def load_user_context():
    """
    Middleware to auto-load the current user's profile from the X-User-ID header.
    """
    try:
        user_id = request.headers.get("X-User-ID")
        if user_id:
            user_profile = get_user_profile(user_id)
            if user_profile:
                set_current_user(user_profile)
    except Exception as e:
        logger.error("[%s] Error: %s Load user profile into app context failed", __name__, e)
        raise RuntimeError(f"Failed to load user profile into app context: {e}") from e      

def require_user_context():
    """
    Middleware that enforces user context must be loaded for protected routes.
    """
    if not get_current_user():
        return jsonify({"error": "Missing user context"}), 401

# context_bp = Blueprint("context", __name__)

# @context_bp.route("/context/connection", methods=["POST"])
# @require_auth
# def set_connection_context():
#     """
#     Sets a connection as active in the current context. 
    
#     Args
#         N/A
    
#     Return
#         status: JSON-like structure indicating that a connection is active in the current context 

#     """
#     user_profile = get_current_user()
#     if not user_profile:
#         return jsonify({"error": "User context not loaded"}), 401

#     connection_id = request.get_json().get("connection_id")
#     if not connection_id:
#         return jsonify({"error": "Missing connection_id"}), 400

#     connection_profile = get_connection_profile(user_profile.user_id, connection_id)
#     if not connection_profile:
#         logger.error("Failed to load connection profile for active user profile")
#         return jsonify({"error": "Connection profile not found"}), 404

#     set_current_connection(connection_profile)
#     return jsonify({"message": "Connection context set successfully."})

# @context_bp.route("/context/connection", methods=["DELETE"])
# @require_auth
# def clear_connection_context():
#     """
#     Removes an active connection from the current context. 
    
#     Args
#         N/A
    
#     Return
#         status: JSON-like structure indicating that active connection cleared from current context 
#     """
    
#     clear_current_connection()
#     return jsonify({"message": "Connection context cleared."})

# @context_bp.route("/context", methods=["GET"])
# @require_auth
# def get_context():
#     """
#     Gets active user and connection profiles from the current context.
    
#     Args
#         N/A
    
#     Return
#         status: JSON-like structure representing user and connections profiles as dict objects 
#     """
#     user_profile = get_current_user()
#     connection_profile = get_current_connection()

#     return jsonify({
#         "user_profile": user_profile.to_dict if user_profile else None,
#         "connection_profile": connection_profile.to_dict() if connection_profile else None
#     })