import cv2
import numpy as np
import logging
import re

logger = logging.getLogger(__name__)

# Keywords that might indicate a profile content (requires OCR text to be effective)
PROFILE_KEYWORDS = [
    r"bio", r"about me", r"interests", r"prompt", r"profile",
    r"looking for", r"my self-summary", r"occupation", r"education"
]
COMPILED_PROFILE_KEYWORDS = [re.compile(p, re.IGNORECASE) for p in PROFILE_KEYWORDS]

# Keywords or patterns that might indicate a conversation (requires OCR text to be effective)
CONVERSATION_KEYWORDS = [
    r"message", r"send", r"chat", r"reply", r"delivered", r"sent",
    r"type a message", r"online", r"typing",
    r"\d{1,2}:\d{2}\s*(?:AM|PM)" # Timestamps like 10:30 AM
]
COMPILED_CONVERSATION_KEYWORDS = [re.compile(p, re.IGNORECASE) for p in CONVERSATION_KEYWORDS]


def has_significant_text_heuristics(image_cv2_gray, image_cv2_color) -> tuple[bool, float]:
    """
    Uses heuristics to guess if an image has significant text.
    Returns a boolean and a confidence score (0.0 - 1.0).
    This is a basic heuristic and not a replacement for OCR.
    """
    height, width = image_cv2_gray.shape
    area = height * width

    # 1. Edge density (text often has many sharp edges)
    edges = cv2.Canny(image_cv2_gray, 50, 150, apertureSize=3)
    edge_pixels = np.sum(edges > 0)
    edge_density = edge_pixels / area
    
    # logger.error(f"Edge density: {edge_density}")

    # 2. Contour analysis (looking for small, regular shapes like characters)
    #    and larger rectangular blocks (like text paragraphs or UI elements)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    
    text_like_contours = 0
    min_char_area = (height * 0.01) * (width * 0.005) # Heuristic: min area for a char
    max_char_area = (height * 0.1) * (width * 0.1)    # Heuristic: max area for a char
    
    possible_text_block_contours = 0
    min_block_area = (width * 0.2) * (height * 0.05) # Heuristic: min area for a text block

    for contour in contours:
        (x, y, w, h) = cv2.boundingRect(contour)
        aspect_ratio = w / float(h) if h > 0 else 0
        contour_area = cv2.contourArea(contour)

        # Character-like contours
        if min_char_area < contour_area < max_char_area and 0.1 < aspect_ratio < 2.0:
            text_like_contours += 1
        
        # Text block-like contours (larger rectangular areas)
        if contour_area > min_block_area and 0.5 < aspect_ratio < 20: # Blocks can be wide or tall
             # Further check if the block is mostly uniform or has fine textures inside (more advanced)
            possible_text_block_contours +=1

    # logger.error(f"Text-like contours: {text_like_contours}, Possible text blocks: {possible_text_block_contours}")

    # Heuristic decision points
    # These thresholds are highly empirical and need tuning for your specific dataset
    is_text_heavy = False
    confidence = 0.0

    if edge_density > 0.15 and text_like_contours > 50 : # High edge density and many small contours
        is_text_heavy = True
        confidence = max(confidence, 0.6)
    elif possible_text_block_contours > 3 and text_like_contours > 100: # Fewer large blocks but many char-like contours
        is_text_heavy = True
        confidence = max(confidence, 0.7)
    elif text_like_contours > 200: # A lot of small contours, likely text
        is_text_heavy = True
        confidence = max(confidence, 0.5)
    
    if is_text_heavy:
        # Additional check: color simplicity (screenshots often have fewer distinct colors)
        # This is a simplified check. A more robust way involves color quantization.
        resized_for_color = cv2.resize(image_cv2_color, (50, 50))
        unique_colors = len(np.unique(resized_for_color.reshape(-1, 3), axis=0))
        # logger.error(f"Unique colors in sample: {unique_colors}")
        if unique_colors < 200: # Arbitrary threshold for color simplicity
            confidence = min(confidence + 0.2, 1.0)
        else: # More colors, might be a photo with text overlay
            confidence = max(confidence - 0.1, 0.1)


    logger.error(f"LOG.INFO: Text heuristics: text_heavy={is_text_heavy}, confidence={confidence:.2f}, edges={edge_density:.2f}, small_contours={text_like_contours}, block_contours={possible_text_block_contours}")
    return is_text_heavy, confidence


