import base64
from datetime import datetime, timezone
from flask import current_app
import openai
from typing import Optional, Dict, List
from class_defs.profile_def import ConnectionProfile, UserProfile
from class_defs.spur_def import Spur
from infrastructure.logger import get_logger
from infrastructure.clients import get_openai_client
from infrastructure.id_generator import generate_spur_id, get_null_connection_id, generate_conversation_id
from services.connection_service import get_connection_profile, get_active_connection_firestore
from services.storage_service import get_conversation
from services.user_service import get_user
from utils.gpt_output import parse_gpt_output
from utils.prompt_template import build_prompt, get_system_prompt
from utils.trait_manager import infer_tone, infer_situation, analyze_convo_for_context, downscale_image_from_bytes, extract_json_block
from utils.validation import validate_and_normalize_output, classify_confidence, spurs_to_regenerate


logger = get_logger(__name__)

def get_user_profile_for_prompt(user_id: str) -> Dict:
    """
    Retrieves the user profile for prompt generation.

    Args:
        user_id (str): The ID of the user whose profile is to be fetched.

    Returns:
        Dict: A dictionary representation of the user's profile.
    """
    user = get_user(user_id)
    if not user:
        raise ValueError(f"User with ID {user_id} not found")
    
    prompt_dict = {}
    prompt_dict["name"] = f"    -User Name: {user.name if user.name else ''}, \n"
    prompt_dict["age"] = f" -User Age: {user.age if user.age else 'unknown'}, \n"
    prompt_dict["user_context_block"] = f"  -Personal Info about User {user.name if user.name else ''}: {user.user_context_block if user.user_context_block else ''}. \n"

    return prompt_dict
    
def get_connection_profile_for_prompt(user_id: str, connection_id: str) -> Dict:
    """
    Retrieves the connection profile for prompt generation.

    Args:
        user_id (str): The ID of the user associated with the connection.
        connection_id (str): The ID of the connection whose profile is to be fetched.

    Returns:
        Dict: A dictionary representation of the connection's profile.
    """
    connection_profile = get_connection_profile(user_id, connection_id)
    if not connection_profile:
        raise ValueError(f"Connection with ID {connection_id} not found for user {user_id}")

    prompt_dict = {}
    prompt_dict["name"] = f"    -Connection Name: {connection_profile.connection_name if connection_profile.connection_name else ''}, \n"
    prompt_dict["age"] = f" -Connection Age: {connection_profile.connection_age if connection_profile.connection_age else 'unknown'}, \n"

    prompt_dict["connection_context_block"] = f"    -Personal Info about Connection {connection_profile.connection_name if connection_profile.connection_name else ''}: {connection_profile.connection_context_block if connection_profile.connection_context_block else ''}, \n"
    
    try:
        personality_traits = []
        if connection_profile.personality_traits:
            for trait_dict in connection_profile.personality_traits:
                if isinstance(trait_dict, dict):
                    for k, v in trait_dict.items():
                        if isinstance(v, (int, float)):
                            v_str = f"{v:.2f}"
                        else:
                            v_str = str(v)
                        personality_traits.append(f"{k}: {v_str}")

        prompt_dict['personality_traits'] = (f" -Connection Personality Traits: {', '.join(personality_traits) if personality_traits else 'unknown'}, \n")
        

            
        if connection_profile.connection_profile_text and connection_profile.connection_profile_text != "":
            text = connection_profile.connection_profile_text
            if isinstance(text, list):
                joined_text = ', '.join(text)
            elif isinstance(text, str):
                joined_text = text
            else:
                joined_text = ''
            prompt_dict["connection_profile_text"] = f" -Connection Profile Text: {joined_text}. \n"

        return prompt_dict
    except Exception as e:
        logger.error(f"Error processing connection profile in get_connection_profile_for_prompt: {e}")
        raise ValueError(f"Error processing connection profile for user {user_id}, connection {connection_id}: {e}")

def merge_spurs(original_spurs: list, regenerated_spurs: list) -> list:
    """
    Replaces spurs in original_spurs with those in regenerated_spurs that share the same variant.

    Args:
        original_spurs (list of Spur): The full list of originally generated spurs.
        regenerated_spurs (list of Spur): The newly generated spurs that failed filtering and were regenerated.

    Returns:
        list of Spur: A combined list where spurs in regenerated_spurs replace matching variants in original_spurs.
    """
    regenerated_by_variant = {spur.variant: spur for spur in regenerated_spurs}
    merged_spurs = []

    for spur in original_spurs:
        if spur.variant in regenerated_by_variant:
            merged_spurs.append(regenerated_by_variant[spur.variant])
        else:
            merged_spurs.append(spur)

    return merged_spurs

