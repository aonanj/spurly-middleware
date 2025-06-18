from flask import Blueprint, request, jsonify, g
from infrastructure.token_validator import verify_token, handle_all_errors
from infrastructure.logger import get_logger
from infrastructure.id_generator import generate_conversation_id
from services.connection_service import get_active_connection_firestore
from services.gpt_service import get_spurs_for_output
from utils.middleware import enrich_context, sanitize_topic
from class_defs.conversation_def import Conversation
from services.storage_service import ConversationStorage
import json

generate_bp = Blueprint("generate", __name__)
logger = get_logger(__name__)

@generate_bp.route("/generate", methods=["POST"])
@verify_token
@handle_all_errors
##@enrich_context
##@sanitize_topic
def generate():
    """
    POST /generate

    Receives conversation context and images via multipart form data.

    Expected form fields:
    - conversation_id (str, optional)
    - situation (str, optional)
    - topic (str, optional)
    - user_id (str, optional): If not provided, extracted from auth token.
    - connection_id (str, optional)
    - conversation_messages (JSON string, optional): List of message dicts with 'sender' and 'text'.
    - images (files, optional): Multiple image files (message screenshots + profile screenshots)
    """
    # Check if request is multipart
    if not request.content_type or 'multipart/form-data' not in request.content_type:
        logger.error("Request is not multipart/form-data")
        return jsonify({'error': "Request must be multipart/form-data"}), 400

    # Extract form fields
    conversation_id = request.form.get("conversation_id", "")
    situation = request.form.get("situation", "")
    topic = request.form.get("topic", "")
    connection_id = request.form.get("connection_id", None)
    
    # Get user_id from auth token or form
    user_id = getattr(g, 'user_id', None)
    if not user_id:
        user_id = request.form.get("user_id", None)
        if not user_id:
            logger.error("User ID not found in g.user or form data for /generate route.")
            return jsonify({'error': "Authentication error: User ID not available."}), 401
    
    # Handle connection_id
    if not connection_id:
        logger.info(f"No connection_id provided for user {user_id}, attempting to get active connection.")
        connection_id = get_active_connection_firestore(user_id)
    
    # Parse conversation messages from JSON string
    conversation_messages = None
    conversation_messages_json = request.form.get("conversation_messages", None)
    if conversation_messages_json:
        try:
            conversation_messages = json.loads(conversation_messages_json)
            logger.info(f"Parsed {len(conversation_messages)} conversation messages")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse conversation_messages JSON: {e}")
            return jsonify({'error': "Invalid conversation_messages JSON format"}), 400
    
    # Process uploaded images
    images = []
    image_files = request.files.getlist("images")
    
    if image_files:
        logger.info(f"Received {len(image_files)} images")
        for idx, image_file in enumerate(image_files):
            if image_file and image_file.filename and allowed_file(image_file.filename):
                try:
                    # Read image data
                    image_data = image_file.read()
                    images.append({
                        'filename': image_file.filename or f'image_{idx}.jpg',
                        'data': image_data,
                        'mime_type': image_file.content_type or 'image/jpeg'
                    })
                    
                    # Option 2: Save to storage and pass URLs
                    # url = save_image_to_storage(image_data, user_id, idx)
                    # images.append({'url': url})
                    
                except Exception as e:
                    logger.error(f"Error processing image {idx}: {e}")
    
    # Save conversation if messages provided
    if conversation_messages:
        if not conversation_id or conversation_id.strip() == "":
            conversation_id = generate_conversation_id(user_id)
        
        conversation_dict = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "connection_id": connection_id,
            "conversation": conversation_messages,
        }
        if situation and situation.strip() != "":
            conversation_dict["situation"] = situation
        if topic and topic.strip() != "":
            conversation_dict["topic"] = topic
            
        conversation_obj = Conversation.from_dict(conversation_dict)
        storage = ConversationStorage()
        storage.save_conversation(conversation=conversation_obj)
    
    logger.info(f"Generating spurs for user_id: {user_id}, connection_id: {connection_id}, "
                f"conversation_id: '{conversation_id}', images: {len(images)}")

    # Generate spurs with images
    spur_objs = get_spurs_for_output(
        user_id=user_id,
        connection_id=connection_id,
        conversation_id=conversation_id,
        situation=situation,
        topic=topic,
        conversation_messages=conversation_messages,
        images=images  # Pass images to GPT service
    )
  
    spurs = [spur.to_dict() for spur in spur_objs]

    return jsonify({
        "user_id": user_id,
        "spurs": spurs,
    })


def allowed_file(filename: str) -> bool:
    """Check if the file extension is allowed."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Optional: Function to save images to storage (Firebase, S3, etc.)
def save_image_to_storage(image_data: bytes, user_id: str, index: int) -> str:
    """
    Save image to storage and return URL.
    Implement based on your storage solution (Firebase, S3, etc.)
    """
    # Example implementation would go here
    # return storage_url
    raise NotImplementedError("Image storage functionality not yet implemented")