from flask import current_app
import re
from PIL import Image
import io
from infrastructure.clients import get_openai_client
from infrastructure.logger import get_logger
import json
import base64
import os
from typing import List, Dict, Any


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
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    elif (text.strip().startswith('{') and text.strip().endswith('}')) or (text.strip().startswith('[') and text.strip().endswith(']')):
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

def infer_situation(conversation) -> dict:
    """
    Uses GPT to infer the messaging situation from a list of conversation turns.

    Args:
        conversation (list): [{"speaker": "user"|"other", "text": "..."}, ...]

    Returns:
        dict: {"situation": "cta_setup", "confidence": 0.89}
    """

    system_prompt = """
    You are a conversation analyst. Your task is to infer the situational context or intent behind a given text message. Focus on what the sender is trying to accomplish in the conversation. This might include recovering from a misstep, shifting the topic, escalating or de-escalating intimacy, prompting action, testing interest, expressing vulnerability, or managing face. Assume messages come from informal, text-based conversations, often in early-stage romantic or social exchanges. Be attuned to subtext, indirect cues, and soft pivots.
    
Valid situations:
- "cold_open": The conversation is just starting, no context yet.
- "recovery": The conversation has gone off track, possibly because the user said something unintentionally offensive or offputting, and the user is trying to get it back on track.
- "follow_up_no_response": The user has sent a message but received no response, seemingly because the other person is not interested.
- "cta_setup": The user is trying to set up a call to action (CTA) like a date or phone call.
- "cta_response": The user has received a response to a CTA, like a date or phone call.
- "message_refinement": The user is trying to refine a message they sent, possibly because it was misunderstood or not well received.
- "topic_pivot": The user is trying to change the topic of conversation, possibly because the current topic is not going well.
- "re_engagement": The user is trying to re-engage the other person after a lull in conversation.
"""

    prompt = f"""You're an expert messaging assistant. Analyze the following message and infer the likely conversational situation or intent behind it. Consider whether the sender is attempting a recovery (e.g. after a misstep), setting up a call to action, changing the subject, seeking validation, escalating or de-escalating intimacy, testing interest, etc.
Respond ONLY with a JSON object like this:
{{"situation": "<situation>", "confidence": 0.85}}. For example, if you infer the situation is "cold_open" with 85% confidence, you would respond:
{{"situation": "cold_open", "confidence": 0.85}}.


Conversation:
{json.dumps(conversation, indent=3)}
"""

    if not conversation or conversation.isEmpty() or conversation.count == 0:
        logger.error("No conversation provided for situation inference.")
        return {"situation": "cold_open", "confidence": 0.0}

    #DEBUG
    logger.error("DEBUG: trait_manager.infer_situation: Inferring situation from conversation: %s", json.dumps(conversation, indent=3))

    openai_client = get_openai_client()
    if not openai_client:
        logger.error("OpenAI client not available for inferring situation.")
        return {"situation": "cold_open", "confidence": 0.0}
    
    try:
        #DEBUG
        logger.error("DEBUG: trait_manager.infer_situation: Sending prompt to OpenAI: %s", prompt)
        response = openai_client.chat.completions.create(
            model="chatgpt-4o-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
                ],
            max_tokens=3000,
            temperature=0.6
            )
        content = (response.choices[0].message.content or "").strip()
        json_parsed_content = extract_json_block(content)
        return json.loads(json_parsed_content)
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error in infer_situation decorator of middleware.py: %s", err_point, e)
        return {"situation": "cold_open", "confidence": 0.0}


def infer_tone(message):
    """
    Uses GPT to infer the tone of a single message with a confidence score.

    Args:
        message (str): The message to analyze.

    Returns:
        dict: {"tone": "warm", "confidence": 0.82}
    """

    system_prompt = """You are a communication analyst. Your task is to infer the tone of a text message, based on word choice, punctuation, style, and implicit emotional signals. The tone may include categories such as: sincere, annoyed, sarcastic, playful, flirtatious, defensive, passive-aggressive, indifferent, enthusiastic, formal, etc. Assume messages come from informal, text-based conversations, often in early-stage romantic or social exchanges. Be attuned to subtext, indirect cues, and soft pivots. Messages may be short, ambiguous, or deliberately indirect—read between the lines where appropriate. Your analysis should focus on the emotional intent behind the message, rather than its literal meaning. Inferred tone should be 1-2 words. Output a JSON object with the inferred tone and a confidence score from 0 to 1:
    {"tone": "<tone>", "confidence": 0.XX}  
    """
    prompt = f"""Analyze the tone of the following Text Message. Identify the emotional intent (e.g., friendly, annoyed, flirtatious, sarcastic, indifferent, enthusiastic, formal, passive-aggressive, etc.). Respond only with a JSON object like:
{{"tone": "<tone>", "confidence": 0.84}}. For example, if you infer the tone is "friendly" with 84% confidence, you would respond:
{{"tone": "friendly", "confidence": 0.84}}. 

Text Message: 
{message}"""

    if not message or message.strip() == "":
        logger.error("No message provided for tone inference.")
        return {"tone": "neutral", "confidence": 0.0}

    #DEBUG
    logger.error("DEBUG: trait_manager.infer_tone: Inferring situation from conversation: %s", message)
    
    openai_client = get_openai_client()
    if not openai_client:
        logger.error("OpenAI client not available for inferring tone.")
        return  {"tone": "neutral", "confidence": 0.0}
    
    
    
    try:
        #DEBUG
        logger.error("DEBUG: trait_manager.infer_tone: Sending prompt to OpenAI: %s", prompt)
        response = openai_client.chat.completions.create(
            model="chatgpt-4o-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
                ],
            max_tokens=3000,
            temperature=0.5
            )
        content = (response.choices[0].message.content or "").strip()
        json_parsed_content = extract_json_block(content)
        return json.loads(json_parsed_content)
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error in infer_tone decorator of trait_manager.py: %s", err_point, e)
        return {"tone": "neutral", "confidence": 0.0}

