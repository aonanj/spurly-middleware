from flask import current_app
import re
from PIL import Image
import io
from infrastructure.clients import get_openai_client
from infrastructure.logger import get_logger
from utils.usage_tracker import track_openai_usage_manual, estimate_tokens_from_messages
import json
import base64
import os
from typing import List, Dict, Any, Optional


logger = get_logger(__name__)



def downscale_image_from_bytes(image_bytes: bytes, max_dim: int = 1024) -> bytes:
    # Load image from byte stream
    img = Image.open(io.BytesIO(image_bytes))

    # Resize while preserving aspect ratio
    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    # Save back to bytes
    output_buffer = io.BytesIO()
    img.save(output_buffer, format='JPEG')  # or 'JPEG' if needed
    return output_buffer.getvalue()

def extract_json_block(text):
    # First, try to find a JSON code block with either an object or an array
    match = re.search(r"```json\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # If not wrapped in a code block, check if it looks like a JSON object or array
    stripped = text.strip()
    if (stripped.startswith('{') and stripped.endswith('}')) or (stripped.startswith('[') and stripped.endswith(']')):
        return stripped

    # If nothing matches, raise an error
    logger.error(f"No JSON code block found in text: {text}")
    raise ValueError(f"No JSON code block found. GPT response: {text}")

def infer_personality_traits_from_openai_vision(image_files_data: List[Dict[str, Any]], user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Infers personality traits from a list of images using a single OpenAI vision call.

    Args:
        image_files_data: A list of dictionaries, each containing:
            "bytes": Image content in bytes.
            "content_type": MIME type (e.g., "image/jpeg").
        user_id: User ID for usage tracking (optional)

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
                logger.error("Skipping image due to missing bytes.")
                continue

            resized_image_bytes = downscale_image_from_bytes(image_bytes, max_dim=1024)
            base64_image = base64.b64encode(resized_image_bytes).decode("utf-8")
            image_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })

        if not image_parts:
            logger.error("No valid images to process.")
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
                "confidence": 0.XX
                },
                {
                "personality_trait": "Trait Two",
                "confidence": 0.XX
                },
                {
                "personality_trait": "Trait Three",
                "confidence": 0.XX
                },
                {
                "personality_trait": "Trait Four",
                "confidence": 0.XX
                },
                {
                "personality_trait": "Trait Five",
                "confidence": 0.XX
                }
            ]
            }
            """
        
        # Prepare messages for token estimation
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": [
                *image_parts,
                {"type": "text", "text": "Please infer five personality traits from the image or images provided."}
            ]}
        ]
        
        # Estimate tokens for manual tracking
        estimated_prompt_tokens = estimate_tokens_from_messages(messages)
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=3000,
            temperature=0.5,
        )

        # Track usage if user_id is provided
        if user_id:
            if hasattr(response, 'usage') and response.usage:
                track_openai_usage_manual(
                    user_id=user_id,
                    model="gpt-4o",
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    feature="trait_inference"
                )
            else:
                # Fallback to estimation
                estimated_completion_tokens = 500  # Conservative estimate for trait inference
                track_openai_usage_manual(
                    user_id=user_id,
                    model="gpt-4o",
                    prompt_tokens=estimated_prompt_tokens,
                    completion_tokens=estimated_completion_tokens,
                    feature="trait_inference"
                )

        content = (response.choices[0].message.content or "").strip()
        json_parsed_content = extract_json_block(content)
                    
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
                            "confidence": float(item["confidence"])
                        }
                        for item in traits_list
                        if isinstance(item, dict)
                        and "personality_trait" in item
                        and "confidence" in item
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
        logger.error(f"Error in trait inference: {e}", exc_info=True)

    return []

def infer_situation(conversation, user_id: Optional[str] = None) -> dict:
    """
    Uses GPT to infer the likely conversational situation or intent behind a conversation.
    
    Args:
        conversation: Conversation object to analyze
        user_id: User ID for usage tracking (optional)
    
    Returns:
        dict: {"situation": "cold_open", "confidence": 0.85}
    """
    system_prompt = """You are an expert assistant highly skilled in human interaction and behavioral analysis in the context of conversational interactions, especially those ocurring as text/direct messaging exchanges. Analyze the accompanying conversation to infer the situation surrounding the conversation, particularly in the most recent messages or message. Assume messages come from informal, text-based conversations, often in early-stage romantic or social exchanges, such as on dating apps or social media. Consider not just the plain meaning of each message, but give equal consideration to unspoken intent at the most recent point in the conversation, subtext, indirect cues, soft pivots, and other subtle indicators (e.g., message length, emjoi and punctuation usage, timeperiod between messages, etc.). 
    
    Inferred situation should be 1-2 words, accompanied by a confidence score expressed as a float between 0 and 1 to indicate how confident you are in your inference (lower values may be appropriate if the conversation is ambiguous or short). Consider whether the sender is attempting a recovery (e.g. after a misstep), setting up a call to action (cta), responding to a cta, reengaging after a long period of no contact, restarting a conversation after receiving no response, changing the subject, refining a message that may have been misunderstood or was unclear, or a "cold_open" where the sender is initiating contact without prior context. Again, you are to assume this conversation is occuring in the early stages of a social or romantic interaction, such as on a dating app or social media, and therefore situations that are more common in familiar contexts need to be avoided -- examples to avoid include "escalating intimacy", "seeking personal validation", etc. These are not appropriate situations to infer in this context, as they are not common in early-stage social or romantic interactions. You should also avoid inferring situations that are too specific or detailed, such as "seeking validation for a personal decision" or "testing interest in a specific topic". Instead, focus on broader situations that are more likely to occur in the context of a dating app or social media conversation.
    
    Responses indicating that you are unable to infer a situation are unacceptable, and you are prohibited from returning such responses. You already have a mechanism to convey uncertainty, which is the confidence score. If you are unable to infer a situation, you should return a situation of "cold_open" with a confidence score of 0.0. You should not return an empty response or a response that does not conform to the expected JSON format.
    
    You should respond ONLY with a JSON object in the following format:
    {"situation": "<situation>", "confidence": 0.XX}. For example, if you infer the situation is "cold_open" with 85 percent confidence, you would format your response like this: {"situation": "cold_open", "confidence": 0.85}.
