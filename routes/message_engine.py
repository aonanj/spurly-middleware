from flask import Blueprint, request, jsonify, g
from infrastructure.token_validator import verify_token, handle_errors
from infrastructure.logger import get_logger
from infrastructure.id_generator import get_null_connection_id, generate_conversation_id
from services.connection_service import get_active_connection_firestore
from services.gpt_service import get_spurs_for_output
from utils.middleware import enrich_context, sanitize_topic

generate_bp = Blueprint("generate", __name__)
logger = get_logger(__name__)

@generate_bp.route("/generate", methods=["POST"])
@verify_token
@handle_errors
@enrich_context
@sanitize_topic
def generate():
    """
    POST /generate

    Receives conversation context and user/POI sketches, sends to GPT engine for Spur generation.

    Expected JSON fields:
    - conversation_id (str)
    - connection_id (str)
    - situation (str)
    - topic (str)
    - profile_ocr_texts (list[str], optional): Text from connection's profile OCR.
    - photo_analysis_data (list[dict], optional): Analysis from connection's photos.
    """
    data = request.get_json()
    if not data:
        logger.warning("No JSON data received in /generate request.")
        return jsonify({'error': "Request must be JSON"}), 400

    user_id_from_g = getattr(g, 'user_id', None)     
    if not user_id_from_g:
        logger.error("User ID not found in g.user for /generate route.")
        return jsonify({'error': "Authentication error: User ID not available."}), 401
    
    user_id = user_id_from_g # Use the authenticated user_id

    conversation_id = data.get("conversation_id", "")
    if not conversation_id or conversation_id.strip() == "":
        conversation_id = generate_conversation_id(user_id)  # Generate a new conversation ID if not provided
        
    conversation_messages = data.get("conversation_messages", None)
    connection_id = data.get("connection_id", "") # Client should provide this



    if not connection_id:
        # Fallback to active connection if not provided by client; consider if this is desired
        # If OCR data is connection-specific, client should always provide connection_id.
        logger.info(f"No connection_id provided for user {user_id}, attempting to get active connection.")
        connection_id = get_active_connection_firestore(user_id)
        connection_id = get_null_connection_id(user_id)
    
    logger.info(f"Generating spurs for user_id: {user_id}, connection_id: {connection_id}, conversation_id: '{conversation_id}'")


    situation = data.get("situation", "")
    topic = data.get("topic", "")

    spur_objs = get_spurs_for_output(
        user_id=user_id,
        connection_id=connection_id,
        conversation_id=conversation_id,
        situation=situation,
        topic=topic,
        conversation_messages=conversation_messages,       # Pass new data
    )
  
    spurs = [spur.to_dict() for spur in spur_objs]

    return jsonify({
        "user_id": user_id,
        "spurs": spurs,
    })