from class_defs.profile_def import ConnectionProfile
from dataclasses import fields
from flask import current_app, json
import base64
import json
from typing import List, Dict, Optional, Any
from openai.types.chat import ChatCompletionMessageParam
from infrastructure.logger import get_logger
from infrastructure.clients import get_firestore_db, get_openai_client
from infrastructure.id_generator import generate_connection_id, get_null_connection_id
from utils.prompt_template import get_profile_text_system_prompt, get_profile_text_user_prompt
from utils.usage_tracker import track_openai_usage, track_openai_usage_manual, estimate_tokens_from_messages
from utils.trait_manager import downscale_image_from_bytes, extract_json_block


logger = get_logger(__name__)

def _join_ocr_subwords(subwords: List[str]) -> str:
    """Joins OCR subwords into a coherent string, handling spaces appropriately."""
    no_space_before = {".", ",", "!", "?", ":", ";", ")", "]", "}", "%"}
    no_space_after = {"(", "[", "{", "$", "“", '"', "‘"}

    result = ""
    for i, subword in enumerate(subwords):
        if i == 0:
            result += subword
        else:
            prev = subwords[i - 1]
            if subword in no_space_before:
                result += subword
            elif prev in no_space_after:
                result += subword
            else:
                result += " " + subword
    return result

def get_top_n_traits(traits_with_scores: List[Dict[str, Any]], n: int = 5) -> List[Dict[str, Any]]:
    """
    Sorts traits by confidence, deduplicates by trait name keeping the highest confidence score,
    and returns the top N traits.
    """
    if not traits_with_scores:
        return []

    # Use a dictionary to track the trait with the highest confidence score, ensuring uniqueness.
    unique_traits = {}
    for trait in traits_with_scores:
        # Ensure the trait dictionary has the expected 'trait' key.
        trait_name = trait.get("trait")
        if not trait_name:
            continue
        
        # Normalize the trait name to handle minor variations like whitespace or casing.
        normalized_name = trait_name.strip().lower()
        current_confidence = trait.get("confidence", 0.0)
        
        # If the trait is new, or if this instance has a higher confidence, store it.
        if (normalized_name not in unique_traits or 
                current_confidence > unique_traits[normalized_name].get("confidence", 0.0)):
            unique_traits[normalized_name] = trait

    # Convert the dictionary of unique traits back to a list.
    deduplicated_list = list(unique_traits.values())
    
    # Finally, sort the unique traits by confidence and return the top N.
    sorted_traits = sorted(deduplicated_list, key=lambda x: x.get("confidence", 0.0), reverse=True)
    return sorted_traits[:n]

def create_connection_profile(
    data: Dict, 
    # images: Optional[List[bytes]] = None, # This was for the old trait system from generic images
    # links: Optional[List[str]] = None,    # This is being removed
    connection_profile_text: Optional[List[str]] = None,
    personality_traits_list: Optional[List[Dict[str, Any]]] = None, 
    connection_profile_pic_url: str = "") -> Dict:
    
    
    user_id = data['user_id']
    if not user_id:
        logger.error("Error: Cannot create connection profile - missing user ID in g.user")
        return {"error": "Authentication error: User ID not available."}


    connection_id = generate_connection_id(user_id)
    data['connection_id'] = connection_id

    profile = ConnectionProfile.from_dict(data) # Initial profile from form data
    profile_data_to_save = profile.to_dict()

    # OCR'd text content
    if connection_profile_text is not None and isinstance(connection_profile_text, list):
        # Join subwords into coherent strings
        joined_texts = _join_ocr_subwords(connection_profile_text) 
        profile_data_to_save["connection_profile_text"] = joined_texts

    # Personality traits from profile pictures (using OpenAI Vision)

            
    profile_data_to_save["personality_traits"] = get_top_n_traits(personality_traits_list or [], 5)

    profile_data_to_save["connection_context_block"] = data.get("connection_context_block", None)
    profile_data_to_save["connection_profile_pic_url"] = connection_profile_pic_url if connection_profile_pic_url else ""
    profile_data_to_save["connection_name"] = data.get("connection_name", None) 
    profile_data_to_save["connection_age"] = data.get("connection_age", None)

    try:
       db = get_firestore_db()
       db.collection("users").document(user_id).collection("connections").document(connection_id).set(profile_data_to_save)
       logger.error(f"LOG.INFO: Connection profile {connection_id} created for user {user_id}.")
       
       response_data = profile_data_to_save.copy()
       if response_data.get('personality_traits'):
           response_data['personality_traits'] = [t.copy() for t in response_data['personality_traits']]
           for trait in response_data['personality_traits']:
               if 'confidence' in trait and isinstance(trait['confidence'], float):
                   trait['confidence'] = f"{trait['confidence']:.2f}"

       return response_data

    except Exception as e:
        logger.error("Error creating connection profile in Firestore for user %s: %s", user_id, e, exc_info=True)
        return {"error": f"Cannot create connection profile due to storage error: {str(e)}"}



