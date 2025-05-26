from flask import Blueprint, request, jsonify, g, current_app
from infrastructure.auth import require_auth
# from infrastructure.id_generator import get_null_connection_id # Not directly used in create/update logic now
from infrastructure.logger import get_logger
from services.connection_service import (
     # save_connection_profile, # This route uses its own ConnectionProfile creation
     get_user_connections,
     set_active_connection_firestore,
     get_active_connection_firestore,
     clear_active_connection_firestore,
     create_connection_profile,
     get_connection_profile,
     update_connection_profile,
     delete_connection_profile,
     save_connection_profile # Re-added for the /save route
)
# storage_service imports for validation constants
from services.storage_service import MAX_PROFILE_IMAGE_SIZE_BYTES, _allowed_profile_image_file 
from utils.extract_profile_snippet import extract_profile_snippet

logger = get_logger(__name__)

connection_bp = Blueprint("connection", __name__)

MAX_PROFILE_CONTENT_IMAGE_SIZE_BYTES = 10 * 1024 * 1024 
ALLOWED_CONTENT_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def _allowed_content_image_file(filename: str) -> bool:
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_CONTENT_IMAGE_EXTENSIONS

@connection_bp.route("/connection/save", methods=["POST"])
@require_auth
def save_connection():
    # This route is for saving a complete JSON profile object
    # It's different from create/update which handle file uploads for specific fields
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400
    
    user_id = g.user.get('user_id')
    # Ensure user_id from auth is used
    if 'user_id' in data and data['user_id'] != user_id:
        logger.warning(f"User ID mismatch in /connection/save. Authenticated: {user_id}, Provided: {data['user_id']}")
        return jsonify({"error": "User ID mismatch"}), 403
    data['user_id'] = user_id # Enforce authenticated user_id

    try:
        from class_defs.profile_def import ConnectionProfile 
        # Create ConnectionProfile instance from the provided JSON data
        profile_obj = ConnectionProfile.from_dict(data)
        # Ensure connection_id is set if it's an update, or handle if it should be new
        if not profile_obj.connection_id and 'connection_id' in data : # If it was in data but not set by from_dict (e.g. if from_dict filters strictly)
             profile_obj.connection_id = data['connection_id']
        elif not profile_obj.connection_id : # If it's a new profile being saved this way without an ID
             logger.warning(f"Attempt to save connection profile via /save without connection_id for user {user_id}. This route might be intended for updates with ID.")
             # Decide behavior: error out, or generate ID (though create_connection is for that)
             # For now, assuming save_connection_profile service can handle this or it's an update.
             pass


    except Exception as e:
        logger.error(f"Error creating ConnectionProfile from save_connection data for user {user_id}: {e}", exc_info=True)
        return jsonify({"error": f"Invalid profile data: {str(e)}"}), 400
        
    result = save_connection_profile(profile_obj) 
    return jsonify(result)


@connection_bp.route("/connection/create", methods=["POST"])
@require_auth
def create_connection():
    user_id = g.user.get('user_id')
    if not user_id: 
        logger.error("User ID not found in g.user for /connection/create.")
        return jsonify({"error": "Authentication error: User ID not available."}), 401

    form_data = request.form.to_dict() # Basic profile fields
    
    # Process connectionProfileContent (OCR Images)
    profile_content_texts = []
    connection_profile_content_files_fs = request.files.getlist('connectionProfileContent')
    for file_fs in connection_profile_content_files_fs:
        if file_fs and file_fs.filename:
            original_filename = file_fs.filename
            if not _allowed_content_image_file(original_filename):
                logger.warning(f"User {user_id} skipped invalid content file type in create: {original_filename}")
                continue 
            image_bytes = file_fs.read(); file_fs.seek(0)
            if not image_bytes or len(image_bytes) > MAX_PROFILE_CONTENT_IMAGE_SIZE_BYTES:
                logger.warning(f"User {user_id} skipped content file in create (size issue): {original_filename}")
                continue
            try:
                extracted_text = extract_profile_snippet(image_bytes=image_bytes)
                if extracted_text: profile_content_texts.append(extracted_text)
            except Exception as e:
                logger.error(f"Error processing content file {original_filename} for create (user {user_id}): {e}", exc_info=True)

    # Process connectionProfilePics (for OpenAI Trait Inference)
    profile_pics_to_process_for_traits = []
    connection_profile_pics_fs = request.files.getlist('connectionProfilePics')
    for file_fs in connection_profile_pics_fs:
        if file_fs and file_fs.filename:
            original_filename = file_fs.filename
            if not _allowed_profile_image_file(original_filename): 
                logger.warning(f"User {user_id} skipped invalid profile pic type in create: {original_filename}")
                continue
            image_bytes = file_fs.read(); file_fs.seek(0)
            if not image_bytes or len(image_bytes) > MAX_PROFILE_IMAGE_SIZE_BYTES: 
                logger.warning(f"User {user_id} skipped profile pic in create (size issue): {original_filename}")
                continue
            profile_pics_to_process_for_traits.append({
                "bytes": image_bytes, "filename": original_filename, "content_type": file_fs.content_type
            })
            
    # Call service: removed 'images' and 'links' args for old trait system
    result = create_connection_profile(
        data=form_data, 
        profile_text_content_list=profile_content_texts,
        profile_pics_raw_files=profile_pics_to_process_for_traits 
    )
    return jsonify(result)


