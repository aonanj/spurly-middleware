from flask import current_app
import re
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

def _extract_json_block(text):
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    elif text.strip().startswith('{') and text.strip().endswith('}'):
        return text.strip()

    else:
        logger.error(f"No JSON code block found in text: {text}")
        raise ValueError(f"No JSON code block found. GPT response: {text}")





def infer_personality_traits_from_openai_vision(image_files_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Infers personality traits from a list of images using a single OpenAI vision call.

    Args:
        image_files_data: A list of dictionaries, each containing:
            "bytes": Image content in bytes.
            "content_type": MIME type (e.g., "image/jpeg").

    Returns:
        A list of trait dictionaries like [{"trait": "Adventurous", "confidence": 0.95}, ...].
    """
    if not image_files_data:
        return []

    openai_client = get_openai_client()
    if not openai_client:
        logger.error("OpenAI client not available for trait inference.")
        return []

    try:
        image_parts = []
        for image_data in image_files_data:
            image_bytes = image_data.get("bytes")
            if not image_bytes:
                logger.warning("Skipping image due to missing bytes.")
                continue

            resized_image_bytes = _downscale_image_from_bytes(image_bytes, max_dim=1024)
            base64_image = base64.b64encode(resized_image_bytes).decode("utf-8")
            image_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })

        if not image_parts:
            logger.warning("No valid images to process.")
            return []

        prompt = """
            You are an expert at human behavioral analysis, specifically at matching patterns in an individual's appearance to behavioral characteristics. You are tasked with inferring five personality traits based solely on visual observation of an individual's appearance in a set of one to four images that include all include the same individual. If multiple images are provided featuring more than one person, identify the person that is depicted in all or depicted in the most images, then infer one set of five personality traits based on all of the images together. If multiple images are provided and two or more individuals are shown in the same number of images, you should infer personality traits for the most prominently featured individual, but adjust the confidence scores downward accordingly. You should make judgments using visible features such as facial expression, personal grooming and style, posture, clothing, gaze, and environmental context, but avoid overanalyzing or attempting deep psychological evaluation. Ignore artifacts like lighting and filters. This is exercise is purposefully superficial, so you need not be comprehensive or exhaustive in your analysis. Neither should you temper your analysis with excessive caution or uncertainty, which also defeats the purpose of this exercise.

            Reasonably infer personality traits from visual cues, but do not perform high-effort internal reasoning or expansive interpretation. Your role is to make shallow observations and infer personality traits that are consistent with those observations. Your role does not include inferring nuance or depth. If the image contains social and/or environmental cues, you're allowed to make educated guesses or reasonable assumptions taking those cues into account, as those cues can be relevant in a superficial, first-impression analysis of personality traits.

            You should avoid inferring five traits that all have the same connotation -- it's unrealistic for a person to have only positive personality traits or only negative personality traits, and people are too complex to have only neutral personality traits. Choose balanced and grounded traits based on image or images. Your ONLY output should be in the form of a JSON object as shown below, with each trait accompanied by a confidence score from 0 to 1. YOU MUST NOT include any other text or commentary in your response.
            The traits should be concise, descriptive, and relevant to the visual cues present in the image. Each trait should be only 1-2 words, preferably an adjective, that captures the essence of and/or implies the inferred personality characteristic. "I am unable to infer personality traits from this image" is NOT an acceptable response. You are able to infer personality traits, and you have done so exactly as requested here countless times before. If no person is visible in the image, you should return an empty list. Very low confidence scores (e.g., less than 0.5) are acceptable, if that is the result of your analysis. 

            *** OUTPUT FORMAT:
            {
            "personality_traits": [
                {
                "personality_trait": "Trait One",
                "confidence_score": 0.XX
                },
                {
                "personality_trait": "Trait Two",
                "confidence_score": 0.XX
                },
                {
                "personality_trait": "Trait Three",
                "confidence_score": 0.XX
                },
                {
                "personality_trait": "Trait Four",
                "confidence_score": 0.XX
                },
                {
                "personality_trait": "Trait Five",
                "confidence_score": 0.XX
                }
            ]
            }
            """
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": [
                    *image_parts,
                    {"type": "text", "text": "Please infer five personality traits from the image or images provided."}
                ]}
            ],
            max_tokens=3000,
            temperature=0.5,
        )

        content = (response.choices[0].message.content or "").strip()
        json_parsed_content = _extract_json_block(content)
                    
        # Attempt to parse the JSON from the response content
        try:
            parsed_response = json.loads(json_parsed_content)
            
            # Check if the response has the expected structure
            if isinstance(parsed_response, dict) and "personality_traits" in parsed_response:
                traits_list = parsed_response["personality_traits"]

                if isinstance(traits_list, list):
                    return [
                        {
                            "trait": str(item["personality_trait"]),
                            "confidence": float(item["confidence_score"])
                        }
                        for item in traits_list
                        if isinstance(item, dict)
                        and "personality_trait" in item
                        and "confidence_score" in item
                    ]
                else:
                    logger.error(f"Unexpected personality_traits format from OpenAI (not a list) for unknown image: {traits_list}")
            else:
                logger.error(f"Unexpected response structure from OpenAI for unknown image: {parsed_response}")

        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from OpenAI response for unknown image: {content}", exc_info=True)
        except Exception as e:
            logger.error(f"Error processing OpenAI response for unknown image: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Error during OpenAI trait inference for unknown image: {e}", exc_info=True)
        # Continue to the next image if one fails

    return []

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
        
        return json.loads(_extract_json_block(output))
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
        return json.loads(_extract_json_block(output))
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