def format_connection_profile(connection_profile: ConnectionProfile) -> str:
    profile_dict = connection_profile.to_dict() 
    connection_id_val = profile_dict.get('connection_id', 'N/A') 
    lines = [f"connection_id: {connection_id_val}"]

    for field_info in fields(ConnectionProfile):
        key = field_info.name
        value = profile_dict.get(key) 

        if key == "user_id" or value is None: 
            continue
        if key == "connection_id" and value is None: 
            continue

        display_key = key.replace('_', ' ')
        if isinstance(value, list):
            if value: 
                if key == "personality_traits":
                    display_key = "Personality Traits"
                    lines.append(f"{display_key}:")
                    for trait_item in value: # Value is now List[Dict[str, Any]]
                        trait_name = trait_item.get('trait', 'Unknown trait')
                        confidence = trait_item.get('confidence', 'N/A')
                        lines.append(f"  - {trait_name} (Confidence: {confidence:.2f})")
                    continue # Skip default list formatting for this key
                elif key == "connection_profile_text": display_key = "Profile Content"
                # profile_image_urls was removed
                
                if key == "connection_profile_text": # specific formatting for these lists
                    lines.append(f"{display_key}:")
                    for item in value: lines.append(f"  - \"{item}\"")
                elif key not in ["personality_traits"]: # Avoid re-printing personality_traits
                    lines.append(f"{display_key}: {', '.join(map(str, value))}")
        else:
            lines.append(f"{display_key}: {value}")
    return "\n".join(lines)

def save_connection_profile(connection_profile: ConnectionProfile) -> dict:
    connection_profile_dict = connection_profile.to_dict() 
    user_id = connection_profile_dict.get("user_id")
    connection_id = connection_profile_dict.get("connection_id")
    null_suffix = current_app.config.get('NULL_CONNECTION_ID_SUFFIX', '_null')

    if not user_id or not connection_id or (isinstance(connection_id, str) and connection_id.endswith(null_suffix)):
        logger.error(f"Cannot save connection profile. Invalid IDs. User: '{user_id}', Conn: '{connection_id}'")
        return {"error": "Cannot save connection profile: Missing or invalid user ID or connection ID."}

    try:
        db = get_firestore_db()  # Ensure Firestore client is initialized
        db.collection("users").document(user_id).collection("connections").document(connection_id).set(connection_profile_dict)
        logger.error(f"LOG.INFO: Connection profile {connection_id} for user {user_id} saved successfully.")
        return {
            "success": "connection profile successfully saved"
        }

    except Exception as e:
        err_point = __package__ or "connection_service"
        logger.error("[%s] Error saving conn profile %s for user %s: %s", err_point, connection_id, user_id, e, exc_info=True)
        return {'error': f"[{err_point}] - Error saving connection profile: {str(e)}"}

def get_user_connections(user_id:str) -> list[ConnectionProfile]:
    if not user_id:
        logger.error("Cannot get connections: missing user ID")
        return [] 

    try:
        db = get_firestore_db()  
        connections_ref = db.collection("users").document(user_id).collection("connections")
        connections_stream = connections_ref.stream()
        connection_list = []
        for connection_doc in connections_stream:
            if connection_doc.exists:
                connection_data = connection_doc.to_dict()
                complete_data = {}
                for f_info in fields(ConnectionProfile):
                    if f_info.name in connection_data:
                        complete_data[f_info.name] = connection_data[f_info.name]
                    elif callable(f_info.default_factory): # Use default_factory if field missing
                        complete_data[f_info.name] = f_info.default_factory()
                    # elif f_info.default is not dataclasses.MISSING:
                    #     complete_data[f_info.name] = f_info.default
                    else: # Field not in data and no default, from_dict might handle or assign None
                         complete_data[f_info.name] = None # Explicitly None if not required and no default
                
                profile = ConnectionProfile.from_dict(complete_data)
                connection_list.append(profile)
        return connection_list
    except Exception as e:
        err_point = __package__ or "connection_service"
        logger.error("[%s] Error getting connections for user %s: %s", err_point, user_id, e, exc_info=True)
        return [] 

