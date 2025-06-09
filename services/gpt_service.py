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
from utils.trait_manager import infer_tone, infer_situation
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
    prompt_dict["name"] = f"User Name: {user.name if user.name else ''}, \n"
    prompt_dict["age"] = f"User Age: {user.age if user.age else 'unknown'}, \n"
    prompt_dict["user_context_block"] = f"Personal Info about User {user.name if user.name else ''}: {user.user_context_block if user.user_context_block else ''}. \n"

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
    prompt_dict["name"] = f"Connection Name: {connection_profile.name if connection_profile.name else ''}, \n"
    prompt_dict["age"] = f"Connection Age: {connection_profile.age if connection_profile.age else 'unknown'}, \n"
    prompt_dict["connection_profile_pic_url"] = f"Connection Profile Pic URL: {connection_profile.connection_profile_pic_url if connection_profile.connection_profile_pic_url else 'unknown'}, \n"
    prompt_dict["connection_context_block"] = f"Personal Info about Connection {connection_profile.name if connection_profile.name else ''}: {connection_profile.connection_context_block if connection_profile.connection_context_block else ''}, \n"

    personality_traits = []
    if connection_profile.personality_traits:
        for trait_dict in connection_profile.personality_traits:
            if isinstance(trait_dict, dict):
                personality_traits.extend(trait_dict.values())

    prompt_dict['personality_traits'] = f"Connection Personality Traits: {', '.join(personality_traits) if personality_traits else 'unknown'}, \n"
    prompt_dict["connection_profile_text"] = f"Connection Profile Text: {', '.join(connection_profile.connection_profile_text) if connection_profile.connection_profile_text else ''}. \n"

    return prompt_dict

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
    connection_id: str,
    conversation_id: str,
    situation: str,
    topic: str,
    selected_spurs: Optional[list[str]] = None,
    conversation_messages: Optional[List[Dict]] = None,  # New parameter
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
        profile_ocr_texts (list[str], optional): List of text excerpts extracted from connection's profile screenshots.
        photo_analysis_data (list[dict], optional): List of analysis results (e.g., traits) from connection's photos.

    Returns:
        List of generated Spur objects.
    """
    user = get_user(user_id)
    if not user:
        raise ValueError(f"User with ID {user_id} not found")
    user_profile_dict = user.to_dict_alt() # Renamed for clarity
    if not selected_spurs:
        selected_spurs = user_profile_dict['selected_spurs']
    
    connection_profile = None
    if connection_id and connection_id != get_null_connection_id():
        connection_profile = get_connection_profile(user_id, connection_id)
    else:
        active_connection_id = get_active_connection_firestore(user_id)
        if active_connection_id and active_connection_id != get_null_connection_id():
            connection_profile = get_connection_profile(user_id, active_connection_id)

    # Initialize context_block first
    context_block = "***User Profile:***\n"
    user_prompt_profile = get_user_profile_for_prompt(user_id) # Create instance for formatting
    context_block += "\n".join(user_prompt_profile.values()) + "\n\n"
    
    if connection_profile and connection_id != get_null_connection_id():
        context_block += "***Connection Profile:***\n"
        connection_prompt_profile = get_connection_profile_for_prompt(user_id, connection_id) # Create instance for formatting
        context_block += "\n".join(connection_prompt_profile.values()) + "\n\n"

    
    if situation and situation != "":
        context_block += f"***Situation:*** {situation}\n\n"
    if topic and topic != "":
        context_block += f"***Topic:*** {topic}\n\n"
    
    tone_info = {}
    tone = ""
    if conversation_messages:
        tone_info = infer_tone(conversation_messages[-1].get("text", ""))
        if classify_confidence(tone_info["confidence"]) == "high":
            tone = tone_info["tone"]
            context_block += f"***Tone:*** {tone}\n\n"
        if not situation or situation == "":  # Infer situation only if not provided
            situation_info = infer_situation(conversation_messages)
            if classify_confidence(situation_info["confidence"]) == "high":
                situation = situation_info["situation"]
                context_block += f"***Situation:*** {situation}\n\n"
        i = 1
        context_block += "\n*** *CONVERSATION* ***\n"
        for msg in conversation_messages:
            context_block += f"* Message #{i} *\n"
            context_block += f"{msg.get('sender', '')}: {msg.get('text', '')}\n"
            i += 1
        context_block += "\n\n"
        context_block += f"NOTE: You should suggest SPURs based on the conversation above. Consider the Situation, Topic, and Tone if they are included. Your suggestions should consider the User Profile and the Connection Profile, and you should tie your suggestions back to the Connection Profile only if it fits into the conversation. Your fundamental goal here is to keep the conversation engaging and relevant.\n\n"

    
    if not conversation_id:
        conversation_id = generate_conversation_id(user_id)

    logger.error(f"Context block for prompt:\n{context_block}")

    prompt = build_prompt(selected_spurs or [], context_block)

    fallback_prompt_suffix = (
        "\nKeep all outputs safe, short, and friendly.\n"
    )
    
    # Fallback response (ensure keys match SPUR_VARIANT_ID_KEYS)
    # This might need to be more dynamic if SPUR_VARIANT_ID_KEYS can change.
    # fallback_response_values = {
    #     key: "We're having trouble generating something right now. Please try your request again."
    #     for key in current_app.config.get('SPUR_VARIANT_ID_KEYS', {}).keys()
    # }


    for attempt in range(3):  # 1 initial + 2 retries
        try:
            current_prompt = prompt + fallback_prompt_suffix if attempt > 0 else prompt
            system_prompt = get_system_prompt()
            openai_client = get_openai_client()
            
            response = openai_client.chat.completions.create(
                model="chatgpt-4o-latest",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": current_prompt}
                ],
                temperature=1.0 if attempt == 0 else 0.75,
            )
            
            ## DEBUG:
            logger.error(f"GPT response: {response}")  # Log the full response for debugging

            raw_output: str = (response.choices[0].message.content or '') if response.choices else ''
            # Pass user_profile_dict to parse_gpt_output
            gpt_parsed_filtered_output = parse_gpt_output(
                raw_output, 
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
                if spur_text: # Ensure spur_text is not empty
                    spur_objects.append(
                        Spur(
                            user_id=user_profile_dict.get("user_id", ""), # from dict
                            spur_id=generate_spur_id(user_id), # from dict
                            conversation_id=conversation_id, # Use derived ID
                            connection_id=ConnectionProfile.get_attr_as_str(connection_profile, "connection_id") if connection_profile else "",
                            situation=situation or "",
                            topic=topic or "",
                            variant=variant or "",
                            tone=tone or "",
                            text=spur_text or "",
                            created_at=datetime.now(timezone.utc),
                        )
                    )
            if spur_objects: # If any spurs were successfully created
                return spur_objects

        except openai.APIError as e:
            logger.warning(f"[Attempt {attempt+1}] OpenAI API error during GPT generation for user {user_id}: {e}")
            if attempt == 2:
                 logger.error(f"Final GPT attempt failed for user {user_id} due to API error.", exc_info=True)
        except Exception as e:
            logger.warning(f"[Attempt {attempt+1}] GPT generation failed for user {user_id} — Error: {e}", exc_info=True)
            if attempt == 2:
                logger.error(f"Final GPT attempt failed for user {user_id} — returning fallback.")
    
    logger.error(f"All GPT generation attempts failed for user {user_id}.")
    # Return an empty list or a list of fallback Spur objects if defined
    # For example, create Spur objects from fallback_response_values if it's structured correctly
    return []

def get_spurs_for_output(user_id: str, conversation_id: str, connection_id: str, situation: str, topic: str,
                         conversation_messages: Optional[List[Dict]] = None,  # New parameter
                         ) -> list:
    """
    Gets spurs that are formatted and content-filtered to send to the frontend. 
    Iterative while loop structure regenerates spurs that fail content filtering.
    """ 
    user_profile = get_user(user_id=user_id)
    if not user_profile:
        raise ValueError(f"User with ID {user_id} not found")
    selected_spurs_from_profile = user_profile.to_dict().get("selected_spurs", []) # Ensure it's a list

    # Initial generation
    spurs = generate_spurs(user_id, connection_id, conversation_id, situation, topic, selected_spurs_from_profile,
                           conversation_messages=conversation_messages) # Pass through

    counter = 0
    max_iterations = 10 # Consider making this configurable

    # Iterative regeneration for spurs that fail validation/filtering
    spurs_needing_regeneration = spurs_to_regenerate(spurs) # This function returns list of variants (strings)

    while spurs_needing_regeneration and counter < max_iterations:
        counter += 1
        logger.info(f"Regeneration attempt {counter} for user {user_id}, variants: {spurs_needing_regeneration}")
        
        fixed_spurs = generate_spurs(user_id, connection_id, conversation_id, situation, topic, spurs_needing_regeneration, # Pass only variants to regenerate
                                     conversation_messages=conversation_messages)
        spurs = merge_spurs(spurs, fixed_spurs)
        spurs_needing_regeneration = spurs_to_regenerate(spurs)

    if counter >= max_iterations and spurs_needing_regeneration:
        logger.warning(f"Max regeneration attempts reached for user {user_id}. Some spurs may not meet quality standards.")

    return spurs