def classify_image(image_cv2) -> str:
    """
    Classify an image based on its visual characteristics.
    
    Args:
        image_cv2: OpenCV image array (numpy.ndarray) - already decoded image
        
    Returns:
        str: Classification result ('conversation', 'profile_content', 'connection_pic', or '')
    """
    # Input validation
    if image_cv2 is None:
        logger.error("Received None image for classification.")
        return ""
    
    if not isinstance(image_cv2, np.ndarray):
        logger.error(f"Expected numpy array, got {type(image_cv2)}")
        return ""
    
    logger.error("LOG.INFO: Classifying image using enhanced heuristics...")
    height, width = image_cv2.shape[:2]
    
    if height == 0 or width == 0:
        logger.error("Invalid image dimensions for classification.")
        return ""

    aspect_ratio = width / float(height)
    image_cv2_gray = cv2.cvtColor(image_cv2, cv2.COLOR_BGR2GRAY)

    # --- Stage 1: Try to identify if it's predominantly a photo or a screenshot ---
    is_screenshot_candidate, text_confidence = has_significant_text_heuristics(image_cv2_gray, image_cv2)

    # If confidence in text presence is very low, lean towards 'photo'
    if not is_screenshot_candidate and text_confidence < 0.3:
        logger.error("LOG.INFO: Classified as 'photo' (low text confidence).")
        return "connection_pic"
    
    # If confidence is moderate but not high, it could be a photo with some text or a very sparse screenshot
    if not is_screenshot_candidate and text_confidence < 0.5:
         # Further check for photo-like qualities (e.g. more complex textures, less uniform regions)
         # For simplicity, we'll still lean to photo but with less certainty.
         # A more advanced check could involve texture analysis (e.g. Haralick features)
        logger.error("LOG.INFO: Classified as 'connection_pic' (moderate text confidence but not clearly screenshot).")
        return "connection_pic"

    # --- Stage 2: If it's likely a screenshot, differentiate conversation vs. profile ---
    # This stage assumes `is_screenshot_candidate` is True or text_confidence is high enough.
    # NOTE: The following keyword checks are placeholders.
    # Effective keyword spotting requires actual OCR text from the image.
    # Without OCR, we rely more on structural heuristics.
    
    ocr_text_available = False # This would be True if you had OCR text
    detected_text_for_keywords = "" # Populate this if OCR is performed

    profile_keyword_score = 0
    if ocr_text_available:
        for pattern in COMPILED_PROFILE_KEYWORDS:
            if pattern.search(detected_text_for_keywords):
                profile_keyword_score += 1
        logger.error(f"Profile keyword score: {profile_keyword_score}")

    conversation_keyword_score = 0
    if ocr_text_available:
        for pattern in COMPILED_CONVERSATION_KEYWORDS:
            if pattern.search(detected_text_for_keywords):
                conversation_keyword_score += 1
        logger.error(f"Conversation keyword score: {conversation_keyword_score}")

    # Structural Heuristics for Conversation Screenshots:
    # Look for multiple, distinct horizontal bands of text, potentially aligned.
    # This is a simplified approach.
    num_potential_message_bands = 0
    # Detect horizontal lines, which could be rows of text or dividers
    edges = cv2.Canny(image_cv2_gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=int(width * 0.3), maxLineGap=20)
    if lines is not None:
        # Filter and group lines to identify distinct bands. This is non-trivial.
        # For a simpler proxy: count reasonably long horizontal lines.
        num_potential_message_bands = len(lines)
        # logger.error(f"Number of long horizontal lines (potential message bands proxy): {num_potential_message_bands}")


    # Decision Logic for Screenshots:
    # These thresholds and logic are very heuristic and need extensive tuning.
    
    # Tall, narrow images are often conversation screenshots
    if aspect_ratio < 0.75: # Typical for phone screenshots of conversations
        if num_potential_message_bands > 5: # Many distinct lines of text
             logger.error(f"LOG.INFO: Classified as 'conversation' (tall, many horizontal text bands). AR: {aspect_ratio:.2f}, Bands: {num_potential_message_bands}")
             return "conversation"
        elif ocr_text_available and conversation_keyword_score > profile_keyword_score:
             logger.error("LOG.INFO: Classified as 'conversation' (tall, keyword-based).")
             return "conversation"
        else:
            # If it's tall but doesn't strongly look like a conversation, it might be a profile content or other.
            # Defaulting to profile for tall, texty images if not clearly conversation.
            logger.error(f"LOG.INFO: Classified as 'profile_content' (tall, default from screenshot). AR: {aspect_ratio:.2f}")
            return "profile_content"
            
    # Wider images or those with fewer distinct message bands might be profiles
    elif aspect_ratio >= 0.75 :
        if ocr_text_available and profile_keyword_score > 0 and profile_keyword_score > conversation_keyword_score:
            logger.error("LOG.INFO: Classified as 'profile_content' (keyword-based).")
            return "profile_content"
        # If fewer message bands and wider, more likely a profile or other less structured text.
        elif num_potential_message_bands < 5 and text_confidence > 0.6:
             logger.error(f"LOG.INFO: Classified as 'profile_content' (wider/fewer bands, texty). AR: {aspect_ratio:.2f}, Bands: {num_potential_message_bands}")
             return "profile_content"


    # Fallback / Default based on initial text assessment:
    if is_screenshot_candidate:
        # If it seems like a screenshot but doesn't fit specific rules above,
        # make a general guess. 'profile_content' might be a safer default for unrecognized screenshots.
        logger.error("LOG.INFO: Classified as 'profile_content' (default for recognized screenshot).")
        return "profile_content"
    else:
        # If it wasn't a strong candidate for screenshot and didn't fit profile/conversation
        logger.error("LOG.INFO: Classified as 'photo' (default fallback).")
        return "connection_pic"