def generate_spurs(
    user_id: str,
    connection_id: Optional[str],
    conversation_id: Optional[str],
    situation: Optional[str],
    topic: Optional[str],
    selected_spurs: Optional[list[str]] = None,
    conversation_messages: Optional[List[Dict]] = None,
    images: Optional[List[Dict]] = None,  # New parameter for images
) -> list:
    """
    Generates spur responses based on the provided conversation context and profiles.

    Args:
        user_id (str): User ID.
        connection_id (str): Connection ID of connection associated with conversation.
        conversation_id (str): Conversation ID.
        situation (str): A description of the conversation's context.
        topic (str): A topic associated with the conversation.
        selected_spurs (list[str], optional): List of spur variants to generate/regenerate.
        conversation_messages (list[dict], optional): List of conversation messages.
        images (list[dict], optional): List of images with 'data' (raw bytes of image), 'filename', and 'mime_type'.

    Returns:
        List of generated Spur objects.
    """
    user = get_user(user_id)
    if not user:
        raise ValueError(f"User with ID {user_id} not found")
    user_profile_dict = user.to_dict()
    if not selected_spurs:
        selected_spurs = user_profile_dict['selected_spurs']
    
    connection_profile = None
    if connection_id and connection_id != get_null_connection_id(user_id):
        connection_profile = get_connection_profile(user_id, connection_id)
    else:
        active_connection_id = get_active_connection_firestore(user_id)
        if active_connection_id and active_connection_id != get_null_connection_id(user_id):
            connection_profile = get_connection_profile(user_id, active_connection_id)

    # Initialize context_block first
    context_block = "*** USER PROFILE CONTEXT:\n"
    user_prompt_profile = get_user_profile_for_prompt(user_id)
    context_block += "\n".join(user_prompt_profile.values()) + "\n"
    
    if connection_profile and connection_id and connection_id != get_null_connection_id(user_id):
        context_block += "*** CONNECTION PROFILE CONTEXT: \n"
        connection_prompt_profile = get_connection_profile_for_prompt(user_id, connection_id)
        context_block += "\n".join(connection_prompt_profile.values()) + "\n"

    tone = None
    if conversation_messages and len(conversation_messages) > 0:
        tone_info = {}
        context_block += "\n*** USER-PROVIDED CONVERSATION: \n"
        if not conversation_id:
            conversation_id = generate_conversation_id(user_id)
        i = 1
        context_block += "\n    *** Conversation Messages: \n"
        for msg in conversation_messages:
            context_block += f"     - Message #{i} \n"
            context_block += f"         -{msg.get('sender', '')}: {msg.get('text', '')}\n"
            i += 1
        tone_info = infer_tone(conversation_messages[-1].get("text", ""))
        if classify_confidence(tone_info["confidence"]) == "high":
            tone = tone_info["tone"]
            context_block += f"\n   *** Inferred Tone:  {tone}\n"
        if not situation or situation == "":
            situation_info = infer_situation(conversation_messages)
            if classify_confidence(situation_info["confidence"]) == "high":
                situation = situation_info["situation"]
                context_block += f" *** Situation:  {situation}\n"

    if (situation or topic) and (situation != "" or topic != ""):
        context_block += "\n*** USER-PROVIDED CONVERSATION CONTEXT (overrides): \n"
        if situation and situation != "":
            context_block += f" -Situation:  {situation}\n"
        if topic and topic != "":
            context_block += f" -Topic:  {topic}\n\n"
    
        # Process images if provided
    image_analysis = []
    if images and len(images) > 0:
        logger.info(f"Processing {len(images)} images for context analysis")
        
        # Analyze images for conversation and profile context
        image_analysis = analyze_convo_for_context(images)
        
        if image_analysis:
            context_block += "\n*** CONTEXT FOR CONVERSATION SCREENSHOTS (images): \n"
            for context_dict in image_analysis:
                if isinstance(context_dict, dict):
                    for k, v in context_dict.items():
                        if isinstance(v, (int, float)):
                            v_str = f"{v:.2f}"
                        else:
                            v_str = str(v)
                        context_block += f" - {k}: {v_str}"

    context_block += f"\n*** INSTRUCTIONS: Please generate a set of SPURs suggested for User to say to Connection. You should suggest SPURs based on the"
    
    if (conversation_messages and len(conversation_messages) > 0) or (images and len(images) > 0):
        context_block += " Conversation provided. Your fundamental goal here is to keep the conversation engaging and relevant. Your suggestions should consider the"
    
    context_block += " context, including the User Profile Context"
    
    if connection_profile and connection_id and connection_id != get_null_connection_id(user_id):
        context_block += " and the Connection Profile Context"

    if (conversation_messages and len(conversation_messages) > 0) or (images and len(images) > 0):
        context_block += ", but only as that information fits into and/or enrichs the Conversation"
    context_block += ". "
    
    if situation or topic or tone or (image_analysis and len(image_analysis) > 0):
        context_block += "You should consider the "
    if (situation and situation != "") or (image_analysis[0].get('situation') and image_analysis[0].get('confidence_score') != 0):
        context_block += "situation"
    if (topic and topic != ""):
        if context_block.endswith("situation"):
            context_block += " and "
        context_block += "topic"
    if (tone and tone != "") or (image_analysis[1].get('tone') and image_analysis[1].get('confidence_score') != 0):
        if context_block.endswith("situation") or context_block.endswith("topic"):
            context_block += " and "
        context_block += "tone"
    if (images and len(images) > 0) or (conversation_messages and len(conversation_messages) > 0):
        context_block += " of the Conversation"
    
    context_block += " to inform your suggestions. \n"
    context_block += "You should suggest only one Spur for only these Spur variants: \n"
    
    user_prompt = build_prompt(selected_spurs or [], context_block)

    fallback_prompt_suffix = (
        "\nKeep all outputs safe, short, and friendly.\n"
    )

    openai_client = get_openai_client()
    system_prompt = get_system_prompt()
    
    image_parts = []
    for image_data in images or []:
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
        logger.error("No valid images to process (gpt_service.py:generate_spurs).")
        return []
    
    if not openai_client:
        logger.error("OpenAI client not initialized. Cannot generate spurs. Error at gpt_service.py:generate_spurs")
        return []
    
    for attempt in range(3):  # 1 initial + 2 retries
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
                max_tokens=4000,
                temperature=1.1 if attempt == 0 else 0.75,
                )
            content = (response.choices[0].message.content or "") if response.choices else ""
            
            # Extract JSON from response
            json_parsed_content = extract_json_block(content)

            gpt_parsed_filtered_output = parse_gpt_output(
                json_parsed_content, 
                user_profile_dict, 
                connection_profile.to_dict() if connection_profile else {}
            )
            validated_output = validate_and_normalize_output(gpt_parsed_filtered_output)
            
            spur_objects = []
            variant_keys = current_app.config.get('SPUR_VARIANT_ID_KEYS', {})
            
            if user_profile_dict.get("user_id"):
                user_id = user_profile_dict["user_id"]           
            else:
                user_id = ""

            for variant, _id_key in variant_keys.items():
                spur_text: str = validated_output.get(variant, "")
                if spur_text:
                    spur_objects.append(
                        Spur(
                            user_id=user_profile_dict.get("user_id", ""), 
                            spur_id=generate_spur_id(user_id), 
                            conversation_id=conversation_id or "",
                            connection_id=ConnectionProfile.get_attr_as_str(connection_profile, "connection_id") if connection_profile else "",
                            situation=situation or "",
                            topic=topic or "",
                            variant=variant or "",
                            tone=tone or "",
                            text=spur_text or "",
                            created_at=datetime.now(timezone.utc),
                        )
                    )
            if spur_objects:
                return spur_objects

        except openai.APIError as e:
            logger.error(f"[Attempt {attempt+1}] OpenAI API error during GPT generation for user {user_id}: {e}")
            if attempt == 2:
                 logger.error(f"Final GPT attempt failed for user {user_id} due to API error.", exc_info=True)
        except Exception as e:
            logger.error(f"[Attempt {attempt+1}] GPT generation failed for user {user_id} — Error: {e}", exc_info=True)
            if attempt == 2:
                logger.error(f"Final GPT attempt failed for user {user_id} — returning fallback.")
    
    logger.error(f"All GPT generation attempts failed for user {user_id}.")
    return []

