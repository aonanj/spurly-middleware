import cv2
import numpy as np
from flask import Blueprint, request, jsonify, g
import logging
import base64
from typing import List, Dict, Any

# Configuration
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB

from services.classifiers import classify_image
from services.ocr_service import process_image
from infrastructure.token_validator import verify_token, handle_errors
from infrastructure.logger import get_logger

logger = get_logger(__name__)

ocr_bp = Blueprint('ocr', __name__)


@ocr_bp.route('/scan', methods=['POST'])
@verify_token
@handle_errors
def ocr_scan():
    """
    Endpoint to process multiple images sent as bytes for OCR.
    
    Expected JSON payload:
    {
        "images": [
            {
                "data": "base64_encoded_image_string",
                "filename": "optional_filename.jpg"  # Optional, for logging
            },
            ...
        ]
    }
    
    Returns:
    [
        {
            "status": "success",
            "type": "conversation",
            "conversation_messages": [...],
            "order_num": 0
        },
        {
            "status": "error",
            "type": "unknown",
            "error": "error message",
            "order_num": 1
        },
        ...
    ]
    """
    try:
        user_id = getattr(g, 'user_id', None)
        if not user_id:
            logger.error("User ID not found in g after @verify_token.")
            return jsonify({"error": "Authentication error: User ID not available."}), 401

        # Get JSON data from request
        data = request.get_json()
        if not data or 'images' not in data:
            logger.error("No images data provided in request for user_id: %s", user_id)
            return jsonify({"error": "Missing 'images' in request body"}), 400

        images_data = data.get('images', [])
        if not images_data:
            logger.error("Empty images list provided for user_id: %s", user_id)
            return jsonify({"error": "No images provided"}), 400

        batch_results = []

        for idx, image_info in enumerate(images_data):
            try:
                # Extract base64 data
                if isinstance(image_info, dict):
                    image_b64 = image_info.get('data', '')
                    filename = image_info.get('filename', f'image_{idx}')
                elif isinstance(image_info, str):
                    # If just a string, assume it's base64 data
                    image_b64 = image_info
                    filename = f'image_{idx}'
                else:
                    logger.error("Invalid image data format at index %d for user_id: %s", idx, user_id)
                    batch_results.append({
                        "status": "error",
                        "type": "unknown",
                        "error": "Invalid image data format",
                        "order_num": idx
                    })
                    continue

                # Decode base64 to bytes
                try:
                    # Remove data URL prefix if present
                    if ',' in image_b64 and image_b64.startswith('data:'):
                        image_b64 = image_b64.split(',', 1)[1]
                    
                    image_bytes = base64.b64decode(image_b64)
                except Exception as decode_error:
                    logger.error("Failed to decode base64 image at index %d for user_id: %s. Error: %s", 
                               idx, user_id, decode_error)
                    batch_results.append({
                        "status": "error",
                        "type": "unknown",
                        "error": "Invalid base64 encoding",
                        "order_num": idx
                    })
                    continue

                # Validate image size
                if len(image_bytes) == 0:
                    logger.error("Empty image at index %d for user_id: %s", idx, user_id)
                    batch_results.append({
                        "status": "error",
                        "type": "unknown",
                        "error": "Empty image data",
                        "order_num": idx
                    })
                    continue

                if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
                    size_mb = len(image_bytes) / (1024 * 1024)
                    max_mb = MAX_IMAGE_SIZE_BYTES / (1024 * 1024)
                    logger.error("Image at index %d too large: %.2fMB for user_id: %s. Limit is %.0fMB.",
                               idx, size_mb, user_id, max_mb)
                    batch_results.append({
                        "status": "error",
                        "type": "unknown",
                        "error": f"Image size ({size_mb:.1f}MB) exceeds limit of {max_mb:.0f}MB",
                        "order_num": idx
                    })
                    continue

                # Convert to CV2 format for classification
                nparr = np.frombuffer(image_bytes, np.uint8)
                image_cv2 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if image_cv2 is None:
                    logger.error("Failed to decode image at index %d for user_id: %s", idx, user_id)
                    batch_results.append({
                        "status": "error",
                        "type": "unknown",
                        "error": "Invalid or corrupt image data",
                        "order_num": idx
                    })
                    continue

                # Classify the image
                category = classify_image(image_cv2)
                logger.error("Image at index %d (filename: %s) from user_id: %s classified as '%s'", 
                          idx, filename, user_id, category)

                if category == 'conversation':
                    # Process conversation image
                    try:
                        # Create a file-like object from bytes for process_image
                        from io import BytesIO
                        file_obj = BytesIO(image_bytes)
                        file_obj.name = filename  # Add filename attribute if needed
                        
                        conversation_data = process_image(user_id=user_id, image_file=file_obj)
                        
                        if conversation_data is not None:
                            batch_results.append({
                                "status": "success",
                                "type": "conversation",
                                "conversation_messages": conversation_data,
                                "order_num": idx
                            })
                        else:
                            logger.error("Conversation processing returned None for image at index %d, user_id: %s", 
                                       idx, user_id)
                            batch_results.append({
                                "status": "error",
                                "type": "conversation",
                                "error": "Failed to extract conversation messages",
                                "order_num": idx
                            })
                    except Exception as process_error:
                        logger.error("Error processing conversation image at index %d for user_id: %s. Error: %s", 
                                   idx, user_id, process_error, exc_info=True)
                        batch_results.append({
                            "status": "error",
                            "type": "conversation",
                            "error": "Failed to process conversation image",
                            "order_num": idx
                        })
                else:
                    # Handle all non-conversation images
                    logger.error("LOG.INFO: Image at index %d from user_id: %s is not a conversation (type: %s)", 
                              idx, user_id, category)
                    batch_results.append({
                        "status": "error",
                        "type": category if category else "unknown",
                        "error": "Image is not a conversation screenshot",
                        "order_num": idx
                    })

            except Exception as image_error:
                logger.exception("Unexpected error processing image at index %d for user_id: %s. Error: %s", 
                               idx, user_id, image_error)
                batch_results.append({
                    "status": "error",
                    "type": "unknown",
                    "error": "An unexpected error occurred while processing this image",
                    "order_num": idx
                })
                

        return jsonify(batch_results), 200

    except Exception as e:
        logger.exception("Unhandled exception in /ocr/scan for user_id: %s. Error: %s", 
                        getattr(g, 'user_id', 'Unknown'), e)
        return jsonify({"error": "An internal server error occurred"}), 500


