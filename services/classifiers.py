import cv2
import numpy as np
import logging
import re

logger = logging.getLogger(__name__)

# Keywords that might indicate a profile snippet (requires OCR text to be effective)
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
    
    # logger.debug(f"Edge density: {edge_density}")

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

    # logger.debug(f"Text-like contours: {text_like_contours}, Possible text blocks: {possible_text_block_contours}")

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
        # logger.debug(f"Unique colors in sample: {unique_colors}")
        if unique_colors < 200: # Arbitrary threshold for color simplicity
            confidence = min(confidence + 0.2, 1.0)
        else: # More colors, might be a photo with text overlay
            confidence = max(confidence - 0.1, 0.1)


    logger.info(f"Text heuristics: text_heavy={is_text_heavy}, confidence={confidence:.2f}, edges={edge_density:.2f}, small_contours={text_like_contours}, block_contours={possible_text_block_contours}")
    return is_text_heavy, confidence


def classify_image(image_cv2) -> str:
    logger.info("Classifying image using enhanced heuristics...")
    height, width = image_cv2.shape[:2]
    
    if height == 0 or width == 0:
        logger.error("Invalid image dimensions for classification.")
        return "unknown" # Or raise an error

    aspect_ratio = width / float(height)
    image_cv2_gray = cv2.cvtColor(image_cv2, cv2.COLOR_BGR2GRAY)

    # --- Stage 1: Try to identify if it's predominantly a photo or a screenshot ---
    is_screenshot_candidate, text_confidence = has_significant_text_heuristics(image_cv2_gray, image_cv2)

    # If confidence in text presence is very low, lean towards 'photo'
    if not is_screenshot_candidate and text_confidence < 0.3:
        logger.info("Classified as 'photo' (low text confidence).")
        return "photo"
    
    # If confidence is moderate but not high, it could be a photo with some text or a very sparse screenshot
    if not is_screenshot_candidate and text_confidence < 0.5:
         # Further check for photo-like qualities (e.g. more complex textures, less uniform regions)
         # For simplicity, we'll still lean to photo but with less certainty.
         # A more advanced check could involve texture analysis (e.g. Haralick features)
        logger.info("Classified as 'photo' (moderate text confidence but not clearly screenshot).")
        return "photo"

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
        logger.debug(f"Profile keyword score: {profile_keyword_score}")

    conversation_keyword_score = 0
    if ocr_text_available:
        for pattern in COMPILED_CONVERSATION_KEYWORDS:
            if pattern.search(detected_text_for_keywords):
                conversation_keyword_score += 1
        logger.debug(f"Conversation keyword score: {conversation_keyword_score}")

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
        # logger.debug(f"Number of long horizontal lines (potential message bands proxy): {num_potential_message_bands}")


    # Decision Logic for Screenshots:
    # These thresholds and logic are very heuristic and need extensive tuning.
    
    # Tall, narrow images are often conversation screenshots
    if aspect_ratio < 0.75: # Typical for phone screenshots of conversations
        if num_potential_message_bands > 5: # Many distinct lines of text
             logger.info(f"Classified as 'conversation' (tall, many horizontal text bands). AR: {aspect_ratio:.2f}, Bands: {num_potential_message_bands}")
             return "conversation"
        elif ocr_text_available and conversation_keyword_score > profile_keyword_score:
             logger.info("Classified as 'conversation' (tall, keyword-based).")
             return "conversation"
        else:
            # If it's tall but doesn't strongly look like a conversation, it might be a profile snippet or other.
            # Defaulting to profile for tall, texty images if not clearly conversation.
            logger.info(f"Classified as 'profile_snippet' (tall, default from screenshot). AR: {aspect_ratio:.2f}")
            return "profile_snippet"
            
    # Wider images or those with fewer distinct message bands might be profiles
    elif aspect_ratio >= 0.75 :
        if ocr_text_available and profile_keyword_score > 0 and profile_keyword_score > conversation_keyword_score:
            logger.info("Classified as 'profile_snippet' (keyword-based).")
            return "profile_snippet"
        # If fewer message bands and wider, more likely a profile or other less structured text.
        elif num_potential_message_bands < 5 and text_confidence > 0.6:
             logger.info(f"Classified as 'profile_snippet' (wider/fewer bands, texty). AR: {aspect_ratio:.2f}, Bands: {num_potential_message_bands}")
             return "profile_snippet"


    # Fallback / Default based on initial text assessment:
    if is_screenshot_candidate:
        # If it seems like a screenshot but doesn't fit specific rules above,
        # make a general guess. 'profile_snippet' might be a safer default for unrecognized screenshots.
        logger.info("Classified as 'profile_snippet' (default for recognized screenshot).")
        return "profile_snippet"
    else:
        # If it wasn't a strong candidate for screenshot and didn't fit profile/conversation
        logger.info("Classified as 'photo' (default fallback).")
        return "photo"

# Example usage (for testing purposes, if you run this file directly)
if __name__ == '__main__':
    # This part requires you to have OpenCV installed and an image file for testing.
    # Replace 'path_to_your_test_image.jpg' with an actual image path.
    # test_image_path = 'path_to_your_test_image.jpg'
    # try:
    #     img = cv2.imread(test_image_path)
    #     if img is None:
    #         print(f"Error: Could not load image from {test_image_path}")
    #     else:
    #         logging.basicConfig(level=logging.DEBUG) # Show debug logs for testing
    #         category = classify_image(img)
    #         print(f"The image '{test_image_path}' is classified as: {category}")
    # except Exception as e:
    #     print(f"An error occurred: {e}")

    # Create dummy images for testing different scenarios
    logging.basicConfig(level=logging.INFO) # Use INFO for less verbose output

    # Test 1: Tall "conversation-like" image (many horizontal structures)
    convo_img = np.zeros((600, 300, 3), dtype=np.uint8) + 240 # Light gray background
    for i in range(10):
        cv2.putText(convo_img, f"Message line {i+1}", (10, 30 + i * 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1)
        cv2.rectangle(convo_img, (5, 10 + i * 50), (290, 45 + i * 50), (200,200,200),2) # "Message bubbles"
    print(f"Test 'dummy_conversation_image' classified as: {classify_image(convo_img)}")

    # Test 2: Wider "profile-like" image (some text, but less structured like convo)
    profile_img = np.zeros((400, 500, 3), dtype=np.uint8) + 250
    cv2.putText(profile_img, "User Bio:", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
    cv2.putText(profile_img, "Some details about the user here.", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50,50,50), 1)
    cv2.putText(profile_img, "More text, perhaps interests or prompts.", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50,50,50), 1)
    print(f"Test 'dummy_profile_image' classified as: {classify_image(profile_img)}")

    # Test 3: "Photo-like" image (less text-like features, more color variance if it were real)
    # For a dummy, we'll make it simple with few sharp edges.
    photo_img = np.zeros((400, 500, 3), dtype=np.uint8)
    cv2.circle(photo_img, (250, 200), 100, (30, 80, 150), -1) # A "colored object"
    cv2.putText(photo_img, "Vacation 2024", (10,380), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220,220,220),1) # Minimal text
    print(f"Test 'dummy_photo_image' classified as: {classify_image(photo_img)}")