def get_spurs_for_output(
    user_id: str, 
    conversation_id: str, 
    connection_id: str, 
    situation: str, 
    topic: str,
    conversation_messages: Optional[List[Dict]] = None,
    images: Optional[List[Dict]] = None,  # New parameter
) -> list:
    """
    Gets spurs that are formatted and content-filtered to send to the frontend. 
    Iterative while loop structure regenerates spurs that fail content filtering.
    
    Args:
        user_id (str): User ID.
        conversation_id (str): Conversation ID.
        connection_id (str): Connection ID.
        situation (str): Situation context.
        topic (str): Topic of conversation.
        conversation_messages (list[dict], optional): List of conversation messages.
        images (list[dict], optional): List of images with base64 data.
    
    Returns:
        list: List of Spur objects ready for output.
    """ 
    user_profile = get_user(user_id=user_id)
    if not user_profile:
        raise ValueError(f"User with ID {user_id} not found")
    selected_spurs_from_profile = user_profile.to_dict().get("selected_spurs", [])

    # Initial generation
    spurs = generate_spurs(
        user_id, 
        connection_id, 
        conversation_id, 
        situation, 
        topic, 
        selected_spurs_from_profile,
        conversation_messages=conversation_messages,
        images=images  # Pass images through
    )

    counter = 0
    max_iterations = 3 

    # Iterative regeneration for spurs that fail validation/filtering
    spurs_needing_regeneration = spurs_to_regenerate(spurs)

    while spurs_needing_regeneration and counter < max_iterations:
        counter += 1
        logger.error(f"LOG.INFO: Regeneration attempt {counter} for user {user_id}, variants: {spurs_needing_regeneration}")
        
        fixed_spurs = generate_spurs(
            user_id, 
            connection_id, 
            conversation_id, 
            situation, 
            topic, 
            spurs_needing_regeneration,
            conversation_messages=conversation_messages,
            images=images  # Pass images for regeneration too
        )
        spurs = merge_spurs(spurs, fixed_spurs)
        spurs_needing_regeneration = spurs_to_regenerate(spurs)

    if counter >= max_iterations and spurs_needing_regeneration:
        logger.error(f"Max regeneration attempts reached for user {user_id}. Some spurs may not meet quality standards.")

    return spurs