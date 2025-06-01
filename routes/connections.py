from flask import Blueprint, request, jsonify, g, current_app
import logging
from typing import List, Dict, Any, Optional
from infrastructure.token_validator import verify_token, handle_errors
from infrastructure.logger import get_logger
from services.connection_service import (
    get_user_connections,
    set_active_connection_firestore,
    get_active_connection_firestore,
    clear_active_connection_firestore,
    create_connection_profile,
    get_connection_profile,
    update_connection_profile,
    delete_connection_profile,
    save_connection_profile
)
from services.storage_service import MAX_PROFILE_IMAGE_SIZE_BYTES, _allowed_profile_image_file
from utils.ocr_utils import perform_ocr_on_screenshot as perform_ocr
from utils.trait_manager import infer_personality_traits_from_openai_vision
from PIL import Image
import io
import base64
from werkzeug.datastructures import FileStorage

logger = get_logger(__name__)

connection_bp = Blueprint("connection", __name__)

# Constants
MAX_PROFILE_CONTENT_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_CONTENT_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg'}


def _allowed_content_image_file(filename: str) -> bool:
    """Check if content image filename has allowed extension."""
    if not filename:
        return False
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_CONTENT_IMAGE_EXTENSIONS


def _process_image_file(file_obj: FileStorage, max_size: int, 
                       allowed_extensions: set) -> Optional[bytes]:
    """
    Process and validate an uploaded image file.
    
    Args:
        file_obj: FileStorage object from Flask
        max_size: Maximum allowed file size in bytes
        allowed_extensions: Set of allowed file extensions
        
    Returns:
        Image bytes if valid, None otherwise
    """
    if not file_obj or not file_obj.filename:
        return None
        
    # Check extension
    if not ('.' in file_obj.filename and 
            file_obj.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
        logger.warning(f"Invalid file extension: {file_obj.filename}")
        return None
    
    # Read file
    file_obj.seek(0)
    image_bytes = file_obj.read()
    file_obj.seek(0)  # Reset for potential re-read
    
    # Check size
    if not image_bytes or len(image_bytes) > max_size:
        logger.warning(f"Invalid file size: {len(image_bytes) if image_bytes else 0} bytes")
        return None
        
    return image_bytes


def _extract_image_bytes_from_request(field_name: str) -> List[bytes]:
    """
    Extract image bytes from request, handling both file uploads and base64 data.
    
    Args:
        field_name: Name of the form field containing images
        
    Returns:
        List of image bytes
    """
    image_bytes_list = []
    
    # Check for file uploads
    if field_name in request.files:
        files = request.files.getlist(field_name)
        for file_obj in files:
            if file_obj and file_obj.filename:
                file_obj.seek(0)
                image_bytes = file_obj.read()
                if image_bytes:
                    image_bytes_list.append(image_bytes)
    
    # Check for base64 data in JSON
    elif request.is_json:
        data = request.get_json()
        if data and field_name in data:
            images_data = data.get(field_name, [])
            if isinstance(images_data, list):
                for img_data in images_data:
                    try:
                        # Handle base64 string
                        if isinstance(img_data, str):
                            if ',' in img_data and img_data.startswith('data:'):
                                img_data = img_data.split(',', 1)[1]
                            image_bytes = base64.b64decode(img_data)
                            image_bytes_list.append(image_bytes)
                        # Handle dict with 'data' field
                        elif isinstance(img_data, dict) and 'data' in img_data:
                            b64_data = img_data['data']
                            if ',' in b64_data and b64_data.startswith('data:'):
                                b64_data = b64_data.split(',', 1)[1]
                            image_bytes = base64.b64decode(b64_data)
                            image_bytes_list.append(image_bytes)
                    except Exception as e:
                        logger.error(f"Failed to decode base64 image: {e}")
                        continue
    
    return image_bytes_list


@connection_bp.route("/connection/save", methods=["POST"])
@verify_token
@handle_errors
def save_connection():
    """Save a complete connection profile from JSON data."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
        
        user_id = g.user.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401
            
        # Ensure user_id from auth is used
        if 'user_id' in data and data['user_id'] != user_id:
            logger.warning(f"User ID mismatch. Authenticated: {user_id}, Provided: {data['user_id']}")
            return jsonify({"error": "User ID mismatch"}), 403
        
        data['user_id'] = user_id
        
        # Import here to avoid circular import
        from class_defs.profile_def import ConnectionProfile
        
        # Create ConnectionProfile instance
        profile_obj = ConnectionProfile.from_dict(data)
        
        # Save the profile
        result = save_connection_profile(profile_obj)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in save_connection for user {g.user.get('user_id')}: {e}", exc_info=True)
        return jsonify({"error": f"Failed to save profile: {str(e)}"}), 500


@connection_bp.route("/connection/create", methods=["POST"])
@verify_token
@handle_errors
def create_connection():
    """Create a new connection profile with image processing."""
    try:
        user_id = g.user.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401

        # Get form data
        if request.is_json:
            form_data = request.get_json()
        else:
            form_data = request.form.to_dict()
        
        # Process profile content images (OCR)
        profile_content_texts = []
        content_images = _extract_image_bytes_from_request('profileContentImageBytes')
        
        for image_bytes in content_images:
            if not image_bytes or len(image_bytes) > MAX_PROFILE_CONTENT_IMAGE_SIZE_BYTES:
                logger.warning(f"Skipping oversized content image for user {user_id}")
                continue
                
            try:
                # Verify it's a profile content image
                # Note: classify_image needs to accept bytes, not FileStorage
                # You may need to update classify_image accordingly
                extracted_text = perform_ocr(image_bytes)
                if extracted_text:
                    profile_content_texts.extend(extracted_text)  # perform_ocr returns a list
            except Exception as e:
                logger.error(f"Error processing content image for user {user_id}: {e}", exc_info=True)

        # Process profile pictures (personality traits)
        personality_traits = []
        pic_images = _extract_image_bytes_from_request('connectionPicsImageBytes')
        
        for image_bytes in pic_images:
            if not image_bytes or len(image_bytes) > MAX_PROFILE_IMAGE_SIZE_BYTES:
                logger.warning(f"Skipping oversized profile pic for user {user_id}")
                continue
                
            try:
                # Get image format
                img = Image.open(io.BytesIO(image_bytes))
                content_type = f"image/{img.format.lower()}" if img.format else "image/jpeg"
                
                image_dict = {
                    "bytes": image_bytes,
                    "content_type": content_type
                }
                
                # Get personality traits
                trait_list = infer_personality_traits_from_openai_vision([image_dict])
                if trait_list and len(trait_list) > 0:
                    personality_traits.append({
                        "trait": trait_list[0].get("trait", ""),
                        "confidence": trait_list[0].get("confidence", 0.0)
                    })
            except Exception as e:
                logger.error(f"Error processing profile pic for user {user_id}: {e}", exc_info=True)
        
        # Create the connection profile
        result = create_connection_profile(
            data=form_data,
            connection_app_ocr_text_list=profile_content_texts,
            personality_traits_list=personality_traits
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in create_connection for user {g.user.get('user_id')}: {e}", exc_info=True)
        return jsonify({"error": "Failed to create connection profile"}), 500


@connection_bp.route("/connection/update", methods=["PATCH"])
@verify_token
@handle_errors
def update_connection():
    """Update an existing connection profile."""
    try:
        user_id = g.user.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401

        # Get form data
        if request.is_json:
            form_data = request.get_json()
        else:
            form_data = request.form.to_dict()
            
        connection_id = form_data.get("connection_id")
        if not connection_id:
            return jsonify({"error": "Missing connection_id"}), 400

        # Process profile content images if provided
        profile_content_texts = None
        if 'connectionProfileContent' in request.files or \
           (request.is_json and 'connectionProfileContent' in form_data):
            profile_content_texts = []
            content_images = _extract_image_bytes_from_request('connectionProfileContent')
            
            for image_bytes in content_images:
                if not image_bytes or len(image_bytes) > MAX_PROFILE_CONTENT_IMAGE_SIZE_BYTES:
                    continue
                    
                try:
                    extracted_text = perform_ocr(image_bytes)
                    if extracted_text:
                        profile_content_texts.extend(extracted_text)
                except Exception as e:
                    logger.error(f"Error processing content image: {e}", exc_info=True)

        # Process profile pictures if provided
        personality_traits = None
        if 'connectionProfilePics' in request.files or \
           (request.is_json and 'connectionProfilePics' in form_data):
            personality_traits = []
            pic_images = _extract_image_bytes_from_request('connectionProfilePics')
            
            for image_bytes in pic_images:
                if not image_bytes or len(image_bytes) > MAX_PROFILE_IMAGE_SIZE_BYTES:
                    continue
                    
                try:
                    img = Image.open(io.BytesIO(image_bytes))
                    content_type = f"image/{img.format.lower()}" if img.format else "image/jpeg"
                    
                    image_dict = {
                        "bytes": image_bytes,
                        "content_type": content_type
                    }

                    trait_list = infer_personality_traits_from_openai_vision([image_dict])
                    if trait_list and len(trait_list) > 0:
                        personality_traits.append({
                            "trait": trait_list[0].get("trait", ""),
                            "confidence": trait_list[0].get("confidence", 0.0)
                        })
                except Exception as e:
                    logger.error(f"Error processing profile pic: {e}", exc_info=True)
        
        # Get context block if provided
        connection_context_block = form_data.get("connection_context_block", "").strip()
        
        # Update the profile
        result = update_connection_profile(
            user_id=user_id,
            connection_id=connection_id,
            data=connection_context_block if connection_context_block else None,
            connection_app_ocr_text_list=profile_content_texts,
            updated_personality_traits=personality_traits
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in update_connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to update connection profile"}), 500


@connection_bp.route("/connection/fetch-all", methods=["GET"])
@verify_token
@handle_errors
def fetch_user_connections():
    """Fetch all connections for the authenticated user."""
    try:
        user_id = g.user.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401
            
        connections_list = get_user_connections(user_id)
        
        # Convert to dict format, handling None values
        connections_data = []
        for conn in connections_list:
            if conn:
                try:
                    connections_data.append(conn.to_dict())
                except Exception as e:
                    logger.error(f"Error converting connection to dict: {e}")
                    continue
                    
        return jsonify(connections_data)
        
    except Exception as e:
        logger.error(f"Error fetching connections: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch connections"}), 500


@connection_bp.route("/connection/set-active", methods=["POST"])
@verify_token
@handle_errors
def set_active_connection():
    """Set the active connection for the user."""
    try:
        user_id = g.user.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
            
        connection_id = data.get("connection_id")
        if not connection_id:
            return jsonify({"error": "Missing connection_id"}), 400
            
        result = set_active_connection_firestore(user_id, connection_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error setting active connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to set active connection"}), 500


@connection_bp.route("/connection/get-active", methods=["GET"])
@verify_token
@handle_errors
def get_active_connection():
    """Get the active connection ID for the user."""
    try:
        user_id = g.user.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401
            
        active_connection_id = get_active_connection_firestore(user_id)
        return jsonify({"connection_id": active_connection_id})
        
    except Exception as e:
        logger.error(f"Error getting active connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to get active connection"}), 500


@connection_bp.route("/connection/clear-active", methods=["DELETE"])
@verify_token
@handle_errors
def clear_active_connection():
    """Clear the active connection for the user."""
    try:
        user_id = g.user.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401
            
        result = clear_active_connection_firestore(user_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error clearing active connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to clear active connection"}), 500


@connection_bp.route("/connection/fetch-single", methods=["GET"])
@verify_token
@handle_errors
def fetch_single_connection():
    """Fetch a single connection profile by ID."""
    try:
        user_id = g.user.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401
            
        connection_id = request.args.get("connection_id")
        if not connection_id:
            return jsonify({"error": "Missing connection_id parameter"}), 400
            
        profile = get_connection_profile(user_id, connection_id)
        if profile:
            return jsonify(profile.to_dict())
        else:
            return jsonify({"error": "Connection profile not found"}), 404
            
    except Exception as e:
        logger.error(f"Error fetching connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch connection profile"}), 500


@connection_bp.route("/connection/delete", methods=["DELETE"])
@verify_token
@handle_errors
def delete_connection():
    """Delete a connection profile."""
    try:
        user_id = g.user.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
            
        connection_id = data.get("connection_id")
        if not connection_id:
            return jsonify({"error": "Missing connection_id"}), 400
            
        result = delete_connection_profile(user_id, connection_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error deleting connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to delete connection profile"}), 500