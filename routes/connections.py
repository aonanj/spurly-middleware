from flask import Blueprint, request, jsonify, g, current_app
from typing import List, Optional
from datetime import datetime, timezone
from infrastructure.clients import get_firestore_db
import time
from infrastructure.token_validator import verify_token, handle_all_errors, verify_app_check_token
from infrastructure.logger import get_logger
from infrastructure.adapters import extract_image_bytes_from_request
from services.connection_service import (
    get_user_connections,
    set_active_connection_firestore,
    get_active_connection_firestore,
    clear_active_connection_firestore,
    create_connection_profile,
    get_connection_profile,
    update_connection_profile,
    delete_connection_profile,
    get_top_n_traits,
    save_connection_profile
)
from services.connection_service import get_profile_text
from utils.moderation import redact_flagged_sentences
from services.storage_service import MAX_PROFILE_IMAGE_SIZE_BYTES, upload_profile_image
from utils.ocr_utils import perform_ocr_on_screenshot as perform_ocr
from utils.trait_manager import infer_personality_traits_from_openai_vision
from PIL import Image
import io
import base64
from werkzeug.datastructures import FileStorage
from utils.usage_middleware import estimate_trait_inference_tokens
from services.billing_service import check_user_usage_limit

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
        logger.error(f"Invalid file extension: {file_obj.filename}")
        return None
    
    # Read file
    file_obj.seek(0)
    image_bytes = file_obj.read()
    file_obj.seek(0)  # Reset for potential re-read
    
    # Check size
    if not image_bytes or len(image_bytes) > max_size:
        logger.error(f"Invalid file size: {len(image_bytes) if image_bytes else 0} bytes")
        return None
        
    return image_bytes


def extract_image_bytes_from_request(field_name: str) -> List[bytes]:
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
    elif field_name in request.form:
        img_data = request.form.get(field_name)
        if img_data:
            try:
                image_bytes = base64.b64decode(img_data)
                image_bytes_list.append(image_bytes)

            except Exception as e:
                logger.error(f"Failed to decode base64 image: {e}")
                

    return image_bytes_list


