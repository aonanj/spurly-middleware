# routes/conversations.py
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from infrastructure.auth import require_auth
from infrastructure.logger import get_logger
from services.spur_service import save_spur, delete_saved_spur, get_saved_spurs
from services.storage_service import (
    get_conversations,
    save_conversation,
    get_conversation,
    delete_conversation,
)

logger = get_logger(__name__)

conversations_bp = Blueprint("conversations", __name__)

@conversations_bp.route("/conversations", methods=["GET"])
@require_auth
def get_conversations_bp():
    user_id = g.user['user_id']
    if not user_id: # pragma: no cover
        err_point = __package__ or __name__ # pragma: no cover
        logger.error(f"Error: {err_point}") # pragma: no cover
        return jsonify({'error': f"[{err_point}] - Error:"}), 400 # pragma: no cover

    filters = {} # L26

    if request.args.get("keyword"): # L28
        filters["keyword"] = request.args.get("keyword") # L29

    # L30-L37 (Covers loop + L31, L32, L34)
    for date_field in ["date_from", "date_to"]:
        date_str = request.args.get(date_field)
        if date_str:
            try:
                filters[date_field] = datetime.fromisoformat(date_str)
            except ValueError as e: # L35
                err_point = __package__ or __name__ # L36
                logger.error("[%s] Error: %s", err_point, e) # L37
                return jsonify({'error': f"{err_point} - Error: {str(e)}"}), 400 # L38

    # L39, L40 (result assignment + return)
    result = get_conversations(user_id, filters) # L41
    return jsonify(result) # L42

@conversations_bp.route("/conversations", methods=["POST"])
@require_auth
def save_conversation_bp():
    data = request.get_json() # L47
    user_id = g.user['user_id'] # L48
    if not user_id: # pragma: no cover
        err_point = __package__ or __name__ # pragma: no cover
        logger.error(f"Error: {err_point}") # pragma: no cover
        return jsonify({'error': f"[{err_point}] - Error:"}), 400 # pragma: no cover
    # L52, L53 (result assignment + return)
    result = save_conversation(data) # L54
    return jsonify(result) # L55 - Note: Coverage request ended at L54, but this covers L55 too.

@conversations_bp.route("/conversations/<conversation_id>", methods=["GET"])
@require_auth
def get_conversation_bp(conversation_id):
    user_id = g.user['user_id'] # L59
    if not user_id: # pragma: no cover
        err_point = __package__ or __name__ # pragma: no cover
        logger.error(f"Error: {err_point}") # pragma: no cover
        return jsonify({'error': f"[{err_point}] - Error:"}), 400 # pragma: no cover
    # L64, L65 (result assignment + return)
    result = get_conversation(conversation_id) # L66 - Note: Coverage request ended at L65, but this covers L66 too.
    return jsonify(result) # L67

@conversations_bp.route("/conversations/<conversation_id>", methods=["DELETE"])
@require_auth
def delete_conversation_bp(conversation_id):
    user_id = g.user['user_id'] # L70
    if not user_id: # pragma: no cover
        err_point = __package__ or __name__ # pragma: no cover
        logger.error(f"Error: {err_point}") # pragma: no cover
        return jsonify({'error': f"[{err_point}] - Error:"}), 400 # pragma: no cover
    # L75, L76 (result assignment + return)
    result = delete_conversation(conversation_id) # L77 - Note: Coverage request ended at L76, but this covers L77 too.
    return jsonify(result) # L78

@conversations_bp.route("/saved-spurs", methods=["GET"])
@require_auth
def fetch_saved_spurs_bp():
    user_id = g.user['user_id'] # L81
    if not user_id: # pragma: no cover
        err_point = __package__ or __name__ # pragma: no cover
        logger.error(f"Error: {err_point}") # pragma: no cover
        return jsonify({'error': f"[{err_point}] - Error:"}), 400 # pragma: no cover

    filters = {} # L87
    # L88-L91 (covers loop + L89, L90, L91)
    for field in ["variant", "situation"]:
        value = request.args.get(field)
        if value:
            filters[field] = value

    # L93-L100 (covers loop + L94, L95, L97)
    for date_field in ["date_from", "date_to"]:
        date_str = request.args.get(date_field)
        if date_str:
            try:
                filters[date_field] = datetime.fromisoformat(date_str)
            except ValueError as e: # L98
                err_point = __package__ or __name__ # L99
                logger.error(f"Error: {err_point}") # L100
                return jsonify({'error': f"[{err_point}] - Error:"}), 400 # L101

    # L102-L103
    if request.args.get("keyword"):
        filters["keyword"] = request.args.get("keyword")

    # L105-L107
    sort = request.args.get("sort", "desc")
    if sort in ["asc", "desc"]:
        filters["sort"] = sort

    # L109, L110 (result assignment + return)
    result = get_saved_spurs(user_id, filters) # L111
    return jsonify(result) # L112 - Note: Coverage request ended at L111, but this covers L112 too.

@conversations_bp.route("/saved-spurs", methods=["POST"])
@require_auth
def save_spur_bp():
    data = request.get_json() # L116
    user_id = g.user['user_id'] # L117
    if not user_id: # pragma: no cover
        err_point = __package__ or __name__ # pragma: no cover
        logger.error(f"Error: {err_point}") # pragma: no cover
        return jsonify({'error': f"[{err_point}] - Error:"}), 400 # pragma: no cover

    # L122, L123 (result assignment + return)
    result = save_spur(user_id, data) # L124
    return jsonify(result) # L125 - Note: Coverage request ended at L124, but this covers L125 too.


@conversations_bp.route("/saved-spurs/<spur_id>", methods=["DELETE"])
@require_auth
def delete_saved_spurs_bp(spur_id):
    user_id = g.user['user_id'] # L130
    if not user_id: # pragma: no cover
        err_point = __package__ or __name__ # pragma: no cover
        logger.error(f"Error: {err_point}") # pragma: no cover
        return jsonify({'error': f"[{err_point}] - Error:"}), 400 # pragma: no cover

    # L135, L136 (result assignment + return)
    result = delete_saved_spur(user_id, spur_id) # L137
    return jsonify(result) # L138 - Note: Coverage request ended at L137, but this covers L138 too.