def set_active_connection_firestore(user_id: str, connection_id: Optional[str]) -> dict: # connection_id can be None
    if not user_id:
        logger.error("Cannot set active connection: missing user ID")
        return {"error": "Missing user ID for set_active_connection"} 
    
    effective_connection_id = connection_id if connection_id is not None else get_null_connection_id(user_id)
    if effective_connection_id == None or effective_connection_id == "":
        effective_connection_id = "null_connection_id_p"
    
    try:
        db = get_firestore_db()  # Ensure Firestore client is initialized
        db.collection("users").document(user_id).collection("settings").document("active_connection").set({
            "connection_id": effective_connection_id
        })
        logger.error(f"LOG.INFO: Active connection set to '{effective_connection_id}' for user '{user_id}'.")
        return {"success": "active connection set", "connection_id": effective_connection_id}
    except Exception as e:
        logger.error(f"Error setting active conn for user {user_id} to {effective_connection_id}: {e}", exc_info=True)
        return {"error": f"Cannot set active connection: {str(e)}"}

def get_active_connection_firestore(user_id: str) -> str:
    if not user_id:
        logger.error("Cannot get active connection: missing user ID")
        return get_null_connection_id("UNKNOWN_USER_ACTIVE_CONN_ERROR") 

    try:
        db = get_firestore_db()  # Ensure Firestore client is initialized
        doc_ref = db.collection("users").document(user_id).collection("settings").document("active_connection")
        doc = doc_ref.get()
        if doc.exists:
            active_cid = doc.to_dict().get("connection_id")
            logger.error(f"Retrieved active connection_id '{active_cid}' for user '{user_id}'.")
            return active_cid if active_cid is not None else get_null_connection_id(user_id) # Ensure null if db has None
        else:
            logger.error(f"No active conn for user '{user_id}'. Setting/returning null.")
            active_connection_id = get_null_connection_id(user_id)
            set_active_connection_firestore(user_id, active_connection_id) 
            return active_connection_id
    except Exception as e:
        err_point = __package__ or "connection_service"
        logger.error("[%s] Error getting active conn for user %s: %s", err_point, user_id, e, exc_info=True)
        return get_null_connection_id(user_id) 

def clear_active_connection_firestore(user_id: str) -> dict:
    if not user_id:
        logger.error("Cannot clear active connection: missing user ID")
        return {"error": "Missing user ID for clear_active_connection"}
    
    try:
        null_connection_id = get_null_connection_id(user_id)
        result = set_active_connection_firestore(user_id, null_connection_id) # Set to null
        if "error" in result: 
            return {"error": f"Failed to clear active connection by setting to null: {result['error']}"}
        logger.error(f"LOG.INFO: Active connection cleared (set to '{null_connection_id}') for user '{user_id}'.")
        return {"success": "active connection cleared", "connection_id": null_connection_id}
    except Exception as e:
        err_point = __package__ or "connection_service"
        logger.error("[%s] Error clearing active conn for user %s: %s", err_point, user_id, e, exc_info=True)
        return {'error': f"Error clearing active connection: {str(e)}"}

def get_connection_profile(user_id: str, connection_id: str) -> Optional[ConnectionProfile]:
    null_connection_id = current_app.config.get('NULL_CONNECTION_ID', 'null_connection_id_p')
    if not user_id or not connection_id or (isinstance(connection_id, str) and connection_id.endswith(null_connection_id)):
        logger.error(f"Attempt to get profile with invalid IDs. User:'{user_id}', Conn:'{connection_id}'")
        return None 

    try:
        db = get_firestore_db()  # Ensure Firestore client is initialized
        doc_ref = db.collection("users").document(user_id).collection("connections").document(connection_id)
        doc = doc_ref.get()
        if doc.exists:
            connection_data = doc.to_dict()
            complete_data = {} # Ensure all fields for ConnectionProfile, using defaults if missing
            for f_info in fields(ConnectionProfile):
                if f_info.name in connection_data:
                    complete_data[f_info.name] = connection_data[f_info.name]
                elif callable(f_info.default_factory):
                    complete_data[f_info.name] = f_info.default_factory()
                # elif f_info.default is not dataclasses.MISSING:
                #    complete_data[f_info.name] = f_info.default
                else:
                    complete_data[f_info.name] = None # Or handle as ConnectionProfile.from_dict does

            profile = ConnectionProfile.from_dict(complete_data)
            return profile
        else:
            logger.error(f"Conn profile not found: user '{user_id}', conn '{connection_id}'.")
            return None
    except Exception as e:
        logger.error("[%s] Error getting conn profile (user %s, conn %s): %s", "conn_service", user_id, connection_id, e, exc_info=True)
        raise ConnectionError(f"Could not retrieve connection profile: {str(e)}") from e

