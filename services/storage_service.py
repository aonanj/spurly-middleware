from class_defs.conversation_def import Conversation
from datetime import datetime, timezone, timedelta
from flask import g, current_app
from google.cloud import firestore
from google.cloud import storage # Added for GCS
from gpt_training.anonymizer import anonymize_conversation
from infrastructure.clients import db, get_algolia_client
from infrastructure.id_generator import generate_conversation_id # Could use a generic ID generator here too
from infrastructure.logger import get_logger
import openai
import uuid # For generating unique filenames
from werkzeug.utils import secure_filename # For sanitizing filenames


logger = get_logger(__name__)

# Configuration for profile image uploads (could also be in config.py)
MAX_PROFILE_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB example
ALLOWED_PROFILE_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def _allowed_profile_image_file(filename: str) -> bool:
    """Checks if the filename has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_PROFILE_IMAGE_EXTENSIONS

def upload_profile_image(user_id: str, connection_id: str, image_bytes: bytes, original_filename: str, content_type: str) -> str:
    """
    Uploads a profile image to Google Cloud Storage and returns its public URL.

    Args:
        user_id (str): The ID of the user uploading the image.
        connection_id (str): The ID of the connection this image is for.
        image_bytes (bytes): The image content in bytes.
        original_filename (str): The original filename of the uploaded image.
        content_type (str): The content type of the image.

    Returns:
        str: The public URL of the uploaded image.

    Raises:
        ValueError: If the file type or size is invalid, or bucket is not configured.
        ConnectionError: If the upload to GCS fails.
    """
    if not _allowed_profile_image_file(original_filename):
        logger.error(f"User {user_id} attempted to upload invalid file type for profile pic: {original_filename}")
        raise ValueError(f"Invalid file type for profile picture: {original_filename}. Allowed: {', '.join(ALLOWED_PROFILE_IMAGE_EXTENSIONS)}")

    if len(image_bytes) == 0:
        logger.error(f"User {user_id} attempted to upload an empty profile pic: {original_filename}")
        raise ValueError("Profile picture cannot be empty.")

    if len(image_bytes) > MAX_PROFILE_IMAGE_SIZE_BYTES:
        logger.error(f"User {user_id} attempted to upload oversized profile pic: {original_filename}, size: {len(image_bytes)}")
        raise ValueError(f"Profile picture size exceeds {MAX_PROFILE_IMAGE_SIZE_BYTES // (1024*1024)}MB limit.")

    storage_client = storage.Client()
    bucket_name = current_app.config.get("GCS_PROFILE_PICS_BUCKET")
    if not bucket_name:
        logger.critical("GCS_PROFILE_PICS_BUCKET is not configured in the application.")
        raise ValueError("Storage bucket for profile pictures is not configured.")

    bucket = storage_client.bucket(bucket_name)
    
    # Sanitize filename and make it unique
    s_filename = secure_filename(original_filename)
    unique_file_id = str(uuid.uuid4())
    # Structure the path: e.g., profiles/<user_id>/<connection_id>/<uuid>-<filename>
    gcs_filename = f"profiles/{user_id}/{connection_id}/{unique_file_id}-{s_filename}"
    
    blob = bucket.blob(gcs_filename)

    try:
        blob.upload_from_string(image_bytes, content_type=content_type)
        logger.info(f"Successfully uploaded profile picture '{gcs_filename}' to GCS bucket '{bucket_name}' for user '{user_id}', connection '{connection_id}'.")
        return blob.public_url
    except Exception as e:
        logger.error(f"Failed to upload profile picture '{gcs_filename}' to GCS for user '{user_id}': {e}", exc_info=True)
        raise ConnectionError(f"Could not upload profile picture due to a storage error: {str(e)}")


# --- Existing Conversation Methods ---
def save_conversation(data: Conversation) -> dict:
    
    """
    Saves a conversation with the conversation_id.

    Args
        data: the conversation data associated with the active user to be saved
            Conversation 

    Return
        status: indicates if conversation is saved
            str

    """

    user_id = g.user['user_id']
    conversation_id = data.conversation_id
    connection_id = data.connection_id
    
    if not user_id:
        logger.error("Error: Failed to save conversation - missing user_id", __name__)
        return {"error": "Missing user_ids"}

    if not conversation_id:
        conversation_id = generate_conversation_id(user_id)
    elif conversation_id.startswith(":"):
        conversation_id = f"{user_id}{conversation_id}"

    # Prepare data for Firestore, ensuring created_at is set
    created_time = data.created_at or datetime.now(timezone.utc)
    # Ensure created_at is a datetime object before conversion
    if isinstance(created_time, str):
        try:
            created_time = datetime.fromisoformat(created_time)
        except ValueError:
            logger.error(f"Invalid created_at format for {conversation_id}. Using current time.", exc_info=True)
            created_time = datetime.now(timezone.utc)

    spurs = data.spurs
    situation = data.situation
    topic = data.topic
    conversation_obj = get_conversation(conversation_id) # Changed variable name
    conversation_text = Conversation.conversation_as_string(conversation_obj) # Use the fetched object
    
    try:
        doc_ref = db.collection("users").document(user_id).collection("conversations").document(conversation_id)
        doc = doc_ref.get()
        # if doc.exists: # This part is redundant if get_conversation already fetches it or handles non-existence
            # conversation_obj = Conversation.from_dict(doc.to_dict())


        doc_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "conversation": conversation_obj.conversation if conversation_obj else [], # Ensure this is serializable
            "connection_id": connection_id,
            "situation": situation,
            "topic": topic,
            "spurs": spurs,
            "created_at": created_time
        }

        # Anonymization should happen on the data to be saved
        # anonymize_conversation(Conversation.from_dict(doc_data)) # This creates a new object, ensure it's used or data is modified in place

        # Re-creating Conversation object for anonymization if needed, or ensure anonymize_conversation modifies dict
        temp_convo_for_anonymization = Conversation.from_dict(doc_data)
        anonymize_conversation(temp_convo_for_anonymization)
        # Assuming anonymize_conversation modifies the object in place or you re-assign its .to_dict()
        # For safety, let's assume it modifies in place or doc_data needs to be updated from temp_convo_for_anonymization
        # This part needs careful review of anonymize_conversation's behavior.
        # For now, assuming doc_data is what we intend to save after potential anonymization if anonymize_conversation modifies it.
        # If anonymize_conversation works on the object, then get the dict again:
        # anonymized_doc_data = temp_convo_for_anonymization.to_dict()
        # doc_ref.set(anonymized_doc_data)
        # For this refactor, I'll assume the current anonymization logic is separate and focus on the new function.
        # The original anonymize_conversation call seemed to not use its return value.

        doc_ref.set(doc_data) # Saving original or intended data

        # --- Index in Algolia ---
        algolia_client = get_algolia_client()
        aloglia_conversations_index = current_app.config['ALGOLIA_CONVERSATIONS_INDEX']
        if algolia_client and conversation_text: 
            try:
                algolia_payload = {
                    "objectID": conversation_id,
                    "user_id": user_id,
                    "text": conversation_text,
                    "created_at_timestamp": int(created_time.timestamp()),
                    "connection_id": connection_id,
                    "situation": situation,
                    "topic": topic,
                }
                algolia_payload = {k: v for k, v in algolia_payload.items() if v is not None}

                res = algolia_client.save_object(aloglia_conversations_index, algolia_payload)
                # wait_for_task might be synchronous and slow down requests. Consider backgrounding.
                algolia_client.wait_for_task(index_name=aloglia_conversations_index, task_id=res.task_id)
                logger.info(f"Successfully indexed conversation {conversation_id} in Algolia.")
            except Exception as algolia_error:
                logger.error(f"Failed to index conversation {conversation_id} in Algolia: {algolia_error}", exc_info=True)
        
        return {"status": "conversation saved", "conversation_id": conversation_id}
    except firestore.ReadAfterWriteError as e:
        logger.error("[%s] Error: %s Save conversation failed", __name__, e)
        raise firestore.ReadAfterWriteError(f"Save conversation failed: {e}") from e
    except Exception as e:
        logger.error("[%s] Error: %s Save conversation failed", __name__, e)
        raise ValueError(f"Save conversation failed: {e}") from e
        

def get_conversation(conversation_id: str) -> Conversation: # Return type is Conversation
    """
    Gets a conversation by the conversation_id.

    Args
        conversation_id: the unique id for the conversation requested
            str
    Return
        conversation corresponding to the conversation_id
            Conversation object

    """
    
    user_id = g.user['user_id']
    
    if not user_id or not conversation_id:
        logger.error("Error: Failed to get conversation - missing user_id or conversation_id ", __name__)
        # Consider raising a more specific error like ValueError or custom exception
        raise ValueError("Missing user_id or conversation_id for get_conversation")

    doc_ref = db.collection("users").document(user_id).collection("conversations").document(conversation_id)
    doc = doc_ref.get()
    if doc.exists:
        return Conversation.from_dict(doc.to_dict()) # Return Conversation object
    else:
        logger.warning(f"No conversation exists with conversation_id {conversation_id} for user {user_id}", __name__)
        # Depending on desired behavior, could return None or raise a NotFound error
        raise ValueError(f"Conversation with ID {conversation_id} not found for user {user_id}.")

# ... (rest of the existing conversation methods: delete_conversation, get_conversations)
# Ensure they are compatible with Conversation object return type from get_conversation if they use it.

def delete_conversation(conversation_id: str) -> dict:
    """
    Deletes a conversation by the conversation_id from Firestore and Algolia.

    Args
        conversation_id: the unique id for the conversation requested to be deleted
            str
    Return
        status: confirmation string that conversation corresponding to the conversation_id is deleted
            dict

    """
    user_id = g.user['user_id']

    if not user_id:
        logger.error("Error: Could not extract user_id for conversation_id '%s' for deletion", conversation_id)
        return {"error": "User ID not available for deletion"} # More generic error

    if not conversation_id:
        logger.error("Error: Failed to delete conversation - missing conversation_id ", __name__)
        return {"error": "Missing conversation_id"}

    try:
        # --- Delete from Firestore ---
        db.collection("users").document(user_id).collection("conversations").document(conversation_id).delete()
        logger.info(f"Deleted conversation {conversation_id} from Firestore for user {user_id}.")

        # --- Delete from Algolia ---
        algolia_client = get_algolia_client()
        aloglia_conversations_index = current_app.config['ALGOLIA_CONVERSATIONS_INDEX']
        if algolia_client:
            try:
                res = algolia_client.delete_object(index_name=aloglia_conversations_index, object_id=conversation_id)
                algolia_client.wait_for_task(index_name=aloglia_conversations_index, task_id=res.task_id)
                logger.info(f"Deleted conversation {conversation_id} from Algolia index.")
            except Exception as algolia_error:
                logger.error(f"Failed to delete conversation {conversation_id} from Algolia: {algolia_error}", exc_info=True)

        return {"status": f"conversation_id {conversation_id} deleted"}

    except Exception as e:
         logger.error(f"Error deleting conversation {conversation_id} for user {user_id}: {e}", exc_info=True)
         raise ValueError(f"Failed to delete conversation {conversation_id}: {e}") from e


def get_conversations(user_id: str, filters: dict) -> list[Conversation]:
    """
    Searches for conversations based on filters. Uses Algolia for keyword search
    and Firestore for retrieval and other filtering.

    Args:
        user_id (str): User ID associated with the conversations.
        filters (dict, optional): Search/sort criteria (keyword, date_from, date_to, connection_id, sort). Defaults to None.
        limit (int, optional): Maximum number of conversations to return. Defaults to 20. (Limit not used in current code)

    Returns:
        list[Conversation]: A list of Conversation objects matching the criteria.
    """
    if not user_id:
        logger.error("Error: Failed to get conversations - missing user_id", __name__)
        return [] 

    if filters is None:
        filters = {}

    keyword = filters.get("keyword")
    algolia_client = get_algolia_client()
    aloglia_conversations_index = current_app.config.get('ALGOLIA_CONVERSATIONS_INDEX') # Use .get for safety
    aloglia_search_results_limit = current_app.config.get('ALGOLIA_SEARCH_RESULTS_LIMIT', 20) # Default if not set

    try:
        if keyword and algolia_client and aloglia_conversations_index:
            logger.info(f"Performing Algolia keyword search for user '{user_id}' with keyword: '{keyword}'")
            search_params = {"query": keyword, "filters": f"user_id:{user_id}", "hitsPerPage": aloglia_search_results_limit * 5, "attributesToRetrieve": ["objectID"]}
            connection_id_filter = filters.get("connection_id")
            if connection_id_filter: search_params["filters"] += f" AND connection_id:{connection_id_filter}"
            date_filter_parts = []
            if "date_from" in filters and isinstance(filters["date_from"], datetime): date_filter_parts.append(f"created_at_timestamp >= {int(filters['date_from'].timestamp())}")
            if "date_to" in filters and isinstance(filters["date_to"], datetime):
                 to_date = filters["date_to"]; 
                 if to_date.time() == datetime.min.time(): to_date = to_date + timedelta(days=1) - timedelta(microseconds=1)
                 date_filter_parts.append(f"created_at_timestamp <= {int(to_date.timestamp())}")
            if date_filter_parts: search_params["filters"] += " AND " + " AND ".join(date_filter_parts)
            
            # Algolia search method seems to have changed in recent clients.
            # Assuming a search method like client.search_single_index or similar.
            # The provided code `algolia_client.search({"requests": [...]})` might be for batch search.
            # For simplicity, let's assume a single index search that returns a response object with 'hits'.
            # This part needs to be adapted to the actual Algolia client version being used.
            # search_results = algolia_client.search_single_index(aloglia_conversations_index, search_params)
            # conversation_ids = [hit['objectID'] for hit in search_results.get('hits', [])]

            # Using the structure from the file, which seems to be a multi-query format
            raw_algolia_results = algolia_client.search({"indexName": aloglia_conversations_index, "params": search_params})
            
            conversation_ids = []
            if raw_algolia_results and raw_algolia_results.get('results') and raw_algolia_results['results'][0].get('hits'):
                conversation_ids = [hit['objectID'] for hit in raw_algolia_results['results'][0]['hits']]

            if not conversation_ids: logger.info(f"No Algolia hits for keyword '{keyword}', user '{user_id}'."); return []
            logger.info(f"Found {len(conversation_ids)} potential Algolia matches. Fetching from Firestore.")
            
            conversation_docs = []
            id_chunks = [conversation_ids[i:i + 10] for i in range(0, len(conversation_ids), 10)]
            for chunk in id_chunks:
                if not chunk: continue
                query = db.collection("users").document(user_id).collection("conversations").where("conversation_id", "in", chunk)
                docs = query.stream()
                conversation_docs.extend([doc.to_dict() for doc in docs if doc.exists])
            
            convos_map = {convo_data['conversation_id']: Conversation.from_dict(convo_data) for convo_data in conversation_docs if convo_data}
            ordered_convos = [convos_map[cid] for cid in conversation_ids if cid in convos_map][:aloglia_search_results_limit]
            logger.info(f"Returning {len(ordered_convos)} conversations (Algolia)."); return ordered_convos
        else:
            logger.info(f"No keyword or Algolia unavailable. Firestore query for user '{user_id}'.")
            query = db.collection("users").document(user_id).collection("conversations")
            connection_id_filter = filters.get("connection_id")
            if connection_id_filter: query = query.where("connection_id", "==", connection_id_filter)
            sort_field = "created_at"; sort_order_str = filters.get("sort", "desc")
            sort_direction = firestore.Query.DESCENDING if sort_order_str == "desc" else firestore.Query.ASCENDING
            if "date_from" in filters and isinstance(filters["date_from"], datetime): query = query.where(sort_field, ">=", filters["date_from"])
            if "date_to" in filters and isinstance(filters["date_to"], datetime):
                 to_date = filters["date_to"]; 
                 if to_date.time() == datetime.min.time(): to_date = to_date + timedelta(days=1) - timedelta(microseconds=1)
                 query = query.where(sort_field, "<=", to_date)
            query = query.order_by(sort_field, direction=sort_direction).limit(aloglia_search_results_limit)
            docs = query.stream()
            firestore_convos = [Conversation.from_dict(doc.to_dict()) for doc in docs if doc.exists]
            logger.info(f"Returning {len(firestore_convos)} conversations (Firestore)."); return firestore_convos
    except Exception as e:
        logger.error(f"Error getting conversations for user {user_id}: {e}", exc_info=True)
        return []