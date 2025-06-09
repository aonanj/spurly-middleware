# routes/conversations.py
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from infrastructure.token_validator import verify_token, handle_errors
from infrastructure.logger import get_logger
from class_defs.spur_def import Spur
from class_defs.conversation_def import Conversation
from services.spur_service import save_spur, delete_saved_spur, get_saved_spurs
from services.storage_service import (
    get_conversations,
    save_conversation,
    get_conversation,
    delete_conversation,
)

logger = get_logger(__name__)

conversations_bp = Blueprint("conversations", __name__)

@conversations_bp.route("/get-conversations", methods=["GET"])
@verify_token
@handle_errors
def get_conversations_bp():
    user_id = getattr(g, "user_id", None)
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return jsonify({'error': f"[{err_point}] - Error:"}), 400

    filters = {}

    if request.args.get("keyword"):
        filters["keyword"] = request.args.get("keyword")


    for date_field in ["date_from", "date_to"]:
        date_str = request.args.get(date_field)
        if date_str and isinstance(date_str, str):
            try:
                filters[date_field] = datetime.fromisoformat(date_str)
            except ValueError as e:
                err_point = __package__ or __name__
                logger.error("[%s] Error: %s", err_point, e)
                return jsonify({'error': f"{err_point} - Error: {str(e)}"}), 400


    result = get_conversations(user_id, filters)
    return jsonify(result)

@conversations_bp.route("/save-conversation", methods=["POST"])
@verify_token
@handle_errors
def save_conversation_bp():
    user_id = getattr(g, "user_id", None)
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return jsonify({'error': f"[{err_point}] - Error:"}), 400
    data = request.get_json() 
    if not data:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point} - No data provided")
        return jsonify({'error': f"[{err_point}] - No data provided"}), 400
    conversation = data.get('conversation')
    if not isinstance(conversation, dict):
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point} - Invalid data format")
        return jsonify({'error': f"[{err_point}] - Invalid data format"}), 400
 # Ensure this import exists at the top if not already
    conversation_obj = Conversation.from_dict(conversation)
    result = save_conversation(conversation_obj)
    return jsonify(result)

@conversations_bp.route("/get-conversations", methods=["GET"])
@verify_token
@handle_errors
def get_conversation_bp():
    user_id = getattr(g, "user_id", None)
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return jsonify({'error': f"[{err_point}] - Error:"}), 400
    
    data = request.get_json()
    if not data or 'conversation_id' not in data:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point} - No conversation_id provided")
        return jsonify({'error': f"[{err_point}] - No conversation_id provided"}), 400
    conversation_id = data['conversation_id']

    result = get_conversation(user_id=user_id, conversation_id=conversation_id) 
    return jsonify(result)

@conversations_bp.route("/delete-conversation", methods=["DELETE"])
@verify_token
@handle_errors
def delete_conversation_bp():
    user_id = getattr(g, "user_id", None)
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return jsonify({'error': f"[{err_point}] - Error:"}), 400

    data = request.get_json()
    if not data or 'conversation_id' not in data:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point} - No conversation_id provided")
        return jsonify({'error': f"[{err_point}] - No conversation_id provided"}), 400
    conversation_id = data['conversation_id']

    result = delete_conversation(conversation_id)
    return jsonify(result)

@conversations_bp.route("/get-saved-spurs", methods=["GET"])
@verify_token
@handle_errors
def fetch_saved_spurs_bp():
    user_id = getattr(g, "user_id", None)
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return jsonify({'error': f"[{err_point}] - Error:"}), 400

    filters = {}

    for field in ["variant", "situation"]:
        value = request.args.get(field)
        if value:
            filters[field] = value


    for date_field in ["date_from", "date_to"]:
        date_str = request.args.get(date_field)
        if date_str and isinstance(date_str, str):
            try:
                filters[date_field] = datetime.fromisoformat(date_str)
            except ValueError as e:
                err_point = __package__ or __name__
                logger.error(f"Error: {err_point}")
                return jsonify({'error': f"[{err_point}] - Error:"}), 400


    if request.args.get("keyword"):
        filters["keyword"] = request.args.get("keyword")


    sort = request.args.get("sort", "desc")
    if sort in ["asc", "desc"]:
        filters["sort"] = sort


    result = get_saved_spurs(user_id, filters)
    return jsonify(result)

@conversations_bp.route("/save-spur", methods=["POST"])
@verify_token
@handle_errors
def save_spur_bp():

    user_id = getattr(g, "user_id", None)
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return jsonify({'error': f"[{err_point}] - Error:"}), 400

    data = request.get_json()
    if not data or 'spur' not in data:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point} - No spur provided")
        return jsonify({'error': f"[{err_point}] - No spur provided"}), 400
    spur_dict = data['spur']
    if not isinstance(spur_dict, dict):
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point} - Invalid spur format")
        return jsonify({'error': f"[{err_point}] - Invalid spur format"}), 400
    spur = Spur.from_dict(spur_dict)

    result = save_spur(user_id, spur)
    return jsonify(result)


@conversations_bp.route("/delete-spur", methods=["DELETE"])
@verify_token
@handle_errors
def delete_saved_spurs_bp(spur_id):
    user_id = getattr(g, "user_id", None)
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return jsonify({'error': f"[{err_point}] - Error:"}), 400
    
    data = request.get_json()
    if not data or 'spur_id' not in data:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point} - No spur_id provided")
        return jsonify({'error': f"[{err_point}] - No spur_id provided"}), 400
    spur_id = data['spur_id']
    if not spur_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point} - spur_id is required")
        return jsonify({'error': f"[{err_point}] - spur_id is required"}), 400


    result = delete_saved_spur(user_id, spur_id)
    return jsonify(result)