def update_connection_profile(
    user_id: str, 
    connection_id: str, 
    connection_name: Optional[str] = None,
    connection_age: Optional[int] = None,
    data: Optional[str] = None, 
    connection_profile_text: Optional[List[str]] = None, 
    updated_personality_traits: Optional[List[Dict[str, Any]]] = None,
    updated_profile_pic_url: Optional[str] = None 
) -> Dict:
    null_connection_id = current_app.config.get('NULL_CONNECTION_ID', 'null_connection_id_p')
    if not user_id or not connection_id or (isinstance(connection_id, str) and connection_id.endswith(null_connection_id)):
        logger.error("Cannot update conn profile: invalid IDs. User:'%s', Conn:'%s'", user_id, connection_id)
        return {"error": "Cannot update connection profile: Missing or invalid user ID or connection ID."}

    try:
        db = get_firestore_db()  # Ensure Firestore client is initialized
        doc_ref = db.collection("users").document(user_id).collection("connections").document(connection_id)
        current_profile_doc = doc_ref.get()
        if not current_profile_doc.exists:
            logger.error(f"Conn profile {connection_id} for user {user_id} not found. Cannot update.")
            return {"error": "Connection profile not found, cannot update."}
        
        current_profile_data = current_profile_doc.to_dict()
        update_payload = {} # Build payload with only the fields to change
        
        if connection_name is not None and connection_name != current_profile_data.get("connection_name"):
            update_payload["connection_name"] = connection_name
        if connection_age is not None and connection_age != current_profile_data.get("connection_age"):
            update_payload["connection_age"] = connection_age

        # Update basic form data fields
        if data is not None:
            update_payload["connection_context_block"] = data
        elif data == "":
            update_payload["connection_context_block"] = None # Explicitly set to None if empty string

        # Update OCR'd text content if provided (None means no change, [] means clear)
        if connection_profile_text is not None and isinstance(connection_profile_text, list):
            joined_texts = _join_ocr_subwords(connection_profile_text)
            update_payload["connection_profile_text"] = joined_texts
        
        # Update personality traits if provided
        if updated_personality_traits is not None:
            combined_traits = current_profile_data.get("personality_traits", []).copy()  # Make a copy
            combined_traits.extend(updated_personality_traits)  # Use extend, not append!
            
            if combined_traits and len(combined_traits) > 5:
                # Keep only the top 5 by confidence
                update_payload["personality_traits"] = get_top_n_traits(combined_traits, 5)
            else:
                update_payload["personality_traits"] = combined_traits
        
        if updated_profile_pic_url is not None and updated_profile_pic_url.startswith("http"):
            if current_profile_data.get("connection_profile_pic_url") != updated_profile_pic_url:
                update_payload["connection_profile_pic_url"] = updated_profile_pic_url

        if not update_payload:
            logger.error(f"LOG.INFO: No effective update data provided for conn {connection_id}, user {user_id}.")
            return {"warning": "no effective update data provided for connection profile", "connection_id": connection_id}

        doc_ref.update(update_payload)
        logger.error(f"LOG.INFO: Conn profile {connection_id} for user {user_id} updated with keys: {list(update_payload.keys())}.")
        return {"success": "connection profile updated", "connection_id": connection_id}
    except Exception as e:
        logger.error(f"Error updating conn profile {connection_id} for user {user_id}: {e}", exc_info=True)
        return {"error": f"Cannot update connection profile: {str(e)}"}


def delete_connection_profile(user_id: str, connection_id:str) -> dict:
    null_connection_id = current_app.config.get('NULL_CONNECTION_ID', 'null_connection_id_p')
    if not user_id or not connection_id or (isinstance(connection_id, str) and connection_id.endswith(null_connection_id)):
        logger.error("Cannot delete conn profile: invalid IDs. User:'%s', Conn:'%s'", user_id, connection_id)
        return {"error": "Cannot delete connection profile: Missing or invalid user ID or connection ID."}
    
    try:
        db = get_firestore_db()  # Ensure Firestore client is initialized
        doc_ref = db.collection("users").document(user_id).collection("connections").document(connection_id)
        if not doc_ref.get().exists:
            logger.error(f"Delete attempt: non-existent conn profile {connection_id} for user {user_id}.")
            return {"warning": "connection profile not found, no action taken", "connection_id": connection_id}

        doc_ref.delete()
        logger.error(f"LOG.INFO: Conn profile {connection_id} for user {user_id} deleted successfully.")
        # TODO: Delete associated images off firebase storage. 
        return {"success": "connection profile deleted", "connection_id": connection_id}
    except Exception as e:
        logger.error(f"Error deleting conn profile {connection_id} for user {user_id}: {e}", exc_info=True)
        return {"error": f"Cannot delete connection profile: {str(e)}"}
    
