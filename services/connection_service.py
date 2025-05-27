from class_defs.profile_def import ConnectionProfile
from dataclasses import fields
from flask import current_app, g # jsonify removed as it's not typical for service layer
from infrastructure.clients import db
from infrastructure.id_generator import generate_connection_id, get_null_connection_id
from infrastructure.logger import get_logger
from typing import List, Dict, Optional, Any
from utils.trait_manager import (
    infer_personality_traits_from_openai_vision)
from services.storage_service import upload_profile_image # Ensure this path is correct

logger = get_logger(__name__)

def _get_top_n_traits(traits_with_scores: List[Dict[str, Any]], n: int = 5) -> List[Dict[str, Any]]:
    """Sorts traits by confidence and returns the top N unique traits."""
    if not traits_with_scores:
        return []
    
    # Ensure uniqueness by trait name, keeping the highest confidence for duplicates
    unique_traits_map = {}
    for item in traits_with_scores:
        trait_name = item.get("trait")
        confidence = item.get("confidence", 0.0)
        if trait_name:
            if trait_name not in unique_traits_map or confidence > unique_traits_map[trait_name]["confidence"]:
                unique_traits_map[trait_name] = {"trait": trait_name, "confidence": confidence}
    
    sorted_traits = sorted(list(unique_traits_map.values()), key=lambda x: x["confidence"], reverse=True)
    return sorted_traits[:n]

def create_connection_profile(
    data: Dict, 
    # images: Optional[List[bytes]] = None, # This was for the old trait system from generic images
    # links: Optional[List[str]] = None,    # This is being removed
    profile_text_content_list: Optional[List[str]] = None,
    personality_traits_list: Optional[List[Dict[str, Any]]] = None 
) -> Dict:
    user_id = g.user.get('user_id')
    if not user_id:
        logger.error("Error: Cannot create connection profile - missing user ID in g.user")
        return {"error": "Authentication error: User ID not available."}

    if 'user_id' in data and data['user_id'] != user_id:
        logger.warning(f"Attempt to set user_id via form data. Authenticated user_id '{user_id}' will be used.")
    data['user_id'] = user_id

    connection_id = generate_connection_id(user_id)
    data['connection_id'] = connection_id

    profile = ConnectionProfile.from_dict(data) # Initial profile from form data
    profile_data_to_save = profile.to_dict()

    # OCR'd text content
    profile_data_to_save["profile_text_content"] = profile_text_content_list if profile_text_content_list is not None else []

    # Personality traits from profile pictures (using OpenAI Vision)

            
    profile_data_to_save["personality_traits"] = _get_top_n_traits(personality_traits_list, 5)

    profile_data_to_save["context_block"] = profile.context_block if profile.context_block is not None else None

    try:
        db.collection("users").document(user_id).collection("connections").document(connection_id).set(profile_data_to_save)
        logger.info(f"Connection profile {connection_id} created for user {user_id}.")
        saved_profile_object = ConnectionProfile.from_dict(profile_data_to_save)
        return {
            "status": "connection profile created",
            "connection_id": connection_id,
            "connection_profile_summary": format_connection_profile(saved_profile_object)
        }
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

        display_key = key.replace('_', ' ').capitalize()
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
                elif key == "profile_text_content": display_key = "Profile Content"
                # profile_image_urls was removed
                
                if key == "profile_text_content": # specific formatting for these lists
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
        db.collection("users").document(user_id).collection("connections").document(connection_id).set(connection_profile_dict)
        logger.info(f"Connection profile {connection_id} for user {user_id} saved successfully.")
        return {
            "success": "connection profile successfully saved"   }
        
    except Exception as e:
        err_point = __package__ or "connection_service" 
        logger.error("[%s] Error saving conn profile %s for user %s: %s", err_point, connection_id, user_id, e, exc_info=True)
        return {'error': f"[{err_point}] - Error saving connection profile: {str(e)}"}

def get_user_connections(user_id:str) -> list[ConnectionProfile]:
    if not user_id:
        logger.error("Cannot get connections: missing user ID")
        return [] 

    try:
        connections_ref = db.collection("users").document(user_id).collection("connections")
        connections_stream = connections_ref.stream() 
        connection_list = []
        for connection_doc in connections_stream: 
            if connection_doc.exists:
                connection_data = connection_doc.to_dict()
                # Ensure all fields are present for ConnectionProfile.from_dict
                # This is important if documents might have missing fields from older versions.
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
    
    try:
        db.collection("users").document(user_id).collection("settings").document("active_connection").set({
            "connection_id": effective_connection_id
        })
        logger.info(f"Active connection set to '{effective_connection_id}' for user '{user_id}'.")
        return {"success": "active connection set", "connection_id": effective_connection_id}
    except Exception as e:
        logger.error(f"Error setting active conn for user {user_id} to {effective_connection_id}: {e}", exc_info=True)
        return {"error": f"Cannot set active connection: {str(e)}"}

def get_active_connection_firestore(user_id: str) -> str:
    if not user_id:
        logger.error("Cannot get active connection: missing user ID")
        return get_null_connection_id("UNKNOWN_USER_ACTIVE_CONN_ERROR") 

    try:
        doc_ref = db.collection("users").document(user_id).collection("settings").document("active_connection")
        doc = doc_ref.get()
        if doc.exists:
            active_cid = doc.to_dict().get("connection_id")
            logger.debug(f"Retrieved active connection_id '{active_cid}' for user '{user_id}'.")
            return active_cid if active_cid is not None else get_null_connection_id(user_id) # Ensure null if db has None
        else:
            logger.info(f"No active conn for user '{user_id}'. Setting/returning null.")
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
        logger.info(f"Active connection cleared (set to '{null_connection_id}') for user '{user_id}'.")
        return {"success": "active connection cleared", "connection_id": null_connection_id}
    except Exception as e:
        err_point = __package__ or "connection_service"
        logger.error("[%s] Error clearing active conn for user %s: %s", err_point, user_id, e, exc_info=True)
        return {'error': f"Error clearing active connection: {str(e)}"}

