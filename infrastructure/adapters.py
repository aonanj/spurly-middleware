import base64
from typing import List
from flask import request

from .logger import get_logger

logger = get_logger(__name__)


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
    
    return image_bytes_list