@track_openai_usage('add_connection')
def get_profile_text(
    user_id: str,
    img_bytes: bytes,
) -> Dict:
    """
    Takes an image byte array of a profile image and uses GPT-4o to extract profile text.

    Args:
        user_id (str): User ID.

        img_bytes (bytes, optional): Raw bytes of the profile image.

    Returns:
        Dictionary of profile text.
    """
    openai_client = get_openai_client()
    system_prompt = get_profile_text_system_prompt()
    user_prompt = get_profile_text_user_prompt()

    if not img_bytes:
        logger.error("Skipping profile image due to missing bytes.")
        return {"error": "Missing profile image data."}

    resized_image_bytes = downscale_image_from_bytes(img_bytes, max_dim=1024)
    base64_image = base64.b64encode(resized_image_bytes).decode("utf-8")
    image_parts = [{
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
            }
        }]

    if not image_parts:
        logger.error("No valid images to process (connection_service:get_profile_text).")


    if not openai_client:
        logger.error("OpenAI client not initialized. Cannot generate spurs. Error at gpt_service.py:generate_spurs")
        return {"error": "OpenAI client not initialized."}

    user_content = [
        {"type": "text", "text": user_prompt}
    ]
    if image_parts and len(image_parts) > 0:
        user_content.append({"type": "text", "text": "The following image show the Profile from which you are to extract and label profile data: "})
        user_content.extend(image_parts)

    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

    try:
        
        # Estimate tokens for manual tracking
        estimated_prompt_tokens = estimate_tokens_from_messages(messages)
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=8000,
            temperature=0.45,
            )
        
        # Manual usage tracking since decorator might not capture all details
        if hasattr(response, 'usage') and response.usage:
            track_openai_usage_manual(
                user_id=user_id,
                model="gpt-4o",
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                feature="add_connection"
            )
        else:
            # Fallback to estimation
            estimated_completion_tokens = 1000  # Conservative estimate for spur generation
            track_openai_usage_manual(
                user_id=user_id,
                model="gpt-4o",
                prompt_tokens=estimated_prompt_tokens,
                completion_tokens=estimated_completion_tokens,
                feature="add_connection"
            )
        
        content = (response.choices[0].message.content or "") if response.choices else ""
        
        json_parsed_content = {}
        extracted_profile_dict = {}
        
        if (not content or ("I can't assist with that" in content) or ("I can't help with that" in content) or ("unable to process your request" in content)):
            logger.error(f"GPT response for user {user_id} was empty or unhelpful: {content}")
            return {"error": "GPT response was empty or unhelpful. Please try again later."}

        else:
            json_parsed_content = json.loads(extract_json_block(content))
            
            if isinstance(json_parsed_content, Dict):
                logger.error("LOG.INFO: Extracted JSON content is a dictionary.")
                if 'name' in json_parsed_content:
                    extracted_profile_dict['connection_name'] = json_parsed_content['name']
                if 'age' in json_parsed_content:
                    extracted_profile_dict['connection_age'] = json_parsed_content['age']
            skip_keys = {"name", "age"}
            extracted_profile_dict['connection_context_block'] += "\n".join(f" • {k.lower()}: {v.lower()}. " for k, v in json_parsed_content.items() if k not in skip_keys)

        if extracted_profile_dict and len(extracted_profile_dict) > 0:
            return extracted_profile_dict
        else:
            return {"error": "No profile data could be extracted from the image."}
        
    except Exception as e:
        logger.error(f"Profile Data Extraction Failed — Error: {e}", exc_info=True)
        return {"error": f"Profile Data Extraction Failed: {str(e)}"}