def analyze_convo_for_context(images: List[Dict]) -> List[Dict]:
    """
    Analyzes images to extract conversation context and profile information.
    
    Args:
        images: List of dictionaries containing:
            - 'data': raw bytes of image
            - 'filename': Original filename
            - 'mime_type': MIME type of the image
    
    Returns:
        List containing:
            - Dict: 'situation': inferred situation (str), 
                     'confidence_score': confidence score for the situation inference (float)
            - Dict: 'tone': inferred tone of the other person (str),
                     'confidence_score': confidence score for the tone inference (float)

    """
    empty_context = []
    empty_context.append({"situation": "none", "confidence_score": 0.0})
    empty_context.append({"tone": "none", "confidence_score": 0.0})
    
    if not images:
        return empty_context
    
    
    image_parts = []
    for image_data in images:
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
        return empty_context

        
    # Create a prompt for analyzing the images
    system_prompt = """
    You are an expert assistant highly skilled in human interaction and behavioral analysis in the context of conversational interactions, especially those ocurring as text/direct messaging exchanges. Analyze the accompanying image or images and extract the following information:

        - Extract the conversation messages in order. Assume messages come from informal, text-based conversations, often in early-stage romantic or social exchanges, such as on dating apps or social media.
        - Identify who is sending each message (user vs other person)
        - Infer the situation of the conversation: Focus on what the user is trying to accomplish. This might include recovering from a misstep, shifting the topic, escalating or de-escalating intimacy, prompting action, testing interest, expressing vulnerability, or managing face. Be attuned to subtext, indirect cues, and soft pivots. Inferred situation should be 1-2 words, accompanied by a confidence score expressed as a float between 0 and 1 to indicate how confident you are in your inference (lower values may be appropriate if the conversation is ambiguous or short). Example situations include: "cold_open", "recovery", "follow_up_no_response", "cta_setup", "cta_response", "message_refinement", "topic_pivot", "re_engagement". 
        - Infer the tone of the other person, giving the greatest weight to the most recent message from the other person. Tone inference should be based on word choice, punctuation, style, and implicit emotional signals (e.g., emoji usage). The tone should be 1-2 words; examples include: sincere, annoyed, sarcastic, playful, flirtatious, defensive, passive-aggressive, indifferent, enthusiastic, formal, etc.  Be attuned to subtext, indirect cues, and soft pivots. Messages may be short, ambiguous, or deliberately indirect—read between the lines where appropriate. Your analysis should focus on the emotional intent behind the message, rather than its literal meaning. Inferred tone should be 1-2 words, accompanied by a confidence score expressed as a float between 0 and 1 to indicate how confident you are in your inference.

    
    Format your response as a list of two JSON objects:
    [
        {
            "situation": <inferred situation>,
            "confidence_score": <0.XX> 
        },
        {
            "tone": <inferred tone>,
            "confidence_score": <0.XX>
        }
    ]

    Your output must be strictly formatted as above. Do NOT include any text or characters outside of the JSON object. No explanations, no additional text, no markdown formatting. Just the JSON object.
    """
    
    user_prompt = """
    Here is/are the image/images of the conversation you should analyze. Please infer both situation and tone based on the images provided. Respond with a JSON object containing the inferred situation and tone, as described in the system prompt. If the images do not contain any conversation, you should return "none" for both situation and tone, with a confidence score of 0.0.
    """
        
    openai_client = get_openai_client()
    if not openai_client:
        return empty_context
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": user_prompt},
                 *image_parts
                ]
            }],
            max_tokens=3000,
            temperature=0.5
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