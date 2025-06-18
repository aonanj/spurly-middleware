from class_defs.conversation_def import Conversation
from datetime import datetime, timezone, timedelta
from flask import g, current_app
from google.cloud import firestore
from google.cloud import storage 
from infrastructure.clients import get_firestore_db, get_algolia_client
from infrastructure.id_generator import generate_conversation_id 
from infrastructure.logger import get_logger
import uuid
from werkzeug.utils import secure_filename
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import threading

logger = get_logger(__name__)

# Configuration for profile image uploads
MAX_PROFILE_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_PROFILE_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


@dataclass
class ConversationSearchParams:
    """Encapsulates search parameters for better type safety and validation."""
    user_id: str
    keyword: Optional[str] = None
    connection_id: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    sort: str = "desc"
    limit: int = 20
    
    def __post_init__(self):
        """Validate and normalize parameters."""
        if self.sort not in ["asc", "desc"]:
            self.sort = "desc"
        
        if self.limit <= 0:
            self.limit = 20
        elif self.limit > 100:  # Prevent excessive queries
            self.limit = 100
            
        # Ensure date_to includes the entire day if time is midnight
        if self.date_to and self.date_to.time() == datetime.min.time():
            self.date_to = self.date_to + timedelta(days=1) - timedelta(microseconds=1)


class StorageServiceError(Exception):
    """Base exception for storage service errors."""
    pass


class ConversationNotFoundError(StorageServiceError):
    """Raised when a conversation cannot be found."""
    pass


class AlgoliaIndexingError(StorageServiceError):
    """Raised when Algolia indexing fails but should not block the operation."""
    pass


def _allowed_profile_image_file(filename: str) -> bool:
    """Checks if the filename has an allowed extension."""
    if not filename:
        return False
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_PROFILE_IMAGE_EXTENSIONS


def upload_profile_image(user_id: str, connection_id: str, image_bytes: bytes, 
                        original_filename: str, content_type: str) -> str:
    """
    Uploads a profile image to Google Cloud Storage and returns its public URL.
    
    Args:
        user_id: The ID of the user uploading the image
        connection_id: The ID of the connection this image is for
        image_bytes: The image content in bytes
        original_filename: The original filename of the uploaded image
        content_type: The content type of the image
        
    Returns:
        The public URL of the uploaded image
        
    Raises:
        ValueError: If the file type or size is invalid
        StorageServiceError: If the upload fails
    """
    # Validate file type
    if not _allowed_profile_image_file(original_filename):
        logger.error(f"User {user_id} attempted to upload invalid file type: {original_filename}")
        raise ValueError(f"Invalid file type. Allowed: {', '.join(ALLOWED_PROFILE_IMAGE_EXTENSIONS)}")
    
    # Validate file size
    if not image_bytes:
        raise ValueError("Profile picture cannot be empty")
        
    if len(image_bytes) > MAX_PROFILE_IMAGE_SIZE_BYTES:
        size_mb = len(image_bytes) / (1024 * 1024)
        max_mb = MAX_PROFILE_IMAGE_SIZE_BYTES / (1024 * 1024)
        raise ValueError(f"File size ({size_mb:.1f}MB) exceeds {max_mb}MB limit")
    
    # Get storage configuration
    bucket_name = current_app.config.get("GCS_PROFILE_PICS_BUCKET")
    if not bucket_name:
        raise StorageServiceError("Storage bucket not configured")
    
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        
        # Create unique filename
        s_filename = secure_filename(original_filename)
        unique_id = str(uuid.uuid4())
        gcs_path = f"users/{user_id}/connections/{connection_id}/{unique_id}-{s_filename}"
        
        # Upload to GCS
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(image_bytes, content_type=content_type)
        
        logger.error(f"LOG.INFO: Uploaded profile picture for user={user_id}, connection={connection_id}: {gcs_path}")
        return blob.public_url
        
    except Exception as e:
        logger.error(f"Failed to upload profile picture: {e}", exc_info=True)
        raise StorageServiceError(f"Upload failed: {str(e)}")