def get_connection_profile(user_id: str, connection_id: str) -> Optional[ConnectionProfile]:
    null_suffix = current_app.config.get('NULL_CONNECTION_ID_SUFFIX', '_null')
    if not user_id or not connection_id or (isinstance(connection_id, str) and connection_id.endswith(null_suffix)):
        logger.warning(f"Attempt to get profile with invalid IDs. User:'{user_id}', Conn:'{connection_id}'")
        return None 

    try:
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
            logger.warning(f"Conn profile not found: user '{user_id}', conn '{connection_id}'.")
            return None
    except Exception as e:
        logger.error("[%s] Error getting conn profile (user %s, conn %s): %s", "conn_service", user_id, connection_id, e, exc_info=True)
        raise ConnectionError(f"Could not retrieve connection profile: {str(e)}") from e

def update_connection_profile(
    user_id: str, 
    connection_id: str, 
    data: Optional[str] = None, 
    profile_text_content_list: Optional[List[str]] = None, 
    updated_personality_traits: Optional[List[Dict[str, Any]]] = None 
) -> Dict:
    null_suffix = current_app.config.get('NULL_CONNECTION_ID_SUFFIX', '_null')
    if not user_id or not connection_id or (isinstance(connection_id, str) and connection_id.endswith(null_suffix)):
        logger.error("Cannot update conn profile: invalid IDs. User:'%s', Conn:'%s'", user_id, connection_id)
        return {"error": "Cannot update connection profile: Missing or invalid user ID or connection ID."}

    doc_ref = db.collection("users").document(user_id).collection("connections").document(connection_id)
    current_profile_doc = doc_ref.get()
    if not current_profile_doc.exists:
        logger.error(f"Conn profile {connection_id} for user {user_id} not found. Cannot update.")
        return {"error": "Connection profile not found, cannot update."}
    
    current_profile_data = current_profile_doc.to_dict()
    update_payload = {} # Build payload with only the fields to change

    # Update basic form data fields
    if data is not None:
        update_payload["context_block"] = data
    elif data == "":
        update_payload["context_block"] = None # Explicitly set to None if empty string

    # Update OCR'd text content if provided (None means no change, [] means clear)
    if profile_text_content_list is not None:
        if current_profile_data.get("profile_text_content") != profile_text_content_list:
            update_payload["profile_text_content"] = profile_text_content_list
    
        
        combined_traits = current_profile_data.get("personality_traits", [])
        if updated_personality_traits is not None:
            combined_traits.append(updated_personality_traits)
        
        if combined_traits and len(combined_traits) > 5:
            # If more than 5 traits, keep only the top 5 by confidence
            update_payload["personality_traits"] = _get_top_n_traits(combined_traits, 5)

    
    # Note: The logic for comparing new traits with existing ones and merging to keep top 5
    # needs to be clarified. The current interpretation is:
    # - If new images are provided, traits are derived SOLELY from these new images.
    # - If no new images (`profile_pics_raw_files` is None), traits are not touched by this part of the logic.
    # - If `profile_pics_raw_files` is an empty list, it means "remove traits derived from photos".
    # If "compare the confidence scores, and save the highest 5" meant combining traits derived from
    # *old* images (currently stored) with traits from *new* images, then we'd need to fetch
    # `current_profile_data.get("personality_traits", [])`, merge with `new_photo_traits_with_scores`,
    # then apply `_get_top_n_traits`.
    # Given "When ... called with new profile images", it suggests the new images are the source.

    if not update_payload:
        logger.info(f"No effective update data provided for conn {connection_id}, user {user_id}.")
        return {"warning": "no effective update data provided for connection profile", "connection_id": connection_id}

    try:
        doc_ref.update(update_payload)
        logger.info(f"Conn profile {connection_id} for user {user_id} updated with keys: {list(update_payload.keys())}.")
        return {"success": "connection profile updated", "connection_id": connection_id}
    except Exception as e:
        logger.error(f"Error updating conn profile {connection_id} for user {user_id}: {e}", exc_info=True)
        return {"error": f"Cannot update connection profile: {str(e)}"}


def delete_connection_profile(user_id: str, connection_id:str) -> dict:
    null_suffix = current_app.config.get('NULL_CONNECTION_ID_SUFFIX', '_null')
    if not user_id or not connection_id or (isinstance(connection_id, str) and connection_id.endswith(null_suffix)):
        logger.error("Cannot delete conn profile: invalid IDs. User:'%s', Conn:'%s'", user_id, connection_id)
        return {"error": "Cannot delete connection profile: Missing or invalid user ID or connection ID."}
    
    try:
        doc_ref = db.collection("users").document(user_id).collection("connections").document(connection_id)
        if not doc_ref.get().exists:
            logger.warning(f"Delete attempt: non-existent conn profile {connection_id} for user {user_id}.")
            return {"warning": "connection profile not found, no action taken", "connection_id": connection_id}

        doc_ref.delete()
        logger.info(f"Conn profile {connection_id} for user {user_id} deleted successfully.")
        # TODO: Consider deleting associated images from GCS if required. This needs careful thought on cascading deletes.
        return {"success": "connection profile deleted", "connection_id": connection_id}
    except Exception as e:
        logger.error(f"Error deleting conn profile {connection_id} for user {user_id}: {e}", exc_info=True)
        return {"error": f"Cannot delete connection profile: {str(e)}"}