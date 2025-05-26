import cv2
import numpy as np
from flask import Blueprint, request, jsonify, g
import logging

# Assuming MAX_IMAGE_SIZE_BYTES is defined in config.py or globally accessible
# from config import MAX_IMAGE_SIZE_BYTES
# For now, let's use the value from the provided file if not imported from elsewhere
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB

from services.classifiers import classify_image
from services.ocr_service import process_image # Expects (user_id, image_bytes)
from infrastructure.auth import require_auth
from infrastructure.logger import get_logger

logger = get_logger(__name__)

ocr_bp = Blueprint('ocr', __name__)

@ocr_bp.route('/scan', methods=['POST'])
@require_auth
def ocr_scan():
    try:
        user_id = getattr(g, 'user_id', None)
        if not user_id:
            logger.error("User ID not found in g after @require_auth.")
            return jsonify({"error": "Authentication error: User ID not available."}), 401

        # Use 'images' for the field name to accept multiple files
        files = request.files.getlist('images') 

        if not files or all(not f.filename for f in files): # Check if list is empty or contains only empty file objects
            logger.error("No image files provided in request for user_id: %s", user_id)
            return jsonify({"error": "Missing 'images' in request or no files selected"}), 400

        batch_results = []

        for file_idx, file in enumerate(files):
            # Ensure file object is not empty (e.g. if user submits form with no file selected for one of the inputs)
            if not file or not file.filename:
                logger.warning("Empty file part detected in batch for user_id: %s at index %d", user_id, file_idx)
                batch_results.append({
                    "status": "error",
                    "original_filename": "N/A", # Or some placeholder
                    "error": "Empty file part in batch."
                })
                continue

            original_filename = file.filename # For logging or richer response

            try:
                file.seek(0, 2)
                size = file.tell()
                if size == 0:
                    logger.error("Empty image file '%s' provided by user_id: %s", original_filename, user_id)
                    batch_results.append({
                        "status": "error",
                        "original_filename": original_filename,
                        "error": "Empty 'image' file provided"
                    })
                    continue
                if size > MAX_IMAGE_SIZE_BYTES:
                    logger.error("Uploaded image '%s' too large: %d bytes for user_id: %s. Limit is %d bytes.",
                                 original_filename, size, user_id, MAX_IMAGE_SIZE_BYTES)
                    batch_results.append({
                        "status": "error",
                        "original_filename": original_filename,
                        "error": f"Image size exceeds limit of {MAX_IMAGE_SIZE_BYTES // (1024*1024)}MB"
                    })
                    continue
                file.seek(0)

                image_bytes = file.read()
                if not image_bytes: # Should be caught by size == 0, but as a safeguard
                    logger.error("Failed to read image bytes for '%s', or image is empty for user_id: %s", original_filename, user_id)
                    batch_results.append({
                        "status": "error",
                        "original_filename": original_filename,
                        "error": "Invalid or empty image data after read"
                    })
                    continue
                    
                nparr = np.frombuffer(image_bytes, np.uint8)
                image_cv2 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if image_cv2 is None:
                    logger.error("Failed to decode image '%s' for user_id: %s. May be corrupt or unsupported format.", original_filename, user_id)
                    batch_results.append({
                        "status": "error",
                        "original_filename": original_filename,
                        "error": "Invalid or corrupt image data"
                    })
                    continue

                category = classify_image(image_cv2)
                logger.info("Image '%s' from user_id: %s classified as '%s'", original_filename, user_id, category)

                if category == 'conversation':
                    data = process_image(user_id=user_id, image_file=image_bytes)
                    if data is not None:
                        batch_results.append({
                            "status": "success",
                            "original_filename": original_filename,
                            "type": "conversation",
                            "data": data
                        })
                    else:
                        logger.error("Conversation image processing failed for '%s', user_id: %s", original_filename, user_id)
                        batch_results.append({
                            "status": "error",
                            "original_filename": original_filename,
                            "type": "conversation",
                            "error": "Failed to process conversation image."
                        })
                elif category == 'profile_snippet':
                    logger.info("User %s uploaded a 'profile_snippet' ('%s') to /ocr/scan. Guiding to correct endpoint.", user_id, original_filename)
                    batch_results.append({
                        "status": "error",
                        "original_filename": original_filename,
                        "type": "profile_snippet",
                        "error": "This image appears to be a profile snippet.",
                        "message": "Please add profile snippets through the connection profile editing feature."
                    })
                elif category == 'photo':
                    logger.info("User %s uploaded a 'photo' ('%s') to /ocr/scan. Guiding to correct endpoint.", user_id, original_filename)
                    batch_results.append({
                        "status": "error",
                        "original_filename": original_filename,
                        "type": "photo",
                        "error": "This image appears to be a photo.",
                        "message": "Please add photos through the connection profile editing feature."
                    })
                else: # Unhandled or unexpected category
                    logger.warning("Image '%s' from user_id: %s classified into an unhandled category: '%s'.",
                                   original_filename, user_id, category)
                    batch_results.append({
                        "status": "error",
                        "original_filename": original_filename,
                        "type": category, # Include the unknown category for debugging/info
                        "error": "Unsupported image type for this feature.",
                        "message": "Please upload a conversation screenshot."
                    })
            except Exception as file_e: # Catch errors specific to processing one file
                logger.exception("Error processing file '%s' in batch for user_id: %s. Error: %s", 
                                 file.filename if file else "N/A", user_id, file_e)
                batch_results.append({
                    "status": "error",
                    "original_filename": file.filename if file and file.filename else "N/A",
                    "error": "An unexpected error occurred while processing this file."
                })
                # Continue to the next file in the batch

        return jsonify(batch_results)

    except Exception as e:
        logger.exception("Unhandled exception in /ocr/scan (batch) for user_id: %s. Error: %s", getattr(g, 'user_id', 'Unknown'), e)
        return jsonify({"error": "An internal server error occurred while processing the batch of images."}), 500