# Alternative endpoint that accepts multipart/form-data (if needed)
@ocr_bp.route('/scan-multipart', methods=['POST'])
@verify_token
@handle_errors
def ocr_scan_multipart():
    """
    Alternative endpoint that accepts images as multipart/form-data.
    This is closer to the original implementation but returns the new format.
    """
    try:
        user_id = getattr(g, 'user_id', None)
        if not user_id:
            logger.error("User ID not found in g after @verify_token.")
            return jsonify({"error": "Authentication error: User ID not available."}), 401

        files = request.files.getlist('images')
        if not files or all(not f.filename for f in files):
            logger.error("No image files provided in request for user_id: %s", user_id)
            return jsonify({"error": "Missing 'images' in request"}), 400

        batch_results = []

        for idx, file in enumerate(files):
            if not file or not file.filename:
                logger.error("Empty file part detected at index %d for user_id: %s", idx, user_id)
                batch_results.append({
                    "status": "error",
                    "type": "unknown",
                    "error": "Empty file",
                    "order_num": idx
                })
                continue

            try:
                # Read file and process
                file.seek(0)
                image_bytes = file.read()
                
                if not image_bytes:
                    batch_results.append({
                        "status": "error",
                        "type": "unknown",
                        "error": "Empty image file",
                        "order_num": idx
                    })
                    continue

                # Size validation
                if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
                    size_mb = len(image_bytes) / (1024 * 1024)
                    max_mb = MAX_IMAGE_SIZE_BYTES / (1024 * 1024)
                    batch_results.append({
                        "status": "error",
                        "type": "unknown",
                        "error": f"Image size ({size_mb:.1f}MB) exceeds limit of {max_mb:.0f}MB",
                        "order_num": idx
                    })
                    continue

                # Convert to CV2 for classification
                nparr = np.frombuffer(image_bytes, np.uint8)
                image_cv2 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if image_cv2 is None:
                    batch_results.append({
                        "status": "error",
                        "type": "unknown",
                        "error": "Invalid or corrupt image data",
                        "order_num": idx
                    })
                    continue

                # Classify and process
                category = classify_image(image_cv2)
                
                if category == 'conversation':
                    # Reset file pointer for process_image
                    file.seek(0)
                    conversation_data = process_image(user_id=user_id, image_file=file)
                    
                    if conversation_data is not None:
                        batch_results.append({
                            "status": "success",
                            "type": "conversation",
                            "conversation_messages": conversation_data,
                            "order_num": idx
                        })
                    else:
                        batch_results.append({
                            "status": "error",
                            "type": "conversation",
                            "error": "Failed to extract conversation messages",
                            "order_num": idx
                        })
                else:
                    batch_results.append({
                        "status": "error",
                        "type": category if category else "unknown",
                        "error": "Image is not a conversation screenshot",
                        "order_num": idx
                    })

            except Exception as file_error:
                logger.exception("Error processing file at index %d for user_id: %s", idx, user_id)
                batch_results.append({
                    "status": "error",
                    "type": "unknown",
                    "error": "An unexpected error occurred",
                    "order_num": idx
                })

        return jsonify(batch_results), 200

    except Exception as e:
        logger.exception("Unhandled exception in /ocr/scan-multipart for user_id: %s", 
                        getattr(g, 'user_id', 'Unknown'))
        return jsonify({"error": "An internal server error occurred"}), 500