@connection_bp.route("/connection/update", methods=["PATCH"])
@require_auth
def update_connection():
    user_id = g.user.get('user_id')
    if not user_id:
        logger.error("User ID not found in g.user for /connection/update.")
        return jsonify({"error": "Authentication error: User ID not available."}), 401

    form_data = request.form.to_dict()
    connection_id = form_data.get("connection_id")
    if not connection_id:
        return jsonify({'error': "Missing connection_id for update"}), 400

    # Process connectionProfileContent (OCR Images) if provided for update
    profile_content_texts_update = None 
    if 'connectionProfileContent' in request.files: # Check if field was sent
        profile_content_texts_update = []
        connection_profile_content_files_fs = request.files.getlist('connectionProfileContent')
        for file_fs in connection_profile_content_files_fs:
            if file_fs and file_fs.filename:
                original_filename = file_fs.filename
                if not _allowed_content_image_file(original_filename):
                    logger.warning(f"User {user_id} skipped invalid content file type for update: {original_filename}")
                    continue
                image_bytes = file_fs.read(); file_fs.seek(0)
                if not image_bytes or len(image_bytes) > MAX_PROFILE_CONTENT_IMAGE_SIZE_BYTES:
                    logger.warning(f"User {user_id} skipped content file for update (size issue): {original_filename}")
                    continue
                try:
                    extracted_text = extract_profile_snippet(image_bytes=image_bytes)
                    if extracted_text: profile_content_texts_update.append(extracted_text)
                except Exception as e:
                    logger.error(f"Error processing content file {original_filename} for update (user {user_id}): {e}", exc_info=True)

    # Process connectionProfilePics (for OpenAI Trait Inference) if provided for update
    profile_pics_to_process_for_traits_update = None 
    if 'connectionProfilePics' in request.files: # Check if field was sent
        profile_pics_to_process_for_traits_update = []
        connection_profile_pics_fs = request.files.getlist('connectionProfilePics')
        for file_fs in connection_profile_pics_fs:
            if file_fs and file_fs.filename:
                original_filename = file_fs.filename
                if not _allowed_profile_image_file(original_filename):
                    logger.warning(f"User {user_id} skipped invalid profile pic type for update: {original_filename}")
                    continue
                image_bytes = file_fs.read(); file_fs.seek(0)
                if not image_bytes or len(image_bytes) > MAX_PROFILE_IMAGE_SIZE_BYTES:
                    logger.warning(f"User {user_id} skipped profile pic for update (size issue): {original_filename}")
                    continue
                profile_pics_to_process_for_traits_update.append({
                    "bytes": image_bytes, "filename": original_filename, "content_type": file_fs.content_type
                })
    
    update_data_payload = {k: v for k, v in form_data.items() if k not in {"user_id", "connection_id"}}
    
    # Call service: removed 'images' and 'links' args for old trait system
    result = update_connection_profile(
        user_id=user_id,
        connection_id=connection_id,
        data=update_data_payload, 
        profile_text_content_list=profile_content_texts_update, 
        profile_pics_raw_files=profile_pics_to_process_for_traits_update 
    )
    return jsonify(result)

# --- Other existing routes (fetch-all, set-active, get-active, clear-active, fetch-single, delete) ---
# These should remain as previously defined, ensuring they use g.user.get('user_id')
# and handle ConnectionProfile objects correctly (e.g., .to_dict() for jsonify).

@connection_bp.route("/connection/fetch-all", methods=["GET"])
@require_auth
def fetch_user_connections():
    user_id = g.user.get('user_id')
    if not user_id: return jsonify({"error": "Authentication error"}), 401
    connections_list = get_user_connections(user_id) 
    return jsonify([conn.to_dict() for conn in connections_list if conn]) # Added if conn to handle Nones from service

@connection_bp.route("/connection/set-active", methods=["POST"])
@require_auth
def set_active_connection():
    data = request.get_json()
    if not data: return jsonify({"error": "Invalid JSON payload"}), 400
    user_id = g.user.get('user_id')
    if not user_id: return jsonify({"error": "Authentication error"}), 401
    connection_id = data.get("connection_id") 
    result = set_active_connection_firestore(user_id, connection_id)
    return jsonify(result)

@connection_bp.route("/connection/get-active", methods=["GET"])
@require_auth
def get_active_connection():
    user_id = g.user.get('user_id')
    if not user_id: return jsonify({"error": "Authentication error"}), 401
    active_connection_id_val = get_active_connection_firestore(user_id) 
    return jsonify({"connection_id": active_connection_id_val}) 

@connection_bp.route("/connection/clear-active", methods=["DELETE"])
@require_auth
def clear_active_connection():
    user_id = g.user.get('user_id')
    if not user_id: return jsonify({"error": "Authentication error"}), 401
    result = clear_active_connection_firestore(user_id)
    return jsonify(result)

@connection_bp.route("/connection/fetch-single", methods=["GET"])
@require_auth
def fetch_single_connection():
    user_id = g.user.get('user_id')
    if not user_id: return jsonify({"error": "Authentication error"}), 401
    connection_id = request.args.get("connection_id")
    if not connection_id:
        return jsonify({"error": "Missing connection_id parameter"}), 400
        
    profile = get_connection_profile(user_id, connection_id) 
    if profile:
        return jsonify(profile.to_dict())
    else:
        return jsonify({"error": "Connection profile not found"}), 404

@connection_bp.route("/connection/delete", methods=["DELETE"])
@require_auth
def delete_connection():
    data = request.get_json()
    if not data: return jsonify({"error": "Invalid JSON payload"}), 400

    user_id = g.user.get('user_id') 
    if not user_id: return jsonify({"error": "Authentication error"}), 401
    connection_id = data.get("connection_id")

    if not connection_id: 
        return jsonify({'error': "Missing connection_id"}), 400
        
    result = delete_connection_profile(user_id, connection_id)
    return jsonify(result)