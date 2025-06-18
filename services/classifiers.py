import base64
import json
from typing import Dict, Literal
import requests
from PIL import Image
import io

def classify_image(image_data: Dict) -> Literal["photo", "profile", "conversation"]:
    """
    Classify an image as 'photo', 'profile', or 'conversation'.
    
    Args:
        image_data: Dict with keys:
            - 'data': raw bytes of the image
            - 'filename': name of the file
            - 'mime_type': MIME type of the image
    
    Returns:
        One of: "photo", "profile", or "conversation"
    """
    
    # Convert image bytes to base64 for API
    image_bytes = image_data['data']
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    # Prepare the prompt for classification
    classification_prompt = """Analyze this image and classify it into exactly one of these three categories:

1. "photo" - The image shows one or more people (portraits, group photos, selfies, etc.)
2. "profile" - The image is a screenshot of a social media or dating app profile section with text content about a person
3. "conversation" - The image is a screenshot of a text message or direct message conversation between people

Look for these key indicators:
- For "photo": Human faces, bodies, people in any setting
- For "profile": Profile layout with bio text, stats, interests, profile picture alongside text descriptions
- For "conversation": Message bubbles, chat interface, back-and-forth text exchanges

Respond with only one word: either "photo", "profile", or "conversation"."""

    # Example using OpenAI API (replace with your preferred vision model)
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer YOUR_API_KEY"  # Replace with actual API key
    }
    
    payload = {
        "model": "gpt-4o-mini",  # or "gpt-4-vision-preview"
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": classification_prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_data['mime_type']};base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 10,
        "temperature": 0
    }
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()
        classification = result['choices'][0]['message']['content'].strip().lower()
        
        # Validate the response
        if classification in ["photo", "profile", "conversation"]:
            return classification
        else:
            # Fallback logic if response is unexpected
            return "photo"  # Default fallback
            
    except Exception as e:
        print(f"Error during classification: {e}")
        # Implement fallback logic or raise exception
        return "photo"  # Default fallback


# Alternative implementation using open-source models (Transformers)
def classify_image_opensource(image_data: Dict) -> Literal["photo", "profile", "conversation"]:
    """
    Alternative implementation using Hugging Face transformers.
    """
    from transformers.pipelines import pipeline
    
    # Initialize the visual question answering pipeline
    vqa = pipeline("visual-question-answering", model="dandelin/vilt-b32-finetuned-vqa")
    
    # Convert bytes to PIL Image
    image = Image.open(io.BytesIO(image_data['data']))
    
    # Ask specific questions to classify
    questions = [
        "Does this image show people or persons?",
        "Is this a screenshot of a social media profile?",
        "Is this a screenshot of a text message conversation?"
    ]
    
    scores = {"photo": 0, "profile": 0, "conversation": 0}
    
    for question in questions:
        try:
            # Fixed: VQA pipeline expects dictionary with 'image' and 'question' keys
            result = vqa({"image": image, "question": question})
            answer = list(result)[0]['answer'].lower()
            
            if "people" in question and answer in ['yes', 'true']:
                scores["photo"] += 1
            elif "profile" in question and answer in ['yes', 'true']:
                scores["profile"] += 1
            elif "conversation" in question and answer in ['yes', 'true']:
                scores["conversation"] += 1
        except:
            continue
    
    # Return the category with highest score
    return max(scores, key=scores.get)  # type: ignore


# Lightweight rule-based approach using OCR
def classify_image_lightweight(image_data: Dict) -> Literal["photo", "profile", "conversation"]:
    """
    Lightweight implementation using OCR and pattern matching.
    """
    import pytesseract
    import numpy as np
    import cv2
    
    # Convert bytes to image
    nparr = np.frombuffer(image_data['data'], np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Perform OCR
    try:
        text = pytesseract.image_to_string(img).lower()
    except:
        text = ""
    
    # Pattern matching for classification
    conversation_keywords = ['sent', 'delivered', 'read', 'typing', 'message', 'reply', 'am', 'pm']
    profile_keywords = ['bio', 'about', 'interests', 'looking for', 'age', 'location', 'height', 'occupation']
    
    conversation_score = sum(1 for keyword in conversation_keywords if keyword in text)
    profile_score = sum(1 for keyword in profile_keywords if keyword in text)
    
    # Check for face detection for photos
    # Fixed: Use the full path or install opencv-python-headless
    try:
        # Option 1: Use haarcascade file directly (you need to download it)
        face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
        
        # Option 2: If you have the file in a specific location
        # face_cascade = cv2.CascadeClassifier('/path/to/haarcascade_frontalface_default.xml')
        
        # Option 3: Download from OpenCV GitHub
        # import urllib.request
        # cascade_url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
        # urllib.request.urlretrieve(cascade_url, "haarcascade_frontalface_default.xml")
        # face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
        
        if face_cascade.empty():
            faces = []
        else:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    except:
        faces = []
    
    if len(faces) > 0 and conversation_score < 2 and profile_score < 2:
        return "photo"
    elif conversation_score > profile_score and conversation_score >= 2:
        return "conversation"
    elif profile_score >= 2:
        return "profile"
    else:
        return "photo"  # Default


# Alternative lightweight version without face detection
def classify_image_simple(image_data: Dict) -> Literal["photo", "profile", "conversation"]:
    """
    Simple implementation using only OCR and pattern matching, no face detection.
    """
    import pytesseract
    from PIL import Image
    import io
    
    # Convert bytes to PIL Image
    image = Image.open(io.BytesIO(image_data['data']))
    
    # Perform OCR
    try:
        text = pytesseract.image_to_string(image).lower()
    except:
        return "photo"  # If OCR fails, assume it's a photo
    
    # Pattern matching for classification
    conversation_indicators = [
        'sent', 'delivered', 'read', 'typing', 'message', 
        'reply', 'am', 'pm', 'yesterday', 'today',
        'iphone', 'android', 'whatsapp', 'messenger'
    ]
    
    profile_indicators = [
        'bio', 'about', 'interests', 'looking for', 'age', 
        'location', 'height', 'occupation', 'education',
        'followers', 'following', 'posts', 'likes', 'swipe',
        'match', 'instagram', 'twitter', 'tinder', 'bumble'
    ]
    
    # Count indicators
    conversation_score = sum(1 for indicator in conversation_indicators if indicator in text)
    profile_score = sum(1 for indicator in profile_indicators if indicator in text)
    
    # Look for message bubble patterns (timestamps, sequential messages)
    import re
    time_pattern = r'\d{1,2}:\d{2}\s*(am|pm|AM|PM)'
    has_timestamps = len(re.findall(time_pattern, text)) > 1
    
    if has_timestamps or conversation_score >= 3:
        return "conversation"
    elif profile_score >= 3:
        return "profile"
    else:
        # Check if there's very little text (likely a photo)
        word_count = len(text.split())
        if word_count < 10:
            return "photo"
        
        # If we still can't determine, use the highest score
        if conversation_score > profile_score:
            return "conversation"
        elif profile_score > conversation_score:
            return "profile"
        else:
            return "photo"


# # Example usage
# if __name__ == "__main__":
#     # Test with a sample image
#     with open("test_image.jpg", "rb") as f:
#         image_dict = {
#             'data': f.read(),
#             'filename': 'test_image.jpg',
#             'mime_type': 'image/jpeg'
#         }
    
#     result = classify_image(image_dict)
#     print(f"Classification: {result}")