@track_openai_usage('topic_matching')
def trending_topics_matching_connection_interests(user_id: str, connection_id: str) -> List[str]:
    """
    Returns a list of trending topics that are likely of interest to the connection
    based on their profile information.
    
    Args:
        user_id: The ID of the user
        connection_id: The ID of the connection
        
    Returns:
        List of trending topic strings that match the connection's interests
    """
    try:
        # Get connection profile
        connection_profile = get_connection_profile(user_id, connection_id)
        if not connection_profile:
            logger.error(f"Connection profile not found for user {user_id}, connection {connection_id}")
            return []
        
        # Get all trending topics from Firestore (similar to get_random_trending_topic)
        db = get_firestore_db()
        doc = db.collection("trending_topics").document("weekly_pool").get()
        
        if not doc.exists:
            logger.error("No trending topics found in Firestore")
            return []
        
        topics_data = doc.to_dict().get("topics", [])
        if not topics_data:
            logger.error("No topics in trending topics pool")
            return []
        
        # Extract just the topic strings
        trending_topics = [topic.get("topic", "") for topic in topics_data if topic.get("topic")]
        
        if not trending_topics:
            logger.error("No valid trending topics found")
            return []
        
        # Build context about the connection
        connection_context = ""
        
        # Add connection context block if available
        if connection_profile.connection_context_block:
            connection_context += f"Connection Context: {connection_profile.connection_context_block}\n\n"
        
        # Add profile text if available
        if connection_profile.connection_profile_text:
            if isinstance(connection_profile.connection_profile_text, list):
                profile_text = " ".join(connection_profile.connection_profile_text)
            else:
                profile_text = str(connection_profile.connection_profile_text)
            connection_context += f"Profile Information: {profile_text}\n\n"
        
        # Add personality traits if available
        if connection_profile.personality_traits:
            traits_str = ", ".join([trait.get("trait", "") for trait in connection_profile.personality_traits if trait.get("trait")])
            if traits_str:
                connection_context += f"Personality Traits: {traits_str}\n\n"
        
        # If no context is available, return empty list
        if not connection_context.strip():
            logger.error(f"No profile information available for connection {connection_id}")
            return []
        
        # Prepare the prompt for OpenAI
        system_prompt = """You are an expert at matching trending topics to people's interests based on their profile information. 
Your task is to analyze a person's profile and identify which trending topics from a provided list would likely interest them.

Consider all aspects of their profile including:
- Their stated interests and hobbies
- Their personality traits
- Their profession or field of study
- Any activities or preferences mentioned
- Context clues about their lifestyle

Be selective - only return topics that have a clear connection to their profile. It's better to return fewer highly relevant topics than many loosely related ones.

Your response must be a JSON array of strings containing ONLY the trending topics that match (exactly as they appear in the provided list). 
For example: ["NBA Finals", "Taylor Swift tour", "New iPhone release"]

If no topics clearly match their interests, return an empty array: []"""

        user_prompt = f"""Based on the following profile information, which of these trending topics would likely interest this person?

{connection_context}

Trending Topics:
{json.dumps(trending_topics, indent=2)}

Return ONLY a JSON array of the matching topic strings."""

        # Call OpenAI
        openai_client = get_openai_client()
        if not openai_client:
            logger.error("OpenAI client not initialized")
            return []
        
        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Estimate tokens for manual tracking
        estimated_prompt_tokens = estimate_tokens_from_messages(messages)
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=2000,
            temperature=0.4
        )
        
        # Manual usage tracking
        if hasattr(response, 'usage') and response.usage:
            track_openai_usage_manual(
                user_id=user_id,
                model="gpt-4o",
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                feature="topic_matching"
            )
        else:
            # Fallback to estimation
            estimated_completion_tokens = 200
            track_openai_usage_manual(
                user_id=user_id,
                model="gpt-4o",
                prompt_tokens=estimated_prompt_tokens,
                completion_tokens=estimated_completion_tokens,
                feature="topic_matching"
            )
        
        # Parse the response
        content = (response.choices[0].message.content or "").strip()
        
        try:
            # Extract JSON array from response
            matched_topics = json.loads(extract_json_block(content))
            
            if not isinstance(matched_topics, list):
                logger.error(f"OpenAI returned non-list response: {matched_topics}")
                return []
            
            # Validate that returned topics are actually in the trending topics list
            valid_topics = [topic for topic in matched_topics if topic in trending_topics]
            
            if len(valid_topics) != len(matched_topics):
                logger.warning(f"Some returned topics were not in the trending list. Original: {matched_topics}, Valid: {valid_topics}")
            
            return valid_topics
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse OpenAI response for topic matching: {e}, Response: {content}")
            return []
            
    except Exception as e:
        logger.error(f"Error in trending_topics_matching_connection_interests: {e}", exc_info=True)
        return []