"""

    prompt = f"""You are an expert assistant highly skilled in human interaction and behavioral analysis in the context of conversational interactions, especially those ocurring as text/direct messaging exchanges. Analyze the following conversation and infer the likely conversational situation or intent behind it. Consider whether the sender is attempting a recovery (e.g. after a misstep), setting up a call to action (cta), responding to a cta, reengaging after a long period of no contact, restarting a conversation after receiving no response, changing the subject, refining a message that may have been misunderstood or was unclear, or a "cold_open" where the sender is initiating contact without prior context, etc.
    
    Respond ONLY with a JSON object like this: 
        {{"situation": "<situation>", "confidence": 0.XX}}. 
    For example, if you infer the situation is "cold_open" with 85% confidence, you would respond:
        {{"situation": "cold_open", "confidence": 0.85}}.


Conversation:
{json.dumps(conversation, indent=3)}
"""

    if not conversation or conversation.isEmpty() or conversation.count == 0 or len(conversation) == 0:
        logger.error("No conversation provided for situation inference.")
        return {"situation": "cold_open", "confidence": 0.0}


    openai_client = get_openai_client()
    if not openai_client:
        logger.error("OpenAI client not available for inferring situation.")
        return {"situation": "cold_open", "confidence": 0.0}
    
    try:
        # Prepare messages for token estimation
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        # Estimate tokens for manual tracking
        estimated_prompt_tokens = estimate_tokens_from_messages(messages)
        

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,  # type: ignore
            max_tokens=3000,
            temperature=0.7
            )
        
        # Track usage if user_id is provided
        if user_id:
            if hasattr(response, 'usage') and response.usage:
                track_openai_usage_manual(
                    user_id=user_id,
                    model="gpt-4o",
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    feature="situation_inference"
                )
            else:
                # Fallback to estimation
                estimated_completion_tokens = 200  # Conservative estimate for situation inference
                track_openai_usage_manual(
                    user_id=user_id,
                    model="gpt-4o",
                    prompt_tokens=estimated_prompt_tokens,
                    completion_tokens=estimated_completion_tokens,
                    feature="situation_inference"
                )
        
        content = (response.choices[0].message.content or "").strip()
        json_parsed_content = extract_json_block(content)
        return json.loads(json_parsed_content)
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error in infer_situation decorator of middleware.py: %s", err_point, e)
        return {"situation": "cold_open", "confidence": 0.0}


def infer_tone(message, user_id: Optional[str] = None):
    """
    Uses GPT to infer the tone of a single message with a confidence score.

    Args:
        message (str): The message to analyze.
        user_id (str): User ID for usage tracking (optional)

    Returns:
        dict: {"tone": "warm", "confidence": 0.82}
    """

    system_prompt = """You are an expert assistant highly skilled in human interaction and behavioral analysis in the context of conversational interactions, especially those ocurring as text/direct messaging exchanges. Your task is to infer the tone of a conversation, giving the greatest weight to the most recent message from the other person. Assume messages come from informal, text-based conversations, often in early-stage romantic or social exchanges, such as on dating apps or social media. Consider factors such as word choice, punctuation, style, and implicit emotional signals. The tone may include categories such as: sincere, annoyed, sarcastic, playful, flirtatious, defensive, passive-aggressive, indifferent, enthusiastic, formal, etc. Be attuned to subtext, indirect cues, and soft pivots. Messages may be short, ambiguous, or deliberately indirect—read between the lines where appropriate. Your analysis should focus on the emotional intent behind the messages, rather than literal meaning. Inferred tone should be 1-2 words. Output a JSON object with the inferred tone and a confidence score from 0 to 1:
    {"tone": "<tone>", "confidence": 0.XX}  
    """
    prompt = f"""Analyze the tone of the following Text Message. Identify the emotional intent (e.g., friendly, annoyed, flirtatious, sarcastic, indifferent, enthusiastic, formal, passive-aggressive, etc.). Respond only with a JSON object like:
{{"tone": "<tone>", "confidence": 0.XX}}. For example, if you infer the tone is "friendly" with 84% confidence, you would respond:
{{"tone": "friendly", "confidence": 0.84}}. 

