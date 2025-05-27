from typing import List, Dict, Optional, Tuple, Generator
from flask import jsonify
from google.cloud import vision_v1, ImageAnnotatorClient, Image
from infrastructure.clients import vision_client
from infrastructure.logger import get_logger
from utils.ocr_utils import extract_conversation, crop_top_bottom_cv
import cv2
import numpy as np
import io
from contextlib import contextmanager


logger = get_logger(__name__)


class OCRProcessingError(Exception):
    """Custom exception for OCR processing errors"""
    pass


@contextmanager
def convert_image_to_cv2(image_file) -> Generator[np.ndarray, None, None]:
    """
    Context manager to safely convert uploaded image file to CV2 format.
    
    Args:
        image_file: File object from Flask request
        
    Yields:
        numpy.ndarray: CV2 image array
        
    Raises:
        OCRProcessingError: If image conversion fails
    """
    try:
        # Read image bytes
        image_file.seek(0)  # Ensure we're at the beginning
        image_bytes = image_file.read()
        
        if not image_bytes:
            raise OCRProcessingError("Empty image file")
        
        # Convert to numpy array
        np_arr = np.frombuffer(image_bytes, np.uint8)
        image_array = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if image_array is None:
            raise OCRProcessingError("Failed to decode image")
            
        yield image_array
        
    except Exception as e:
        if isinstance(e, OCRProcessingError):
            raise
        raise OCRProcessingError(f"Image conversion failed: {str(e)}")


def validate_image_file(image_file) -> None:
    """
    Validates the uploaded image file.
    
    Args:
        image_file: File object from Flask request
        
    Raises:
        OCRProcessingError: If validation fails
    """
    if not image_file:
        raise OCRProcessingError("No image file provided")
    
    # Check file size (e.g., max 10MB)
    image_file.seek(0, 2)  # Seek to end
    file_size = image_file.tell()
    image_file.seek(0)  # Reset to beginning
    
    max_size = 10 * 1024 * 1024  # 10MB
    if file_size > max_size:
        raise OCRProcessingError(f"Image file too large: {file_size} bytes (max: {max_size} bytes)")
    
    # Check file extension if filename is available
    if hasattr(image_file, 'filename') and image_file.filename:
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}
        ext = image_file.filename.lower().split('.')[-1]
        if f'.{ext}' not in allowed_extensions:
            raise OCRProcessingError(f"Unsupported file type: {ext}")


def prepare_image_for_ocr(image_array: np.ndarray) -> bytes:
    """
    Crops and prepares image for OCR processing.
    
    Args:
        image_array: CV2 image array
        
    Returns:
        bytes: Encoded image content ready for OCR
        
    Raises:
        OCRProcessingError: If image preparation fails
    """
    try:
        # Crop image
        cropped_img = crop_top_bottom_cv(image_array)
        
        if cropped_img is None or cropped_img.size == 0:
            raise OCRProcessingError("Image cropping failed or resulted in empty image")
        
        # Validate cropped image dimensions
        height, width = cropped_img.shape[:2]
        if height < 10 or width < 10:
            raise OCRProcessingError(f"Cropped image too small: {width}x{height}")
        
        # Encode image
        success, encoded_image = cv2.imencode('.png', cropped_img)
        if not success:
            raise OCRProcessingError("Failed to encode cropped image")
        
        return encoded_image.tobytes()
        
    except Exception as e:
        if isinstance(e, OCRProcessingError):
            raise
        raise OCRProcessingError(f"Image preparation failed: {str(e)}")


def perform_ocr(content: bytes, client: ImageAnnotatorClient) -> vision_v1.AnnotateImageResponse:
    """
    Performs OCR on the prepared image content.
    
    Args:
        content: Encoded image bytes
        client: Google Vision API client
        
    Returns:
        AnnotateImageResponse: OCR response from Google Vision API
        
    Raises:
        OCRProcessingError: If OCR fails
    """
    try:
        image = Image(content=content)
        
        # Use annotate_image for better performance and features
        request = {
            'image': image,
            'features': [
                {'type_': vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION},
            ]
        }
        
        response = client.annotate_image(request)
        
        if response.error.message:
            raise OCRProcessingError(f"Google Vision API error: {response.error.message}")
        
        # Validate response has text
        if not response.full_text_annotation or not response.full_text_annotation.pages:
            raise OCRProcessingError("No text detected in image")
        
        return response
        
    except Exception as e:
        if isinstance(e, OCRProcessingError):
            raise
        raise OCRProcessingError(f"OCR processing failed: {str(e)}")


def process_image(user_id: str, image_file) -> List[Dict]:
    """
    Processes an image file containing a messaging conversation and extracts text.
    
    Args:
        user_id: ID of the user making the request
        image_file: File object from Flask request containing screenshot
        
    Returns:
        List[Dict]: Extracted conversation messages
        
    Raises:
        OCRProcessingError: If any step of the processing fails
        
    Example:
        >>> from flask import request
        >>> if 'file' not in request.files:
        >>>     return jsonify({"error": "No file part"}), 400
        >>> file = request.files['file']
        >>> if file.filename == '':
        >>>     return jsonify({"error": "No selected file"}), 400
        >>> try:
        >>>     messages = process_image(user_id, file)
        >>>     return jsonify({"messages": messages}), 200
        >>> except OCRProcessingError as e:
        >>>     return jsonify({"error": str(e)}), 400
    """
    module_name = __package__ or __name__
    
    try:
        # Validate inputs
        if not user_id:
            raise OCRProcessingError("User ID is required")
        
        validate_image_file(image_file)
        
        logger.info(f"Processing image for user: {user_id}")
        
        # Convert image to CV2 format
        with convert_image_to_cv2(image_file) as image_array:
            # Prepare image for OCR
            content = prepare_image_for_ocr(image_array)
        
        # Perform OCR
        client = vision_client
        if not client:
            raise OCRProcessingError("Vision client not initialized")
            
        response = perform_ocr(content, client)
        
        # Extract conversation
        conversation_msgs = extract_conversation(
            user_id, 
            response.full_text_annotation.pages[0]
        )
        
        if not conversation_msgs:
            logger.warning(f"No conversation messages extracted for user: {user_id}")
            return []  # Return empty list instead of raising error
        
        logger.info(f"Successfully extracted {len(conversation_msgs)} messages for user: {user_id}")
        return conversation_msgs
        
    except OCRProcessingError:
        # Re-raise OCRProcessingError as-is
        raise
        
    except Exception as e:
        # Log unexpected errors and wrap them
        logger.error(f"[{module_name}] Unexpected error in process_image: {str(e)}", exc_info=True)
        raise OCRProcessingError(f"Unexpected error during image processing: {str(e)}")


def process_image_batch(user_id: str, image_files: List) -> Dict[str, List[Dict]]:
    """
    Process multiple images in batch.
    
    Args:
        user_id: ID of the user making the request
        image_files: List of file objects from Flask request
        
    Returns:
        Dict mapping filenames to extracted messages
    """
    results = {}
    errors = {}
    
    for image_file in image_files:
        filename = getattr(image_file, 'filename', 'unknown')
        try:
            messages = process_image(user_id, image_file)
            results[filename] = messages
        except OCRProcessingError as e:
            errors[filename] = str(e)
            logger.error(f"Failed to process {filename}: {str(e)}")
    
    if errors:
        logger.warning(f"Batch processing completed with {len(errors)} errors")
    
    return {
        "results": results,
        "errors": errors,
        "total": len(image_files),
        "successful": len(results),
        "failed": len(errors)
    }