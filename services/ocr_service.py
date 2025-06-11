from typing import List, Dict, Optional, Tuple, Generator, Any
from flask import jsonify
from google.cloud import vision
from google.api_core import retry, exceptions as core_exceptions
from infrastructure.clients import get_vision_client
from infrastructure.logger import get_logger
from utils.ocr_utils import extract_conversation, crop_top_bottom_cv
import cv2
import numpy as np
import io
from contextlib import contextmanager
import time


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


def perform_ocr_with_retry(content: bytes, client: vision.ImageAnnotatorClient, max_retries: int = 3) -> vision.AnnotateImageResponse:
    """
    Performs OCR with retry logic for transient errors.
    
    Args:
        content: Encoded image bytes
        client: Google Vision API client
        max_retries: Maximum number of retry attempts
        
    Returns:
        AnnotateImageResponse: OCR response from Google Vision API
        
    Raises:
        OCRProcessingError: If OCR fails after all retries
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # If this is a retry, wait with exponential backoff
            if attempt > 0:
                wait_time = min(2 ** attempt, 10)  # Max 10 seconds
                logger.info(f"Retrying OCR after {wait_time} seconds (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            
            # Create a fresh client for each retry to avoid stale connections
            if attempt > 0:
                client = get_vision_client()
                if not client:
                    raise OCRProcessingError("Failed to reinitialize Vision client")
            
            image = vision.Image(content=content)
            
            # Use annotate_image for better performance and features
            request = {
                'image': image,
                'features': [
                    {'type_': vision.Feature.Type.DOCUMENT_TEXT_DETECTION},
                ]
            }
            
            # Configure retry policy for the API call itself
            retry_config = retry.Retry(
                initial=0.1,
                maximum=60.0,
                multiplier=2.0,
                predicate=retry.if_exception_type(
                    core_exceptions.ServiceUnavailable,
                    core_exceptions.DeadlineExceeded,
                ),
                deadline=60.0
            )
            
            response = client.annotate_image(request, retry=retry_config)
            
            if response.error.message:
                # API returned an error in the response
                error_msg = f"Google Vision API error: {response.error.message}"
                logger.error(error_msg)
                
                # Don't retry for permanent errors
                if "InvalidArgument" in response.error.message or "InvalidImage" in response.error.message:
                    raise OCRProcessingError(error_msg)
                
                # For other errors, treat as retryable
                last_error = OCRProcessingError(error_msg)
                continue
            
            # Validate response has text
            if not response.full_text_annotation or not response.full_text_annotation.pages:
                logger.warning("No text detected in image")
                # This is not necessarily an error - image might genuinely have no text
                # Return the response anyway and let the caller handle it
                return response
            
            # Success!
            return response
            
        except (core_exceptions.ServiceUnavailable, core_exceptions.DeadlineExceeded) as e:
            # These are transient errors that should be retried
            logger.warning(f"Transient error during OCR (attempt {attempt + 1}): {str(e)}")
            last_error = e
            continue
            
        except core_exceptions.InvalidArgument as e:
            # This is a permanent error, don't retry
            raise OCRProcessingError(f"Invalid request: {str(e)}")
            
        except Exception as e:
            # Unexpected error
            logger.error(f"Unexpected error during OCR: {str(e)}", exc_info=True)
            last_error = e
            
            # If it looks like a connection error, retry
            error_str = str(e).lower()
            if any(term in error_str for term in ['timeout', 'connection', 'goaway', 'unavailable']):
                continue
            
            # Otherwise, don't retry
            raise OCRProcessingError(f"OCR processing failed: {str(e)}")
    
    # All retries exhausted
    raise OCRProcessingError(f"OCR failed after {max_retries} attempts. Last error: {str(last_error)}")


def perform_ocr(content: bytes, client: vision.ImageAnnotatorClient) -> vision.AnnotateImageResponse:
    """
    Performs OCR on the prepared image content.
    This is a wrapper that maintains backward compatibility while adding retry logic.
    
    Args:
        content: Encoded image bytes
        client: Google Vision API client
        
    Returns:
        AnnotateImageResponse: OCR response from Google Vision API
        
    Raises:
        OCRProcessingError: If OCR fails
    """
    return perform_ocr_with_retry(content, client)


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
        client = get_vision_client()
        if not client:
            raise OCRProcessingError("Vision client not initialized")
            
        response = perform_ocr(content, client)
        
        # Check if we have valid pages
        if not response.full_text_annotation or not response.full_text_annotation.pages:
            logger.warning(f"No text/pages found in image for user: {user_id}")
            return []  # Return empty list for images with no text
        
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


def process_image_batch(user_id: str, image_files: List) -> Dict[str, Any]:
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