class ConversationStorage:
    """Handles conversation storage operations with Firestore and Algolia."""
    
    def __init__(self):
        # Use threading instead of asyncio for better Flask compatibility
        self._algolia_thread_pool = []
        self._algolia_lock = threading.Lock()
    
    def _validate_conversation_data(self, conversation: Conversation) -> None:
        """Validates conversation data before saving."""
        if not conversation.user_id:
            raise ValueError("Missing user_id")
            
        if not conversation.conversation_id:
            raise ValueError("Missing conversation_id")
            
        # Ensure conversation_id has proper format
        if conversation.conversation_id.startswith(":"):
            conversation.conversation_id = f"{conversation.user_id}{conversation.conversation_id}"
    
    def _prepare_algolia_payload(self, conversation: Conversation, 
                                  conversation_text: str) -> Dict[str, Any]:
        """Prepares the payload for Algolia indexing."""
        created_at = conversation.created_at

                
        payload = {
            "objectID": conversation.conversation_id,
            "user_id": conversation.user_id,
            "text": conversation_text,
            "created_at_timestamp": int(created_at.timestamp()),
        }
        
        # Add optional fields
        optional_fields = ["connection_id", "situation", "topic"]
        for field in optional_fields:
            value = getattr(conversation, field, None)
            if value:
                payload[field] = value
                
        return payload
    
    def _index_to_algolia_background(self, conversation: Conversation, 
                                    conversation_text: str) -> None:
        """Index to Algolia in a background thread."""
        def _do_index():
            try:
                algolia_client = get_algolia_client()
                if not algolia_client or not conversation_text:
                    return
                    
                index_name = current_app.config.get('ALGOLIA_CONVERSATIONS_INDEX')
                if not index_name:
                    logger.error("Algolia index name not configured")
                    return
                
                payload = self._prepare_algolia_payload(conversation, conversation_text)
                algolia_client.save_object(index_name, payload)
                logger.error(f"LOG.INFO: Indexed conversation {conversation.conversation_id} to Algolia")
                
            except Exception as e:
                logger.error(f"Failed to index to Algolia: {e}", exc_info=True)
            finally:
                # Clean up thread reference
                with self._algolia_lock:
                    if threading.current_thread() in self._algolia_thread_pool:
                        self._algolia_thread_pool.remove(threading.current_thread())
        
        # Start background thread
        thread = threading.Thread(target=_do_index, daemon=True)
        with self._algolia_lock:
            self._algolia_thread_pool.append(thread)
        thread.start()
    
    def save_conversation(self, conversation: Conversation) -> Dict[str, str]:
        """
        Saves a conversation to Firestore and indexes it in Algolia.
        
        Args:
            conversation: The conversation to save
            
        Returns:
            Dict with success status and conversation_id
            
        Raises:
            ValueError: If validation fails
            StorageServiceError: If save operation fails
        """
        try:
            # Validate data
            self._validate_conversation_data(conversation)
            
            # Ensure created_at is set
            if not conversation.created_at:
                conversation.created_at = datetime.now(timezone.utc)
            elif isinstance(conversation.created_at, str):
                try:
                    conversation.created_at = conversation.created_at
                except ValueError:
                    logger.error(f"Invalid created_at format, using current time")
                    conversation.created_at = datetime.now(timezone.utc)
            
            # Get conversation text for indexing
            conversation_text = conversation.conversation_as_string()
            
            # Save to Firestore
            db = get_firestore_db()
            doc_ref = db.collection("users").document(conversation.user_id).collection("conversations").document(conversation.conversation_id)

            doc_data = conversation.to_dict()
            doc_ref.set(doc_data)
            
            logger.error(f"LOG.INFO: Saved conversation {conversation.conversation_id} to Firestore")
            
            # Index to Algolia in background thread
            self._index_to_algolia_background(conversation, conversation_text)
            
            return {
                "success": "conversation saved",
                "conversation_id": conversation.conversation_id
            }
            
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}", exc_info=True)
            if isinstance(e, (ValueError, StorageServiceError)):
                raise
            raise StorageServiceError(f"Save operation failed: {e}")
    
    def get_conversation(self, user_id: str, conversation_id: str) -> Conversation:
        """
        Retrieves a conversation by ID.
        
        Args:
            user_id: The user ID
            conversation_id: The conversation ID
            
        Returns:
            The conversation object
            
        Raises:
            ValueError: If parameters are invalid
            ConversationNotFoundError: If conversation doesn't exist
        """
        if not user_id or not conversation_id:
            raise ValueError("Both user_id and conversation_id are required")
            
        try:
            db = get_firestore_db()
            doc_ref = db.collection("users").document(user_id).collection("conversations").document(conversation_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                raise ConversationNotFoundError(
                    f"Conversation {conversation_id} not found for user {user_id}"
                )
                
            return Conversation.from_dict(doc.to_dict())
            
        except Exception as e:
            if isinstance(e, ConversationNotFoundError):
                raise
            logger.error(f"Failed to get conversation: {e}", exc_info=True)
            raise StorageServiceError(f"Failed to retrieve conversation: {e}")
    
    def delete_conversation(self, user_id: str, conversation_id: str) -> Dict[str, str]:
        """
        Deletes a conversation from Firestore and Algolia.
        
        Args:
            user_id: The user ID
            conversation_id: The conversation ID
            
        Returns:
            Success status
            
        Raises:
            ValueError: If parameters are invalid
            StorageServiceError: If deletion fails
        """
        if not user_id or not conversation_id:
            raise ValueError("Both user_id and conversation_id are required")
            
        try:
            # Delete from Firestore
            db = get_firestore_db()
            doc_ref = db.collection("users").document(user_id)\
                       .collection("conversations").document(conversation_id)
            doc_ref.delete()
            
            logger.error(f"LOG.INFO: Deleted conversation {conversation_id} from Firestore")
            
            # Delete from Algolia in background
            def _delete_from_algolia():
                try:
                    algolia_client = get_algolia_client()
                    index_name = current_app.config.get('ALGOLIA_CONVERSATIONS_INDEX')
                    
                    if algolia_client and index_name:
                        algolia_client.delete_object(
                            index_name=index_name, 
                            object_id=conversation_id
                        )
                        logger.error(f"LOG.INFO: Deleted conversation {conversation_id} from Algolia")
                except Exception as e:
                    logger.error(f"Failed to delete from Algolia: {e}", exc_info=True)
            
            thread = threading.Thread(target=_delete_from_algolia, daemon=True)
            thread.start()
            
            return {"success": f"conversation_id {conversation_id} deleted"}
            
        except Exception as e:
            logger.error(f"Failed to delete conversation: {e}", exc_info=True)
            raise StorageServiceError(f"Delete operation failed: {e}")
    
    def search_conversations(self, params: ConversationSearchParams) -> List[Conversation]:
        """
        Searches for conversations using Algolia or Firestore.
        
        Args:
            params: Search parameters
            
        Returns:
            List of matching conversations
        """
        try:
            if params.keyword:
                return self._search_with_algolia(params)
            else:
                return self._search_with_firestore(params)
                
        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return []
    
    def _search_with_algolia(self, params: ConversationSearchParams) -> List[Conversation]:
        """Searches conversations using Algolia."""
        algolia_client = get_algolia_client()
        index_name = current_app.config.get('ALGOLIA_CONVERSATIONS_INDEX')
        
        if not algolia_client or not index_name:
            logger.error("Algolia not available, falling back to Firestore")
            return self._search_with_firestore(params)
        
        try:
            # Build Algolia filters
            filters = [f"user_id:{params.user_id}"]
            
            if params.connection_id:
                filters.append(f"connection_id:{params.connection_id}")
                
            if params.date_from:
                filters.append(f"created_at_timestamp >= {int(params.date_from.timestamp())}")
                
            if params.date_to:
                filters.append(f"created_at_timestamp <= {int(params.date_to.timestamp())}")
            
            # Search Algolia
            search_params = {
                "query": params.keyword,
                "filters": " AND ".join(filters),
                "hitsPerPage": params.limit * 2,  # Get extra in case some are missing
                "attributesToRetrieve": ["objectID"]
            }
            
            # Use the correct Algolia client method
            try:
                # Try the newer client method first
                results = algolia_client.search(
                    index_name,
                    search_params
                )
                hits = getattr(results, 'hits', [])
            except AttributeError:
                # Fall back to legacy search method
                search_request = {
                    "indexName": index_name,
                    "params": search_params
                }
                results = algolia_client.search(search_request)
                if results and hasattr(results, 'results') and len(results.results) > 0:
                    hits = getattr(results.results[0], 'hits', [])
                else:
                    hits = []
            
            if not hits:
                return []
            
            # Get conversation IDs
            conversation_ids = [hit['objectID'] for hit in hits]
            
            if not conversation_ids:
                return []
            
            # Fetch from Firestore in batches
            conversations = self._batch_fetch_conversations(
                params.user_id, 
                conversation_ids,
                params.limit
            )
            
            # Maintain Algolia's relevance order
            id_to_convo = {c.conversation_id: c for c in conversations}
            ordered = [id_to_convo[cid] for cid in conversation_ids if cid in id_to_convo]
            
            return ordered[:params.limit]
            
        except Exception as e:
            logger.error(f"Algolia search failed: {e}", exc_info=True)
            return self._search_with_firestore(params)
    
    def _search_with_firestore(self, params: ConversationSearchParams) -> List[Conversation]:
        """Searches conversations using Firestore."""
        try:
            db = get_firestore_db()
            query = db.collection("users").document(params.user_id)\
                     .collection("conversations")
            
            # Apply filters
            if params.connection_id:
                query = query.where("connection_id", "==", params.connection_id)
                
            if params.date_from:
                query = query.where("created_at", ">=", params.date_from)
                
            if params.date_to:
                query = query.where("created_at", "<=", params.date_to)
            
            # Apply sorting
            sort_direction = (firestore.Query.DESCENDING if params.sort == "desc" 
                            else firestore.Query.ASCENDING)
            query = query.order_by("created_at", direction=sort_direction)
            
            # Apply limit
            query = query.limit(params.limit)
            
            # Execute query
            docs = query.stream()
            conversations = []
            for doc in docs:
                try:
                    if doc.exists:
                        conversations.append(Conversation.from_dict(doc.to_dict()))
                except Exception as e:
                    logger.error(f"Error parsing conversation document: {e}")
                    continue
            
            # If keyword search was requested but Algolia wasn't available,
            # do basic filtering on the results
            if params.keyword:
                keyword_lower = params.keyword.lower()
                conversations = [
                    c for c in conversations
                    if keyword_lower in c.conversation_as_string().lower()
                ]
            
            return conversations
            
        except Exception as e:
            logger.error(f"Firestore search failed: {e}", exc_info=True)
            return []
    
    def _batch_fetch_conversations(self, user_id: str, conversation_ids: List[str], 
                                   limit: int) -> List[Conversation]:
        """Fetches conversations from Firestore in batches."""
        conversations = []
        
        # Firestore 'in' queries are limited to 10 items
        for i in range(0, len(conversation_ids), 10):
            chunk = conversation_ids[i:i + 10]
            if not chunk:
                continue
                
            try:
                db = get_firestore_db()
                query = db.collection("users").document(user_id)\
                         .collection("conversations")\
                         .where("conversation_id", "in", chunk)
                
                docs = query.stream()
                for doc in docs:
                    try:
                        if doc.exists and len(conversations) < limit:
                            conversations.append(Conversation.from_dict(doc.to_dict()))
                    except Exception as e:
                        logger.error(f"Error parsing conversation in batch: {e}")
                        continue
                        
                if len(conversations) >= limit:
                    break
            except Exception as e:
                logger.error(f"Error in batch fetch: {e}", exc_info=True)
                continue
                
        return conversations


# Initialize global storage instance
_storage = ConversationStorage()


# Public API functions that maintain backward compatibility
def save_conversation(data: Conversation) -> Dict[str, str]:
    """
    Saves a conversation with the conversation_id.
    
    Args:
        data: The conversation data to save
        
    Returns:
        Status dict with success message and conversation_id
    """
    # Ensure user_id is set from global context if not in data

        
    return _storage.save_conversation(data)


def get_conversation(user_id: str, conversation_id: str) -> Conversation:
    """
    Gets a conversation by the conversation_id.
    
    Args:
        conversation_id: The unique id for the conversation
        
    Returns:
        Conversation object
        
    Raises:
        ConversationNotFoundError: If conversation not found
    """
    user_id = user_id

    
    if not user_id:
        raise ValueError("User not authenticated")
        
    return _storage.get_conversation(user_id, conversation_id)


def delete_conversation(conversation_id: str) -> Dict[str, str]:
    """
    Deletes a conversation by the conversation_id.
    
    Args:
        conversation_id: The unique id for the conversation
        
    Returns:
        Status dict confirming deletion
    """
    user_id = None
    if hasattr(g, 'user_id'):
        user_id = getattr(g, "user_id", None)
    
    if not user_id:
        raise ValueError("User not authenticated")
        
    return _storage.delete_conversation(user_id, conversation_id)


def get_conversations(user_id: str, filters: Optional[Dict[str, Any]] = None) -> List[Conversation]:
    """
    Searches for conversations based on filters.
    
    Args:
        user_id: User ID associated with the conversations
        filters: Search/sort criteria (keyword, date_from, date_to, connection_id, sort, limit)
        
    Returns:
        List of Conversation objects matching the criteria
    """
    if not user_id:
        logger.error("Missing user_id for get_conversations")
        return []
    
    # Convert filters dict to ConversationSearchParams
    if filters is None:
        filters = {}
        
    params = ConversationSearchParams(
        user_id=user_id,
        keyword=filters.get("keyword"),
        connection_id=filters.get("connection_id"),
        date_from=filters.get("date_from"),
        date_to=filters.get("date_to"),
        sort=filters.get("sort", "desc"),
        limit=filters.get("limit", 20)
    )
    
    return _storage.search_conversations(params)