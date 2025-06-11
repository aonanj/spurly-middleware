from flask import current_app
from PIL import Image
import io
from infrastructure.clients import get_openai_client
from infrastructure.logger import get_logger
from utils.prompt_loader import load_system_prompt
import json
import openai
import base64
import os
from typing import List, Dict, Any


logger = get_logger(__name__)



def _downscale_image_from_bytes(image_bytes: bytes, max_dim: int = 1024) -> bytes:
    # Load image from byte stream
    img = Image.open(io.BytesIO(image_bytes))

    # Resize while preserving aspect ratio
    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    # Save back to bytes
    output_buffer = io.BytesIO()
    img.save(output_buffer, format='JPEG')  # or 'JPEG' if needed
    return output_buffer.getvalue()


def infer_personality_traits_from_openai_vision(image_files_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Infers personality traits from a list of images using OpenAI's vision model.

    Args:
        image_files_data: A list of dictionaries, where each dictionary contains:
            "bytes": The image content in bytes.
            "content_type": The image content type (e.g., "image/jpeg").

    Returns:
        A list of unique trait dictionaries, e.g., [{"trait": "Adventurous", "confidence": 0.95}, ...].
        Returns an empty list if no traits could be inferred or an error occurs.
    """
    if not image_files_data:
        return []

    openai_client = get_openai_client() # Get the initialized OpenAI client
    if not openai_client:
        logger.error("OpenAI client not available for trait inference.")
        return []

    all_inferred_traits_with_scores = []

    for image_data in image_files_data:
        if isinstance(image_data, dict):
            image_bytes = image_data.get("bytes")
        else:
            logger.warning("Invalid image_data format. Expected a dictionary.")
            continue
        content_type = image_data.get("content_type", "application/octet-stream") # Default if not provided

        if not image_bytes:
            logger.warning(f"Skipping trait inference for unknown image due to missing image bytes.")
            continue

        try:
            resized_image_bytes = _downscale_image_from_bytes(image_bytes, max_dim=1024)
            base64_image = base64.b64encode(resized_image_bytes).decode('utf-8')
            images_url = f"data:image/jpeg;base64,{base64_image}"
            ##encoded_imgs = json.dumps([base64_image])

            prompt_file = os.path.join(current_app.root_path, 'resources', 'spurly_inference_prompt.txt')
            with open(prompt_file, 'r') as f:
                prompt_template = f.read().strip()
                image_prompt_appendix = "\nThe following images are Base64-ended. There is one person commonly shown in all images. You should infer personality traits about that one person. "
                prompt = prompt_template.join(image_prompt_appendix)
            
            chat_client = get_openai_client()
            resp = chat_client.chat.completions.create(
                model="gpt-4o", 
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": images_url}}
                        ]
                    }
                ]
            )

            # 4) Parse the JSON response
            content = (resp.choices[0].message.content or "").strip()
            traits: List[Dict[str, float]] = json.loads(content)
            
            # Attempt to parse the JSON from the response content
            try:
                traits_from_image = json.loads(content)
                if isinstance(traits_from_image, list):
                    for trait_item in traits_from_image:
                        if isinstance(trait_item, dict) and "trait" in trait_item and "confidence" in trait_item:
                            all_inferred_traits_with_scores.append({
                                "trait": str(trait_item["trait"]),
                                "confidence": float(trait_item["confidence"])
                            })
                        else:
                            logger.error(f"Invalid trait item format from OpenAI for unknown image: {trait_item}")
                else:
                    logger.error(f"Unexpected response format from OpenAI (not a list) for unknown image: {traits_from_image}")

            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from OpenAI response for unknown image: {content}", exc_info=True)
            except Exception as e:
                logger.error(f"Error processing OpenAI response for unknown image: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error during OpenAI trait inference for unknown image: {e}", exc_info=True)
            # Continue to the next image if one fails

    # Remove duplicate traits, keeping the one with the highest confidence
    # This is a simple way; more sophisticated merging could be done.
    final_traits_dict = {}
    for item in all_inferred_traits_with_scores:
        trait_name = item["trait"]
        confidence = item["confidence"]
        if trait_name not in final_traits_dict or confidence > final_traits_dict[trait_name]["confidence"]:
            final_traits_dict[trait_name] = item
    
    unique_traits_with_scores = list(final_traits_dict.values())
    
    #DEBUG 
    logger.error(f"Inferred {len(unique_traits_with_scores)} unique traits with scores from images.")
    return unique_traits_with_scores

def infer_situation(conversation):
    """
    Uses GPT to infer the messaging situation from a list of conversation turns.

    Args:
        conversation (list): [{"speaker": "user"|"other", "text": "..."}, ...]

    Returns:
        dict: {"situation": "cta_setup", "confidence": 0.89}
    """

    prompt = f"""You're a messaging assistant. Analyze the situation of the conversation below.
Respond ONLY with a JSON object like this:
{{"situation": "cta_setup", "confidence": 0.85}}

Valid situations:
- cold_open
- recovery
- follow_up_no_response
- cta_setup
- cta_response
- message_refinement
- topic_pivot
- re_engagement

Conversation:
{json.dumps(conversation, indent=2)}
"""

    try:
        system_prompt = load_system_prompt()
        chat_client=get_openai_client()
        response = chat_client.chat.completions.create(
            model=current_app.config['AI_MODEL'],
            messages=[
                {"role": current_app.config['AI_MESSAGES_ROLE_SYSTEM'], "content": system_prompt},
                {"role": current_app.config['AI_MESSAGES_ROLE_USER'], "content": prompt}
                ], temperature=current_app.config['AI_TEMPERATURE_RETRY'],
        )

        output = (response.choices[0].message.content or "").strip()
        return json.loads(output)
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return {"situation": "cold_open", "confidence": 0.0}


def infer_tone(message):
    """
    Uses GPT to infer the tone of a single message with a confidence score.

    Args:
        message (str): The message to analyze.

    Returns:
        dict: {"tone": "warm", "confidence": 0.82}
    """
    prompt = f"""Analyze the tone of the message below. Respond only with a JSON object like:
{{"tone": "banter", "confidence": 0.84}}

Message:
{message}"""

    try:
        chat_client = get_openai_client()
        response = chat_client.chat.completions.create(
            model=current_app.config['AI_MODEL'],
            messages=[{"role": current_app.config['AI_MESSAGES_ROLE_USER'], "content": prompt}], temperature=current_app.config['AI_TEMPERATURE_RETRY'],
        )
        output = (response.choices[0].message.content or "").strip()
        return json.loads(output)
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return {"tone": "neutral", "confidence": 0.0}

def infer_personality_traits_from_pics(image_data: List[bytes]) -> List[Dict[str, float]]:
    """
    Infer personality traits from one or more pictures of a connection.

    Expected callers:
        - create_connection()
        - update_connection()

    Args:
        image_data (List[bytes]): A list of raw image byte blobs (e.g., JPEG/PNG)
            for the connection whose personality traits we want to infer.

    Returns:
        List[Dict[str, float]]: A mapping from inferred personality trait names
            to confidence scores (0.0–1.0).
    """
    # 1) Base64‑encode each image so it can be sent in a text prompt
    encoded_imgs = [base64.b64encode(img).decode("utf-8") for img in image_data]

    # 2) Build a prompt asking the model to analyze the images
    prompt_file = os.path.join(current_app.root_path, 'resources', 'spurly_inference_prompt.txt')
    with open(prompt_file, 'r') as f:
        prompt_template = f.read().strip()
    image_prompt_appendix = "\nThe following images are Base64-ended. There is one person commonly shown in all images. You should infer personality traits about that one person. "
    f"\n\nImages: \n{json.dumps(encoded_imgs)}"
    prompt = prompt_template.join(image_prompt_appendix)

    # 3) Call the OpenAI ChatCompletion API
    chat_client = get_openai_client()
    resp = chat_client.chat.completions.create(
        model=current_app.config['AI_MODEL'], 
        messages=[{"role": current_app.config['AI_MESSAGES_ROLE_USER'], "content": prompt}], 
        temperature=current_app.config['AI_TEMPERATURE_RETRY'],
    )
    

    # 4) Parse the JSON response
    content = (resp.choices[0].message.content or "").strip()
    traits: List[Dict[str, float]] = json.loads(content)
    return traits