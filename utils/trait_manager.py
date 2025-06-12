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
    raise ValueError("No JSON code block found.")





def infer_personality_traits_from_openai_vision(image_files_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Infers personality traits from a list of images using OpenAI's vision model.

    Args:
        image_files_data: A list of dictionaries, where each dictionary contains:
            "bytes": The image content in bytes.
            "content_type": The image content type (e.g., "image/jpeg").

    Returns:
        A list of trait dictionaries, e.g., [{"trait": "Adventurous", "confidence": 0.95}, ...].
        Returns all traits from all images without deduplication.
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

            prompt = """
                You are an expert at human behavioral analysis, specifically at matching patterns in an individual's appearance to behavioral characteristics. You are tasked with inferring five personality traits based solely on visual observation of an individual's appearance in a set of one to four images that include all include the same individual. If multiple images are provided featuring more than one person, you are to infer personality traits for the individual that is shown in all images. If multiple images are provided and two or more individuals are shown in all images, you should infer personality traits for the most prominently featured individual, but adjust the confidence scores downward accordingly. You should make judgments using visible features such as facial expression, personal grooming and style, posture, clothing, gaze, and environmental context, but avoid overanalyzing or attempting deep psychological evaluation. This is exercise is purposefully superficial, so you need not be comprehensive or exhaustive in your analysis. Neither should you temper your analysis with excessive caution or uncertainty, which also defeats the purpose of this exercise.

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

            
            chat_client = get_openai_client()
            resp = chat_client.chat.completions.create(
                model="gpt-4o", 
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": [
                            {"type": "text", "text": "Please infer five personality traits from the image or images provided."},
                            {"type": "image_url", "image_url": {"url": images_url}}
                        ]
                    }
                ],
                max_tokens=3000,
                temperature=0.5,
            )

            # 4) Parse the JSON response
            content = (resp.choices[0].message.content or "").strip()
            json_parsed_content = _extract_json_block(content)
                       
            # Attempt to parse the JSON from the response content
            try:
                parsed_response = json.loads(json_parsed_content)
                
                # Check if the response has the expected structure
                if isinstance(parsed_response, dict) and "personality_traits" in parsed_response:
                    traits_from_image = parsed_response["personality_traits"]
                    
                    if isinstance(traits_from_image, list):
                        logger.debug(f"Processing {len(traits_from_image)} traits from image")
                        for trait_item in traits_from_image:
                            if isinstance(trait_item, dict) and "personality_trait" in trait_item and "confidence_score" in trait_item:
                                all_inferred_traits_with_scores.append({
                                    "trait": str(trait_item["personality_trait"]),
                                    "confidence": float(trait_item["confidence_score"])
                                })
                                logger.debug(f"Added trait: {trait_item['personality_trait']} with confidence {trait_item['confidence_score']}")
                            else:
                                logger.error(f"Invalid trait item format from OpenAI for unknown image: {trait_item}")
                    else:
                        logger.error(f"Unexpected personality_traits format from OpenAI (not a list) for unknown image: {traits_from_image}")
                else:
                    logger.error(f"Unexpected response structure from OpenAI for unknown image: {parsed_response}")

            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from OpenAI response for unknown image: {content}", exc_info=True)
            except Exception as e:
                logger.error(f"Error processing OpenAI response for unknown image: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error during OpenAI trait inference for unknown image: {e}", exc_info=True)
            # Continue to the next image if one fails

    # Return all traits without deduplication
    logger.info(f"Inferred {len(all_inferred_traits_with_scores)} total traits from {len(image_files_data)} images.")
    return all_inferred_traits_with_scores

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