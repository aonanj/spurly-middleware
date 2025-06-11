from infrastructure.logger import get_logger
from typing import Any, Union, Dict, List, Tuple, Optional
import numpy as np
import re
from dataclasses import dataclass
from collections import defaultdict
from sklearn.cluster import DBSCAN
import cv2
from PIL import Image
from google.cloud import vision
from infrastructure.clients import get_vision_client
from google.cloud import vision
import io


logger = get_logger(__name__)


@dataclass
class MessageBlock:
    """Represents a text block that might be a message."""
    text: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    center_x: float
    center_y: float
    width: float
    height: float
    confidence: float
    is_message: bool = True
    speaker: Optional[str] = None
    cluster_id: Optional[int] = None


class ConversationExtractor:
    """
    Advanced conversation extraction that uses multiple heuristics to identify
    messages and speakers with higher accuracy.
    """
    
    def __init__(self, confidence_threshold: float = 0.80):
        self.confidence_threshold = confidence_threshold
        self.ui_patterns = self._compile_ui_patterns()
        self.message_patterns = self._compile_message_patterns()
        
    def _compile_ui_patterns(self) -> List[re.Pattern]:
        """Compile patterns for UI elements that should be filtered out."""
        patterns = [
            # Navigation and UI elements
            r"^\s*Chat\s*$",
            r"^\s*Profile\s*$",
            r"^\s*Send a message\s*$",
            r"^\s*Type a message\s*$",
            r"^\s*Write a message\s*$",
            r"^\s*Message\s*$",
            r"^\s*Sent\s*$",
            r"^\s*Delivered\s*$",
            r"^\s*Read\s*$",
            r"^\s*Seen\s*$",
            r"^\s*GIF\s*$",
            r"^\s*Photo\s*$",
            r"^\s*Camera\s*$",
            r"^\s*Gallery\s*$",
            r"^\s*Voice\s*$",
            r"^\s*Video\s*$",
            r"^\s*Call\s*$",
            r"^\s*Search\s*$",
            r"^\s*Back\s*$",
            r"^\s*Menu\s*$",
            r"^\s*Settings\s*$",
            r"^\s*Online\s*$",
            r"^\s*Offline\s*$",
            r"^\s*Active\s*$",
            r"^\s*Typing\s*\.{3}\s*$",
            
            # Timestamps (various formats)
            r"^\s*\d{1,2}:\d{2}\s*(AM|PM)?\s*$",
            r"^\s*Yesterday\s*$",
            r"^\s*Today\s*$",
            r"^\s*Now\s*$",
            r"^\s*Just now\s*$",
            r"^\s*\d+\s*(min|mins|minute|minutes|hr|hrs|hour|hours|day|days)\s*ago\s*$",
            
            # Date patterns - EXPANDED
            r"^\s*(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*$",
            r"^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*,?\s*\d{1,2}:\d{2}\s*(AM|PM)?\s*$",
            r"^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*,?\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\s+\d{1,2}:\d{2}\s*(AM|PM)?\s*$",
            r"^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*,?\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{1,2}:\d{2}\s*(AM|PM)?\s*$",
            # Specific pattern for "Sun, May 25 12:30 PM"
            r"^\s*\w{3}\s*,\s*\w+\s+\d{1,2}\s+\d{1,2}:\d{2}\s*(AM|PM)\s*$",
            r"^\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\s*,?\s*\d{4}\s*$",
            r"^\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s*,?\s*\d{4}\s*$",
            r"^\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*$",
            
            # Empty or whitespace
            r"^\s*$",
            
            # Single characters that are likely UI elements
            r"^\s*[<>+×✓✗→←↑↓]\s*$",
        ]
        
        return [re.compile(p, re.IGNORECASE) for p in patterns]
    
    def _compile_message_patterns(self) -> List[re.Pattern]:
        """Compile patterns that indicate actual message content."""
        patterns = [
            # Questions
            r".*\?$",
            r"^(who|what|when|where|why|how|can|could|would|should|did|do|does|is|are|was|were).*",
            
            # Common message starters
            r"^(hey|hi|hello|goodbye|bye|thanks|thank you|sorry|please|ok|okay|yes|no|yeah|nope|sure).*",
            
            # Emotional expressions
            r"^(haha|lol|lmao|omg|wow|oh|ah|hmm|mhm|ugh).*",
            
            # Personal pronouns indicating conversation
            r"^(i|i'm|i've|i'll|you|you're|you've|we|we're|they|they're).*",
        ]
        
        return [re.compile(p, re.IGNORECASE) for p in patterns]
    
    def _is_ui_element(self, text: str, y_position: float, image_height: float) -> bool:
        """
        Determine if text is likely a UI element rather than a message.
        
        Args:
            text: The text content
            y_position: Y coordinate of the text
            image_height: Total height of the image
            
        Returns:
            True if likely a UI element, False if likely a message
        """
        # Check against UI patterns
        for pattern in self.ui_patterns:
            if pattern.fullmatch(text):
                return True
        
        # Check if it's in header area (top 10%)
        if y_position < image_height * 0.10:
            # More aggressive filtering for header area
            if re.search(r'\d{1,2}:\d{2}', text) or len(text) < 5:
                return True
        
        # Check if it's in footer area (bottom 10%)
        if y_position > image_height * 0.90:
            # Common footer elements
            if re.search(r'(send|message|type|write)', text, re.IGNORECASE):
                return True
        
        return False
    
    def _is_likely_message(self, text: str) -> bool:
        """
        Determine if text is likely a message based on content patterns.
        
        Args:
            text: The text to analyze
            
        Returns:
            True if likely a message
        """
        # Check minimum length
        if len(text) < 2:
            return False
        
        # Check against message patterns
        for pattern in self.message_patterns:
            if pattern.search(text):
                return True
        
        # Check for sentence-like structure
        if re.search(r'[.!?]$', text):
            return True
        
        # If it's reasonably long and not matching UI patterns, likely a message
        # Increased threshold to avoid short UI elements
        if len(text) > 15:
            return True
        
        # Check if it contains common conversational words
        conversational_words = ['bike', 'ride', 'riding', 'love', 'hate', 'want', 'need', 
                            'think', 'feel', 'know', 'see', 'tell', 'ask', 'say']
        text_lower = text.lower()
        if any(word in text_lower for word in conversational_words):
            return True
        
        return False
    
    def _cluster_messages(self, messages: List[MessageBlock], image_width: float) -> None:
        """
        Use DBSCAN clustering to group messages by their x-position.
        This helps identify conversation sides even when they're not perfectly aligned.
        
        Args:
            messages: List of message blocks
            image_width: Width of the image
        """
        if len(messages) < 2:
            return
        
        # Prepare features for clustering
        # Use both x_min and x_max to better distinguish left/right alignment
        features = []
        for msg in messages:
            # Normalize positions by image width
            left_edge = msg.x_min / image_width
            right_edge = msg.x_max / image_width
            # Use distance from edges as features
            dist_from_left = left_edge
            dist_from_right = 1.0 - right_edge
            features.append([dist_from_left, dist_from_right])
        
        features = np.array(features)
        
        # Use DBSCAN with appropriate epsilon
        # Smaller epsilon for better separation
        clustering = DBSCAN(eps=0.1, min_samples=1).fit(features)
        
        # Assign cluster IDs
        for i, msg in enumerate(messages):
            msg.cluster_id = clustering.labels_[i]
    
    def _analyze_message_alignment(self, messages: List[MessageBlock]) -> Dict[int, Dict[str, Any]]:
        """
        Analyze the alignment characteristics of each cluster.
        
        Args:
            messages: List of message blocks with cluster assignments
            
        Returns:
            Dictionary mapping cluster_id to alignment statistics
        """
        cluster_stats: Dict[int, Dict[str, Any]] = defaultdict(lambda: {
            'x_positions': [],
            'widths': [],
            'messages': []
        })
        
        for msg in messages:
            if msg.cluster_id is not None:
                cluster_stats[msg.cluster_id]['x_positions'].append(msg.center_x)
                cluster_stats[msg.cluster_id]['widths'].append(msg.width)
                cluster_stats[msg.cluster_id]['messages'].append(msg)
        
        # Calculate statistics for each cluster
        for cluster_id, stats in cluster_stats.items():
            stats['mean_x'] = float(np.mean(stats['x_positions']))
            stats['std_x'] = float(np.std(stats['x_positions']))
            stats['mean_width'] = float(np.mean(stats['widths']))
            stats['count'] = len(stats['messages'])
        
        return dict(cluster_stats)
    
    def _assign_speakers_by_clustering(self, messages: List[MessageBlock], image_width: float) -> None:
        """
        Assign speakers based on clustering results and alignment analysis.
        
        Args:
            messages: List of message blocks
            image_width: Width of the image
        """
        # Cluster messages
        self._cluster_messages(messages, image_width)
        
        # Analyze clusters
        cluster_stats = self._analyze_message_alignment(messages)
        
        if len(cluster_stats) == 0:
            return
        
        # For each cluster, determine if it's left or right aligned
        for cluster_id, stats in cluster_stats.items():
            # Calculate average position relative to edges
            avg_x_min = float(np.mean([msg.x_min for msg in stats['messages']]))
            avg_x_max = float(np.mean([msg.x_max for msg in stats['messages']]))
            
            # Normalize by image width
            left_distance = avg_x_min / image_width
            right_distance = (image_width - avg_x_max) / image_width
            
            # Determine alignment based on which edge the messages are closer to
            if left_distance < right_distance:
                # Messages are closer to left edge = connection
                for msg in stats['messages']:
                    msg.speaker = "connection"
            else:
                # Messages are closer to right edge = user
                for msg in stats['messages']:
                    msg.speaker = "user"
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Fix punctuation spacing
        text = re.sub(r'\s+([.,?!;:])', r'\1', text)
        text = re.sub(r'(")\s+', r'\1', text)
        text = re.sub(r'\s+(")', r'\1', text)
        text = re.sub(r'\s+(\'\w+)', r'\1', text)
        text = re.sub(r'([.?!])(\w)', r'\1 \2', text)
        
        return text
    
    def extract_conversation(self, user_id: str, page: Any) -> List[Dict[str, Any]]:
        """
        Extract conversation messages from OCR page data.
        
        Args:
            user_id: User identifier
            page: Google Vision API page object
            
        Returns:
            List of message dictionaries with sender and text
        """
        try:
            image_width = page.width
            image_height = page.height
            
            # Extract all text blocks
            message_blocks = []
            
            for block in page.blocks:
                # Validate block
                if not self._is_valid_block(block):
                    continue
                
                # Extract block information
                block_info = self._extract_block_info(block, image_width, image_height)
                if not block_info:
                    continue
                
                # Create MessageBlock
                msg_block = MessageBlock(**block_info)
                
                # Filter UI elements (including dates)
                if self._is_ui_element(msg_block.text, msg_block.center_y, image_height):
                    msg_block.is_message = False
                    continue  # Skip adding this block
                
                # Check if it's likely a message
                if not self._is_likely_message(msg_block.text):
                    msg_block.is_message = False
                    continue  # Skip adding this block
                
                # Only add blocks that passed both filters
                message_blocks.append(msg_block)
            
            # All blocks in message_blocks are now messages
            messages = message_blocks
            
            # Assign speakers using clustering
            if messages:
                self._assign_speakers_by_clustering(messages, image_width)
            
            # Sort by vertical position
            messages.sort(key=lambda m: m.center_y)
            
            # Convert to output format with "sender" key
            result = []
            for msg in messages:
                if msg.speaker:
                    result.append({
                        "sender": msg.speaker,
                        "text": self._clean_text(msg.text)
                    })
                else:
                    # If no speaker assigned, mark as unknown
                    result.append({
                        "sender": "unknown",
                        "text": self._clean_text(msg.text)
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"Error in extract_conversation: {str(e)}", exc_info=True)
            raise
        
    def _is_valid_block(self, block: Any) -> bool:
        """Check if a block has valid structure and confidence."""
        if not block.bounding_box or not block.bounding_box.vertices:
            return False
        if len(block.bounding_box.vertices) != 4:
            return False
        if block.confidence < self.confidence_threshold:
            return False
        return True
    
    def _extract_block_info(self, block: Any, image_width: float, image_height: float) -> Optional[Dict]:
        """Extract relevant information from a block."""
        try:
            vertices = block.bounding_box.vertices
            x_coords = [v.x for v in vertices]
            y_coords = [v.y for v in vertices]
            
            # Get text
            text = get_text_from_element(block)
            if not text:
                return None
            
            return {
                'text': text,
                'x_min': min(x_coords),
                'x_max': max(x_coords),
                'y_min': min(y_coords),
                'y_max': max(y_coords),
                'center_x': (min(x_coords) + max(x_coords)) / 2,
                'center_y': (min(y_coords) + max(y_coords)) / 2,
                'width': max(x_coords) - min(x_coords),
                'height': max(y_coords) - min(y_coords),
                'confidence': block.confidence
            }
        except Exception as e:
            logger.error(f"Error extracting block info: {str(e)}")
            return None


# Backward compatibility function
def extract_conversation(user_id: str, page: Any, confidence_threshold: float = 0.80) -> List[Dict]:
    """
    Backward compatible wrapper for the new ConversationExtractor.
    
    Args:
        user_id: User identifier
        page: Google Vision API page object
        confidence_threshold: Minimum confidence threshold
        
    Returns:
        List of message dictionaries
    """
    extractor = ConversationExtractor(confidence_threshold)
    return extractor.extract_conversation(user_id, page)


# Keep existing utility functions
def get_text_from_element(element) -> str:
    """Extracts text from a Vision API element (Block, Paragraph, or Word)."""
    try:
        block_text = ""
        for paragraph in getattr(element, 'paragraphs', []):
            para_text = ""
            for word in getattr(paragraph, 'words', []):
                word_text = "".join([symbol.text for symbol in getattr(word, 'symbols', [])])
                para_text += word_text + " "
            block_text += para_text.strip()
        if not block_text.strip() and hasattr(element, 'text'):
            block_text = element.text
        return block_text.strip()
    except Exception as e:
        logger.error(f"Error in get_text_from_element: {str(e)}")
        raise


def crop_top_bottom_cv(img: np.ndarray) -> Union[np.ndarray, None]:
    """
    Crops the top and bottom rows off an image.
    
    Args:
        img: A NumPy array containing the image content
        
    Returns:
        Cropped image or None if crop is invalid
    """
    if img is None:
        raise ValueError("Unable to open image.")
        
    height, width = img.shape[:2]
    
    if height == 0 or width == 0:
        logger.error("Invalid image dimensions")
        return None
    
    # Define the crop percentages
    top_crop_percent = 0.10  # 10% from top
    bottom_crop_percent = 0.15  # 15% from bottom
    
    # Calculate pixels to remove
    top_crop_pixels = int(height * top_crop_percent)
    bottom_crop_pixels = int(height * bottom_crop_percent)
    
    # Determine crop boundaries
    start_row = top_crop_pixels
    end_row = height - bottom_crop_pixels
    
    if start_row >= end_row:
        logger.error("Invalid crop boundaries")
        return None
    
    # Perform cropping
    cropped_image = img[start_row:end_row, :]
    
    return cropped_image


# Alternative approach using visual features
class VisualConversationExtractor:
    """
    Alternative approach using visual features like message bubbles and colors.
    This can be more accurate for apps with distinct visual styling.
    """
    
    def __init__(self, confidence_threshold: float = 0.80):
        self.confidence_threshold = confidence_threshold
        self.extractor = ConversationExtractor(confidence_threshold)
    
    def extract_with_visual_analysis(self, user_id: str, page: Any, image_array: np.ndarray) -> List[Dict]:
        """
        Extract conversation using both OCR and visual analysis.
        
        Args:
            user_id: User identifier
            page: Google Vision API page object
            image_array: Original image as numpy array
            
        Returns:
            List of message dictionaries
        """
        # First, get text-based extraction
        messages = self.extractor.extract_conversation(user_id, page)
        
        # Then, refine with visual analysis
        if len(messages) > 0 and image_array is not None:
            self._refine_with_visual_features(messages, page, image_array)
        
        return messages
    
    def _refine_with_visual_features(self, messages: List[Dict], page: Any, image: np.ndarray) -> None:
        """
        Refine speaker assignment using visual features like bubble detection.
        
        Args:
            messages: List of messages from text extraction
            page: OCR page data
            image: Original image
        """
        try:
            # Convert to grayscale for edge detection
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Detect edges to find message bubbles
            edges = cv2.Canny(gray, 50, 150)
            
            # Find contours (potential message bubbles)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Analyze color distribution on left vs right
            height, width = image.shape[:2]
            left_half = image[:, :width//2]
            right_half = image[:, width//2:]
            
            # Calculate dominant colors
            left_colors = self._get_dominant_colors(left_half)
            right_colors = self._get_dominant_colors(right_half)
            
            # If there's a significant color difference, use it to refine speaker assignment
            if self._colors_are_different(left_colors, right_colors):
                logger.info("Detected distinct color patterns for speakers")
                # This information can be used to validate or correct speaker assignments
                
        except Exception as e:
            logger.warning(f"Visual analysis failed, using text-only extraction: {str(e)}")
    
    def _get_dominant_colors(self, image_region: np.ndarray, k: int = 3) -> np.ndarray:
        """Get dominant colors in an image region using k-means."""
        try:
            # Reshape image to be a list of pixels
            pixels = image_region.reshape(-1, 3)
            
            # Simple k-means using numpy (to avoid sklearn dependency if not needed)
            # For production, use sklearn.cluster.KMeans
            unique_colors, counts = np.unique(pixels, return_counts=True, axis=0)
            
            # Get top k colors by frequency
            top_indices = np.argsort(counts)[-k:]
            dominant_colors = unique_colors[top_indices]
            
            return dominant_colors
        except Exception as e:
            logger.error(f"Error getting dominant colors: {str(e)}")
            return np.array([])
    
    def _colors_are_different(self, colors1: np.ndarray, colors2: np.ndarray, threshold: float = 50) -> bool:
        """Check if two sets of colors are significantly different."""
        if len(colors1) == 0 or len(colors2) == 0:
            return False
        
        # Calculate average color for each set
        avg1 = np.mean(colors1, axis=0)
        avg2 = np.mean(colors2, axis=0)
        
        # Calculate Euclidean distance
        distance = np.linalg.norm(avg1 - avg2)
        
        return bool(distance > threshold)

def perform_ocr_on_screenshot(screenshot_bytes: bytes) -> List[str]:
    """
    Performs OCR on a screenshot with preprocessing to crop top/bottom regions based on specific text.
    
    Args:
        screenshot_bytes: Image bytes of the screenshot on which to perform OCR
    
    Returns:
        List of strings, each representing text from an individual bounding box
    """
    # Validate input
    if not screenshot_bytes:
        raise ValueError("Screenshot bytes cannot be empty")
    
    # Use the vision client from infrastructure.clients
    try:
        vision_client = get_vision_client()
    except RuntimeError as e:
        logger.error(f"Vision client initialization failed: {str(e)}")
        raise RuntimeError("Vision client has not been initialized. Ensure init_clients() is called.")
    if vision_client is None:
        raise RuntimeError("Vision client has not been initialized. Ensure init_clients() is called.")
    
    content = screenshot_bytes
    
    # Convert to PIL Image for preprocessing
    image = Image.open(io.BytesIO(content))
    width, height = image.size
    
    # First, perform initial OCR to check for text in top/bottom regions
    vision_image = vision.Image(content=content)
    request = vision.AnnotateImageRequest(
        image=vision_image,
        features=[vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION)]
    )
    response = vision_client.annotate_image(request=request)

    if response.error.message:
        raise Exception(f'Error during OCR: {response.error.message}')
    
    # Check if we need to crop
    crop_top = should_crop_top(response.text_annotations, height)
    crop_bottom = should_crop_bottom(response.text_annotations, height)
    
    # Crop the image if needed
    if crop_top or crop_bottom:
        image = crop_screenshot(image, crop_top, crop_bottom)
        
        # Convert cropped image back to bytes for OCR
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        content = img_byte_arr.getvalue()
        
        # Perform OCR on cropped image
        vision_image = vision.Image(content=content)
        request = vision.AnnotateImageRequest(
            image=vision_image,
            features=[vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION)]
        )
        response = vision_client.annotate_image(request=request)
        
        if response.error.message:
            raise Exception(f'Error during OCR on cropped image: {response.error.message}')
    
    # Extract text from individual bounding boxes
    text_blocks = extract_text_blocks(response.text_annotations)
    
    return text_blocks


def should_crop_top(annotations: List, image_height: int) -> bool:
    """
    Checks if the top 15% of the image contains date, time, percentage, or MNO operator names.
    
    Args:
        annotations: List of text annotations from Google Vision API
        image_height: Height of the image in pixels
    
    Returns:
        True if top should be cropped, False otherwise
    """
    if not annotations:
        return False
    
    top_boundary = image_height * 0.15
    
    # MNO operators to check for
    mno_operators = ['at&t', 't-mobile', 'verizon', 'sprint', 'boost', 'cricket', 
                     'metro', 'mint', 'visible', 'google fi', 'us cellular']
    
    for annotation in annotations[1:]:  # Skip first annotation (full text)
        # Get the y-coordinate of the annotation's bounding box
        vertices = annotation.bounding_poly.vertices
        if not vertices:
            continue
            
        # Check if annotation is in top 15%
        max_y = max(vertex.y for vertex in vertices)
        if max_y <= top_boundary:
            text_lower = annotation.description.lower()
            
            # Check for MNO operators
            if any(operator in text_lower for operator in mno_operators):
                return True
            
            # Check for time patterns (e.g., 10:30, 2:45 PM)
            if ':' in text_lower and any(char.isdigit() for char in text_lower):
                return True
            
            # Check for percentage
            if '%' in text_lower:
                return True
            
            # Check for date patterns (basic check for common date indicators)
            date_indicators = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 
                             'aug', 'sep', 'oct', 'nov', 'dec', 'monday', 'tuesday',
                             'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
                             '/', '-']
            if any(indicator in text_lower for indicator in date_indicators):
                # Additional check for numeric patterns
                if any(char.isdigit() for char in text_lower):
                    return True
    
    return False