@connection_bp.route("/connections/save", methods=["POST"])
@handle_all_errors
@verify_token
@verify_app_check_token
def save_connection():
    """Save a complete connection profile from JSON data."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
        
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = data.get("user_id")
            if not user_id:
                return jsonify({"error": "Authentication error"}), 401

        # Ensure user_id from auth is used
        if 'user_id' in data and data['user_id'] != user_id:
            logger.error(f"User ID mismatch. Authenticated: {user_id}, Provided: {data['user_id']}")
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
        logger.error(f"Error in save_connection for user {getattr(g, "user_id", None)}: {e}", exc_info=True)
        return jsonify({"error": f"Failed to save profile: {str(e)}"}), 500


@connection_bp.route("/connections/create", methods=["POST"])
@handle_all_errors
@verify_token
@verify_app_check_token
def create_connection():
    """Create a new connection profile with image processing."""
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401

        # Get form data
        if request.is_json:
            form_data = request.get_json()
            logger.error(f"JSON form data received: {form_data}")  # Debug log for JSON data
        else:
            form_data = request.form.to_dict()
            logger.error(f"Form data received: {form_data}")  # Debug log for form data
        connection_profile_pic_url = form_data.get('connection_profile_pic_url', '')
        form_data.update({'user_id': user_id})  
        
        connection_context_block = ""
        if form_data.get('connection_context_block') and len(form_data.get('connection_context_block', '').strip()) > 0 and form_data.get('connection_context_block', '').strip() != "":
            connection_context_block = redact_flagged_sentences(form_data['connection_context_block'])
            
        
        connection_data = {
            'user_id': user_id,
            'connection_name': form_data.get('connection_name', ''),
            'connection_age': form_data.get('connection_age', ''),
            'connection_context_block': connection_context_block
        }
        logger.error(f"Connection data: {connection_data}")  # Debug log for connection data
        # Process profile content images (OCR)
        profile_content_texts = []
        content_images = extract_image_bytes_from_request('profileContentImageBytes')
        
        for image_bytes in content_images:
            if not image_bytes or len(image_bytes) > MAX_PROFILE_CONTENT_IMAGE_SIZE_BYTES:
                logger.error(f"Skipping oversized content image for user {user_id}")
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
        pic_images_bytes = extract_image_bytes_from_request('connectionPicsImageBytes')
        image_data_list = []

        for image_bytes in pic_images_bytes:
            if not image_bytes or len(image_bytes) > MAX_PROFILE_IMAGE_SIZE_BYTES:
                logger.error(f"Skipping oversized profile pic for user {user_id}")
                continue
            
            try:
                # Prepare all valid images for a single API call
                img = Image.open(io.BytesIO(image_bytes))
                content_type = f"image/{img.format.lower()}" if img.format else "image/jpeg"
                image_data_list.append({
                    "bytes": image_bytes,
                    "content_type": content_type
                })
            except Exception as e:
                logger.error(f"Error preparing profile pic for user {user_id}: {e}", exc_info=True)

        # Make a single, efficient call to the AI model if there are any valid images
        if image_data_list:
            try:
                trait_list = infer_personality_traits_from_openai_vision(image_data_list, user_id)
                if trait_list:
                    # The function now returns the list directly in the desired format
                    personality_traits = trait_list
            except Exception as e:
                logger.error(f"Error inferring personality traits for user {user_id}: {e}", exc_info=True)
        
        # Create the connection profile
        result = create_connection_profile(
            data=connection_data,
            connection_profile_text=profile_content_texts,
            personality_traits_list=personality_traits,
            connection_profile_pic_url=connection_profile_pic_url
        )

        setattr(g, "active_connection_id", result.get("connection_id"))
        set_active_connection_firestore(user_id, result.get("connection_id"))

        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in create_connection for user {getattr(g, "user_id", None)}: {e}", exc_info=True)
        return jsonify({"error": "Failed to create connection profile"}), 500


@connection_bp.route("/connections/update", methods=["PATCH"])
@handle_all_errors
@verify_token
@verify_app_check_token
def update_connection():
    """Update an existing connection profile."""
    try:
        user_id = getattr(g, "user_id", None)
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
        
        name = None
        if 'connection_name' in form_data:
            name = form_data.get("connection_name", "").strip()
        
        age = None
        if 'connection_age' in form_data:
            age_value = form_data.get("connection_age")
            if isinstance(age_value, str):
                if age_value.strip():
                    try:
                        age = int(age_value)
                    except (ValueError, TypeError):
                        logger.error(f"Invalid age value: {age_value}")
                        age = None
            elif isinstance(age_value, int):
                age = age_value
            # For any other type (including None), age remains None

        # Process profile content images if provided
        profile_content_texts = None
        if 'connectionProfileContent' in request.files or \
           (request.is_json and 'connectionProfileContent' in form_data):
            profile_content_texts = []
            content_images = extract_image_bytes_from_request('connectionProfileContent')
            
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
            pic_images = extract_image_bytes_from_request('connectionProfilePics')
            
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
        connection_context_block = ""
        if form_data.get('connection_context_block') and len(form_data.get('connection_context_block', '').strip()) > 0 and form_data.get('connection_context_block', '').strip() != "":
            connection_context_block = redact_flagged_sentences(form_data['connection_context_block'])
        
        # Update the profile
        result = update_connection_profile(
            user_id=user_id,
            connection_id=connection_id,
            connection_name = name, 
            connection_age = age,
            data=connection_context_block if connection_context_block else None,
            connection_profile_text=profile_content_texts,
            updated_personality_traits=personality_traits,
            updated_profile_pic_url=form_data.get("connection_profile_pic_url")
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in update_connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to update connection profile"}), 500


@connection_bp.route("/connections/fetch-all", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def fetch_user_connections():
    """Fetch all connections for the authenticated user."""
    try:
        user_id = getattr(g, "user_id", None)
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


@connection_bp.route("/connections/set-active", methods=["POST"])
@handle_all_errors
@verify_token
@verify_app_check_token
def set_active_connection():
    """Set the active connection for the user."""
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
            
        connection_id = data.get("connection_id")
        if not connection_id:
            return jsonify({"error": "Missing connection_id"}), 400
            
        setattr(g, "active_connection_id", connection_id)
        result = set_active_connection_firestore(user_id, connection_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error setting active connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to set active connection"}), 500


@connection_bp.route("/connections/get-active", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def get_active_connection():
    """Get the active connection ID for the user."""
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = current_app.config.get("user_id", None)
            if not user_id:
                return jsonify({"error": "Authentication error"}), 401

        active_connection_id = get_active_connection_firestore(user_id)
        return jsonify({"connection_id": active_connection_id})
        
    except Exception as e:
        logger.error(f"Error getting active connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to get active connection"}), 500


@connection_bp.route("/connections/clear-active", methods=["DELETE"])
@handle_all_errors
@verify_token
@verify_app_check_token
def clear_active_connection():
    """Clear the active connection for the user."""
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = current_app.config.get("user_id", None)
            if not user_id:
                return jsonify({"error": "Authentication error"}), 401
        
        
        result = clear_active_connection_firestore(user_id)
        setattr(g, "active_connection_id", result.get("connection_id"))    
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error clearing active connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to clear active connection"}), 500


@connection_bp.route("/connections/fetch-single", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def fetch_single_connection():
    """Fetch a single connection profile by ID."""
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = current_app.config.get("user_id", None)
            if not user_id:
                logger.error
                return jsonify({"error": "Authentication error"}), 401
            
        connection_id = request.args.get("connection_id")
        if not connection_id:
            connection_id = get_active_connection_firestore(user_id)
            if not connection_id:
                logger.error("No connection_id provided and no active connection set")
                return jsonify({"error": "Missing connection_id parameter"}), 400
            
        profile = get_connection_profile(user_id, connection_id)
        if profile:
            return jsonify(profile.to_dict())
        else:
            logger.error(f"Connection profile not found for user {user_id} and connection {connection_id}")
            return jsonify({"error": "Connection profile not found"}), 404
            
    except Exception as e:
        logger.error(f"Error fetching connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch connection profile"}), 500


@connection_bp.route("/connections/delete", methods=["DELETE"])
@handle_all_errors
@verify_token
@verify_app_check_token
def delete_connection():
    """Delete a connection profile."""
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
            
        connection_id = data.get("connection_id")
        if not connection_id:
            return jsonify({"error": "Missing connection_id"}), 400
        
        result = delete_connection_profile(user_id, connection_id)
        
        if connection_id == get_active_connection_firestore(user_id):
            clear_result = clear_active_connection_firestore(user_id)
            setattr(g, "active_connection_id", clear_result.get("connection_id"))
            
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error deleting connection: {e}", exc_info=True)
        return jsonify({"error": "Failed to delete connection profile"}), 500

# Add these endpoints to routes/connections.py

@connection_bp.route("/connections/analyze-photos", methods=["POST"])
@handle_all_errors
@verify_token
@verify_app_check_token
def analyze_connection_photos():
    """
    Analyze up to 4 photos of a connection for personality traits only.
    The frontend handles face detection and cropping.
    """
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401

        # Get connection_id from request
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
            
        connection_id = data.get('connection_id')
        if not connection_id:
            return jsonify({"error": "Missing connection_id"}), 400

        # Check if connection exists
        connection_profile = get_connection_profile(user_id, connection_id)
        if not connection_profile:
            return jsonify({"error": "Connection profile not found"}), 404

        # Extract image bytes from request (up to 4 images)
        connection_photo_images = extract_image_bytes_from_request('connection_photos')
        
        if not connection_photo_images:
            return jsonify({"error": "No photos provided"}), 400
        
        if len(connection_photo_images) > 4:
            logger.error(f"User {user_id} uploaded {len(connection_photo_images)} photos, limiting to 4")
            connection_photo_images = connection_photo_images[:4]

        # Estimate tokens needed for photo analysis
        estimated_tokens = estimate_trait_inference_tokens(len(connection_photo_images))
        
        # Check if user has sufficient tokens
        limit_status = check_user_usage_limit(user_id)
        
        if "error" in limit_status:
            logger.error(f"Error checking usage limit for user {user_id}: {limit_status['error']}")
            return jsonify({'error': "Failed to check usage limits"}), 500
        
        remaining_tokens = limit_status.get("remaining_tokens", 0)
        token_margin = remaining_tokens * 0.1  # 10% margin
        
        if remaining_tokens < (estimated_tokens - token_margin):
            logger.error(f"User {user_id} has insufficient tokens: {remaining_tokens} < {estimated_tokens}")
            return jsonify({
                "error": "Insufficient tokens",
                "message": f"token balance: {remaining_tokens}. tokens required for analyzing connection photo: {estimated_tokens}.",
                "remaining_tokens": remaining_tokens,
                "required_tokens": estimated_tokens,
                "subscription_tier": limit_status.get("subscription_tier", "unknown"),
                "usage_percentage": limit_status.get("usage_percentage", 0),
                "upgrade_required": True
            }), 402  # Payment Required

        # Validate image sizes
        valid_images = []
        for i, image_bytes in enumerate(connection_photo_images):
            if not image_bytes or len(image_bytes) > MAX_PROFILE_IMAGE_SIZE_BYTES:
                logger.error(f"Skipping oversized photo {i} for connection {connection_id}")
                continue
            valid_images.append(image_bytes)
        
        if not valid_images:
            return jsonify({"error": "No valid photos provided"}), 400

        personality_traits = []

        # Analyze all photos for personality traits
        try:
            # Prepare images for OpenAI Vision analysis
            image_data_list = []
            for i, image_bytes in enumerate(valid_images):
                try:
                    img = Image.open(io.BytesIO(image_bytes))
                    content_type = f"image/{img.format.lower()}" if img.format else "image/jpeg"
                    
                    image_data_list.append({
                        "bytes": image_bytes,
                        "content_type": content_type
                    })
                except Exception as e:
                    logger.error(f"Error preparing image {i} for analysis: {e}")
                    continue
            
            if image_data_list:
                # Analyze all images for personality traits
                trait_results = infer_personality_traits_from_openai_vision(image_data_list, user_id)
                if trait_results:
                    personality_traits = trait_results
                    logger.error(f"LOG.INFO: Analyzed {len(image_data_list)} photos and extracted {len(personality_traits)} traits")
                else:
                    logger.error(f"No personality traits extracted from {len(image_data_list)} photos")
            
        except Exception as e:
            logger.error(f"Error analyzing photos for personality traits: {e}", exc_info=True)

        # Update connection profile with personality traits
        if personality_traits:
            try:
                db = get_firestore_db()
                doc_ref = db.collection("users").document(user_id).collection("connections").document(connection_id)
                
                # Get current profile data
                current_doc = doc_ref.get()
                if not current_doc.exists:
                    return jsonify({"error": "Connection profile not found"}), 404
                
                current_data = current_doc.to_dict()
                
                # Merge personality traits and keep top 5
                existing_traits = current_data.get('personality_traits', [])
                all_traits = existing_traits + personality_traits
                top_traits = get_top_n_traits(all_traits, 5)
                
                # Update profile
                update_data = {
                    'personality_traits': top_traits,
                    'updated_at': datetime.now(timezone.utc)
                }
                
                doc_ref.update(update_data)
                
                logger.error(f"LOG.INFO: Updated connection {connection_id} with personality traits")
                
            except Exception as e:
                logger.error(f"Error updating connection profile: {e}", exc_info=True)
                return jsonify({"error": "Failed to update connection profile"}), 500

        response_data = {
            "success": True,
            "message": f"Successfully analyzed {len(valid_images)} photo(s)",
            "connection_id": connection_id,
            "photos_analyzed": len(valid_images),
            "traits_extracted": len(personality_traits)
        }
        
        if personality_traits:
            response_traits = [t.copy() for t in personality_traits]
            for trait in response_traits:
                if 'confidence' in trait and isinstance(trait['confidence'], float):
                    trait['confidence'] = f"{trait['confidence']:.2f}"
            response_data["personality_traits"] = response_traits
        
        return jsonify(response_data)

        
    except Exception as e:
        logger.error(f"Error in analyze_connection_photos: {e}", exc_info=True)
        return jsonify({"error": "Failed to analyze connection photos"}), 500


@connection_bp.route("/connections/upload-face-photo", methods=["POST"])
@handle_all_errors
@verify_token
@verify_app_check_token
def upload_face_photo():
    """
    Upload a pre-cropped face photo from the frontend.
    This endpoint expects the frontend to have already detected and cropped the face.
    """
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401

        # Get connection_id from form data
        connection_id = request.form.get('connection_id')
        if not connection_id:
            return jsonify({"error": "Missing connection_id"}), 400

        # Check if connection exists
        connection_profile = get_connection_profile(user_id, connection_id)
        if not connection_profile:
            return jsonify({"error": "Connection profile not found"}), 404

        # Get the uploaded face photo
        if 'connection_profile_pic_url' not in request.files:
            return jsonify({"error": "No face photo provided"}), 400
        
        face_photo_file = request.files['connection_profile_pic_url']
        if not face_photo_file or not face_photo_file.filename:
            return jsonify({"error": "Invalid face photo file"}), 400

        # Read the image data
        face_photo_file.seek(0)
        image_bytes = face_photo_file.read()
        
        if not image_bytes or len(image_bytes) > MAX_PROFILE_IMAGE_SIZE_BYTES:
            return jsonify({"error": "Face photo is too large or empty"}), 400

        # Upload to storage
        try:
            # Generate filename
            timestamp = int(time.time())
            filename = f"connection_face_{connection_id}_{timestamp}.jpg"
            
            # Upload to GCS
            photo_url = upload_profile_image(
                user_id=user_id,
                connection_id=connection_id,
                image_bytes=image_bytes,
                original_filename=filename,
                content_type="image/jpeg"
            )
            
            # Update connection profile with photo URL
            db = get_firestore_db()
            doc_ref = db.collection("users").document(user_id).collection("connections").document(connection_id)
            
            update_data = {
                'connection_profile_pic_url': photo_url,
                'updated_at': datetime.now(timezone.utc)
            }
            
            doc_ref.update(update_data)
            
            logger.error(f"LOG.INFO: Successfully uploaded face photo for connection {connection_id}")
            
            return jsonify({
                "success": True,
                "message": "Face photo uploaded successfully",
                "connection_profile_pic_url": photo_url,
                "connection_id": connection_id
            })
            
        except Exception as e:
            logger.error(f"Error uploading face photo: {e}", exc_info=True)
            return jsonify({"error": "Failed to upload face photo"}), 500
            
    except Exception as e:
        logger.error(f"Error in upload_face_photo: {e}", exc_info=True)
        return jsonify({"error": "Failed to process face photo upload"}), 500


@connection_bp.route("/connections/delete-profile-photo", methods=["DELETE"])
@handle_all_errors
@verify_token
@verify_app_check_token
def delete_profile_photo():
    """Delete the profile photo from a connection."""
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
            
        connection_id = data.get('connection_id')
        
        if not connection_id:
            return jsonify({"error": "Missing connection_id"}), 400

        # Get connection profile
        connection_profile = get_connection_profile(user_id, connection_id)
        if not connection_profile:
            return jsonify({"error": "Connection profile not found"}), 404

        # Update profile to remove the photo URL
        try:
            db = get_firestore_db()
            doc_ref = db.collection("users").document(user_id).collection("connections").document(connection_id)
            
            current_doc = doc_ref.get()
            if not current_doc.exists:
                return jsonify({"error": "Connection profile not found"}), 404
            
            current_data = current_doc.to_dict()
            current_photo_url = current_data.get('connection_profile_pic_url')
            
            if not current_photo_url:
                return jsonify({"error": "No profile photo to delete"}), 404
            
            # Remove the photo URL
            update_data = {
                'connection_profile_pic_url': None,
                'updated_at': datetime.now(timezone.utc)
            }
            
            doc_ref.update(update_data)
            
            logger.error(f"LOG.INFO: Removed profile photo from connection {connection_id}")
            
            # TODO: Optionally delete the actual file from GCS
            # This would require parsing the GCS path from the URL
            
            return jsonify({
                "success": True,
                "message": "Profile photo deleted successfully",
                "connection_id": connection_id
            })
            
        except Exception as e:
            logger.error(f"Error deleting profile photo: {e}", exc_info=True)
            return jsonify({"error": "Failed to delete profile photo"}), 500
            
    except Exception as e:
        logger.error(f"Error in delete_profile_photo: {e}", exc_info=True)
        return jsonify({"error": "Failed to delete profile photo"}), 500


@connection_bp.route("/connections/get-profile-photo", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def get_profile_photo():
    """Get profile photo URL for a connection."""
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            return jsonify({"error": "Authentication error"}), 401

        connection_id = request.args.get('connection_id')
        if not connection_id:
            return jsonify({"error": "Missing connection_id parameter"}), 400

        # Get connection profile
        connection_profile = get_connection_profile(user_id, connection_id)
        if not connection_profile:
            return jsonify({"error": "Connection profile not found"}), 404

        profile_dict = connection_profile.to_dict()
        connection_profile_pic_url = profile_dict.get('connection_profile_pic_url')
        
        return jsonify({
            "success": True,
            "connection_id": connection_id,
            "connection_profile_pic_url": connection_profile_pic_url
        })
        
    except Exception as e:
        logger.error(f"Error in get_profile_photo: {e}", exc_info=True)
        return jsonify({"error": "Failed to get profile photo"}), 500

@connection_bp.route('/connections/create_multipart_form', methods=['POST'])
@handle_all_errors
@verify_token
@verify_app_check_token
def create_connection_with_photos():
    """
    Create a new connection with multipart form data
    Expects:
    - connection_id (text)
    - connection_name (text)
    - connection_age (text/number)
    - connection_context_block (text)
    - connection_face_photo_url (text, optional)
    - ocr_images[] (files)
    - profile_images[] (files)
    """
    user_id = getattr(g, "user_id", None)
    connection_id = request.form.get('connection_id')
    
    
    connection_context_block = ""
    if request.form.get('connection_context_block') and len(request.form.get('connection_context_block', '').strip()) > 0 and request.form.get('connection_context_block', '').strip() != "":
        connection_context_block = redact_flagged_sentences(request.form['connection_context_block'])
    connection_data = {
        'user_id': user_id,
        'connection_id': connection_id,
        'connection_name': request.form.get('connection_name'),
        'connection_age': request.form.get('connection_age'),
        'connection_context_block': connection_context_block,
       
    }
    
    # Validate required fields
    if not connection_data['connection_id']:
        return jsonify({"error": "Missing connection_id"}), 400
    
    # Process OCR images
    try:
        ocr_image_bytes = extract_image_bytes_from_request('profileContentImageBytes')
        connection_profile_text = []
        for image_bytes in ocr_image_bytes:
            # Process each OCR image
            result = perform_ocr(image_bytes)
            connection_profile_text.extend(result)

    except Exception as e:
        logger.error(f"Error getting OCR files: {e}", exc_info=True)
        return jsonify({"error": "Failed to get OCR files"}), 500
    
    # Process profile images (store them)
    try:
        profile_image_bytes = extract_image_bytes_from_request('connectionPicsImageBytes')
        connection_traits = []
        image_dict = []
        for image_bytes in profile_image_bytes:
            try:
                # Use PIL to determine the image format from bytes
                img = Image.open(io.BytesIO(image_bytes))
                image_format = img.format.lower() if img.format else "jpeg"
                image_dict.append({
                    "bytes": image_bytes,
                    "content_type": f"image/{image_format}"
                })
            except Exception as e:
                logger.error(f"Error processing image bytes: {e}")
                # Fallback to default format
                image_dict.append({
                    "bytes": image_bytes,
                    "content_type": "image/jpeg"
                })
        connection_traits = infer_personality_traits_from_openai_vision(image_dict)
    except Exception as e:
        logger.error(f"Error getting profile images: {e}", exc_info=True)
        return jsonify({"error": "Failed to get profile images"}), 500
    

    connection_profile_pic_url = ""
    if request.form.get('connection_profile_pic_url') and request.form.get('connection_profile_pic_url') != "":
        connection_profile_pic_url = request.form.get('connection_profile_pic_url')
    else:
        connection_profile_pic_url = ""

    # Create connection in database
    try:
        connection = create_connection_profile(connection_data, connection_profile_text, connection_traits, connection_profile_pic_url or "")
        return jsonify({
            'connection_id': connection_id,
            'message': 'Connection created successfully'
        }), 201
    except Exception as e:
        logger.error(f"Error creating connection profile: {e}", exc_info=True)
        return jsonify({"error": "Failed to create connection profile"}), 500

@connection_bp.route("/connections/extract-profile-data", methods=["POST"])
@handle_all_errors
@verify_token
@verify_app_check_token
def extract_profile_data():
    """Extract profile data from the request."""
    
    if request.is_json:
        form_data = request.get_json()
        logger.error(f"JSON form data received: {form_data}") 
    else:
        form_data = request.form.to_dict()
        logger.error(f"Form data received: {form_data}") 
    
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = current_app.config.get("user_id", None)
            if not user_id:
                user_id = form_data.get('user_id', None)
                return jsonify({"error": "Authentication error"}), 401
            
        
        img_list = extract_image_bytes_from_request('image')
        img_bytes = img_list[0] if img_list else None


        if not img_bytes:
            return jsonify({"error": "No profile image provided"}), 400

        if len(img_list) > 1:
            logger.error(f"User {user_id} uploaded {len(img_list)} photos, limiting to 1")

        # Validate image sizes
        if not img_bytes or len(img_bytes) > MAX_PROFILE_IMAGE_SIZE_BYTES:
            return jsonify({"error": "Profile image is too large or empty"}), 400

        result = get_profile_text(user_id, img_bytes)

        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error in extract_profile_data for user {getattr(g, 'user_id', None)}: {e}", exc_info=True)
        return jsonify({"error": "Failed to extract profile data"}), 500