Text Message: 
{message}"""

    if not message or message.strip() == "":
        logger.error("No message provided for tone inference.")
        return {"tone": "neutral", "confidence": 0.0}

    
    openai_client = get_openai_client()
    if not openai_client:
        logger.error("OpenAI client not available for inferring tone.")
        return  {"tone": "neutral", "confidence": 0.0}
    
    
    
    try:
        # Prepare messages for token estimation
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        # Estimate tokens for manual tracking
        estimated_prompt_tokens = estimate_tokens_from_messages(messages)
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,  # type: ignore
            max_tokens=3000,
            temperature=0.5
            )
        
        # Track usage if user_id is provided
        if user_id:
            if hasattr(response, 'usage') and response.usage:
                track_openai_usage_manual(
                    user_id=user_id,
                    model="gpt-4o",
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    feature="tone_inference"
                )
            else:
                # Fallback to estimation
                estimated_completion_tokens = 100  # Conservative estimate for tone inference
                track_openai_usage_manual(
                    user_id=user_id,
                    model="gpt-4o",
                    prompt_tokens=estimated_prompt_tokens,
                    completion_tokens=estimated_completion_tokens,
                    feature="tone_inference"
                )
        
        content = (response.choices[0].message.content or "").strip()
        json_parsed_content = extract_json_block(content)
        return json.loads(json_parsed_content)
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error in infer_tone decorator of trait_manager.py: %s", err_point, e)
        return {"tone": "neutral", "confidence": 0.0}

def analyze_convo_for_context(images: List[Dict], user_id: Optional[str] = None) -> List[Dict]:
    """
    Analyzes conversation images for situation and tone context.
    
    Args:
        images: List of image dictionaries
        user_id: User ID for usage tracking (optional)
    
    Returns:
        List of context dictionaries
    """
    empty_context = [{"situation": "none", "confidence": 0.0}, {"tone": "none", "confidence": 0.0}]
    
    if not images:
        return empty_context
    
    try:
        image_parts = []
        for image_data in images:
            image_bytes = image_data.get("bytes")
            if not image_bytes:
                continue

            resized_image_bytes = downscale_image_from_bytes(image_bytes, max_dim=1024)
            base64_image = base64.b64encode(resized_image_bytes).decode("utf-8")
            image_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })

        if not image_parts:
            return empty_context

        system_prompt = """You are an expert assistant highly skilled in human interaction and behavioral analysis in the context of conversational interactions, especially those ocurring as text/direct messaging exchanges. Your task is to analyze the accompanying conversation depicted in the image or images to infer the situation surrounding the conversation and the tone of the conversation, particularly in the most recent messages or message. Assume messages come from informal, text-based conversations, often in early-stage romantic or social exchanges, such as on dating apps or social media. 
        
        You should first extract the conversation messages in order and correctly attribute each to either the user or the other person. Next, you should infer the likely conversational situation, which may be the user's unspoken intent at the most recent point in the conversation. Be attuned to not just the words themselves, but give equal consideration to indirect, implicit, and/or subtle indicators, which may be conveyed via subtext, word choice, indirect cues, soft pivots, and other such indicators (e.g., message length, emjoi and punctuation usage, timeperiod between messages, etc.). Messages may be short, ambiguous, or deliberately indirect—read between the lines where appropriate. Your analysis regarding situation should focus more on the user's perspective and intent behind the messages.
        
        Inferred situation should be 1-2 words, accompanied by a confidence score expressed as a float between 0 and 1 to indicate how confident you are in your inference (lower values may be appropriate if the conversation is ambiguous or short). Consider whether the sender is attempting a recovery (e.g. after a misstep), setting up a call to action (cta), responding to a cta, reengaging after a long period of no contact, restarting a conversation after receiving no response, changing the subject, refining a message that may have been misunderstood or was unclear, a tone mismatch in which the user is evidently failing to pick up on social cues conveyed by the other person, or a "cold_open" where the sender is initiating contact without prior context, etc. 
        
        Next, infer the tone of the conversation, giving the greatest weight to the most recent message from the other person. Tone inference should be based on word choice, punctuation, style, and implicit emotional signals (e.g., emoji usage, message length, receptiveness to the user's messages, etc.). The tone should be 1-2 words; examples include: sincere, annoyed, sarcastic, playful, flirtatious, defensive, passive-aggressive, indifferent, enthusiastic, formal, etc. Be attuned to subtext, indirect cues, and soft pivots, and other subtle indicators. Your analysis should focus on the emotional intent behind the message(s), rather than literal meaning, and you should infer tone primarily from the other person -- that is, the tone should be inferred for the other person, not inferred for the user. Inferred tone should be 1-2 words, accompanied by a confidence score expressed as a float between 0 and 1 to indicate how confident you are in your inference (lower values may be appropriate if the conversation is ambiguous or short).
        
        Responses indicating that you are unable to infer a situation and/or tone are unacceptable, and you are prohibited from returning such responses. You already have a mechanism to convey uncertainty, which is the confidence score. If you are uncertain in your inferences, you are permitted to return very low confidence scores. Under no cirucmstances should you return an empty response or a response that does not conform to the expected JSON format.
        
        You should respond ONLY with a list of JSON objects in the following format:
        [{"situation": <situation>, "confidence": 0.XX}, {"tone": <tone>, "confidence": 0.XX}]. For example, if you infer the situation is "cta_setup" with 85 percent confidence and the tone is "flirtatious" with 90 percent confidence, you would format your response like this:
        [{"situation": "cta_setup", "confidence": 0.85}, {"tone": "flirtatious", "confidence": 0.90}].
        
        If the images don't contain a conversation, return "none" for both with 0.0 confidence."""
    
        user_prompt = """
        Here is/are the image/images of the conversation you should analyze. Please infer both situation and tone based on the images provided. Respond with a JSON object containing the inferred situation and tone, as described in the system prompt. If the images do not contain any conversation, you should return "none" for both situation and tone, with a confidence score of 0.0.
        """
        
        openai_client = get_openai_client()
        if not openai_client:
            return empty_context
        
        # Prepare messages for token estimation
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user", 
                "content": [
                    {"type": "text", "text": user_prompt},
                    *image_parts
                ]
            }
        ]
        
        # Estimate tokens for manual tracking
        estimated_prompt_tokens = estimate_tokens_from_messages(messages)
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=3000,
            temperature=0.5
            )
        
        # Track usage if user_id is provided
        if user_id:
            if hasattr(response, 'usage') and response.usage:
                track_openai_usage_manual(
                    user_id=user_id,
                    model="gpt-4o",
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    feature="conversation_analysis"
                )
            else:
                # Fallback to estimation
                estimated_completion_tokens = 300  # Conservative estimate for conversation analysis
                track_openai_usage_manual(
                    user_id=user_id,
                    model="gpt-4o",
                    prompt_tokens=estimated_prompt_tokens,
                    completion_tokens=estimated_completion_tokens,
                    feature="conversation_analysis"
                )
        
        content = (response.choices[0].message.content or "")
        
        # Extract JSON from response
        json_parsed_content = extract_json_block(content)

        
        if json_parsed_content:
            return json.loads(json_parsed_content)
        else:
            logger.error("Failed to extract JSON from image analysis response")
            return empty_context
       
    except Exception as e:
        logger.error(f"Error analyzing images for situation and tone: {e}", exc_info=True)
        return empty_context


## DEPRECATED: This function is no longer used, but kept for reference.
# It was replaced by infer_personality_traits_from_openai_vision() which uses a single
# OpenAI vision call to infer personality traits from multiple images at once.
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