def should_crop_bottom(annotations: List, image_height: int) -> bool:
    """
    Checks if the bottom 10% of the image contains specific keywords.
    
    Args:
        annotations: List of text annotations from Google Vision API
        image_height: Height of the image in pixels
    
    Returns:
        True if bottom should be cropped, False otherwise
    """
    if not annotations:
        return False
    
    bottom_boundary = image_height * 0.9
    target_words = ['message', 'gif', 'send', 'say', 'text']
    
    for annotation in annotations[1:]:  # Skip first annotation (full text)
        vertices = annotation.bounding_poly.vertices
        if not vertices:
            continue
            
        # Check if annotation is in bottom 10%
        min_y = min(vertex.y for vertex in vertices)
        if min_y >= bottom_boundary:
            text_lower = annotation.description.lower()
            if any(word in text_lower for word in target_words):
                return True
    
    return False


def crop_screenshot(image: Image.Image, crop_top: bool, crop_bottom: bool) -> Image.Image:
    """
    Crops the screenshot based on the flags.
    
    Args:
        image: PIL Image object
        crop_top: Whether to crop top 15%
        crop_bottom: Whether to crop bottom 10%
    
    Returns:
        Cropped PIL Image
    """
    width, height = image.size
    
    # Calculate crop boundaries
    top = int(height * 0.15) if crop_top else 0
    bottom = int(height * 0.9) if crop_bottom else height
    
    # Crop the image
    cropped = image.crop((0, top, width, bottom))
    
    return cropped


def extract_text_blocks(annotations: List) -> List[str]:
    """
    Extracts text from individual bounding boxes.
    
    Args:
        annotations: List of text annotations from Google Vision API
    
    Returns:
        List of strings, each representing text from a bounding box
    """
    if not annotations:
        return []
    
    # Skip the first annotation as it contains all text combined
    text_blocks = []
    for annotation in annotations[1:]:
        text = annotation.description.strip()
        if text:
            text_blocks.append(text)
    
    return text_blocks


# Example usage:
if __name__ == "__main__":
    # Note: Ensure that init_clients() has been called before using this function
    # This would typically be done during Flask app initialization
    
    # Load screenshot bytes
    with open("path/to/your/screenshot.png", "rb") as f:
        screenshot_data = f.read()
    
    try:
        text_blocks = perform_ocr_on_screenshot(screenshot_data)
        
        print("Detected text blocks:")
        for i, text in enumerate(text_blocks, 1):
            print(f"{i}. {text}")
            
    except Exception as e:
        print(f"Error: {e}")