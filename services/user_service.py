from typing import Optional, Dict, List
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from firebase_admin import auth
from flask import current_app
from infrastructure.logger import get_logger
from class_defs.profile_def import UserProfile
from infrastructure.clients import get_firestore_db
from utils.moderation import redact_flagged_sentences


logger = get_logger(__name__)

def get_user(user_id: str) -> Optional[UserProfile]:
    """
    Get a user by their user_id from Firestore.
    
    Args:
        user_id: The unique user identifier
        
    Returns:
        UserProfile object if found, None otherwise
    """
    if not user_id:
        logger.error("get_user called with empty user_id")
        return None
    
    try:
        db = get_firestore_db()
        user_ref = db.collection("users").document(user_id)
        doc = user_ref.get()
        
        if not doc.exists:
            logger.error(f"LOG.INFO: User not found: {user_id}")
            return None
        
        data = doc.to_dict()
        user_profile = UserProfile.from_dict(data)
        return user_profile

    except Exception as e:
        logger.error(f"Error getting user {user_id}: {str(e)}", exc_info=True)
        return None

def get_user_by_auth_provider(auth_provider: str, auth_provider_id: str) -> Optional[UserProfile]:
    """
    Get a user by their authentication provider and provider ID.
    
    Args:
        auth_provider: The authentication provider (e.g., 'google.com', 'apple.com')
        auth_provider_id: The provider-specific ID (e.g., Firebase UID)
        
    Returns:
        UserProfile object if found, None otherwise
    """
    try:
        db = get_firestore_db()
        users_ref = db.collection("users")
        query = users_ref.where("auth_provider", "==", auth_provider).where("auth_provider_id", "==", auth_provider_id)
        docs = query.stream()
        
        for doc in docs:
            data = doc.to_dict()
            return UserProfile.from_dict(data)
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting user by auth provider {auth_provider}/{auth_provider_id}: {str(e)}", exc_info=True)
        return None

def get_user_by_email(email: str) -> Optional[UserProfile]:
    """
    Get a user by their email address.
    Args:
        email: The user's email address

    Returns:
        UserProfile object if found, None otherwise
    """
    try:
        db = get_firestore_db()
        users_ref = db.collection("users")
        query = users_ref.where("email", "==", email)
        docs = query.stream()

        for doc in docs:
            data = doc.to_dict()
            return UserProfile.from_dict(data)
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting user by email {email}: {str(e)}", exc_info=True)
        return None

def create_user(user_id: str,
    email: str,
    auth_provider: str,
    auth_provider_id: str,
    name: Optional[str] = None,
    age: Optional[int] = None,
    user_context_block: Optional[str] = None,
    selected_spurs: Optional[List[str]] = None,
) -> UserProfile:
    """
    Create a new user in Firestore.
    
    Args:
        email: User's email address
        auth_provider: Authentication provider ('email', 'google.com', 'apple.com', 'facebook.com')
        auth_provider_id: Provider-specific ID (Firebase UID for all providers)
        name: User's display name (optional)
        age: User's age (optional)
        user_context_block: User's context/profile text (optional)
        selected_spurs: List of selected spur variants (optional)
        
    Returns:
        Created UserProfile object
        
    Raises:
        ValueError: If required fields are missing or user already exists
    """
    if not email or not auth_provider or not auth_provider_id:
        raise ValueError("Email, auth_provider, and auth_provider_id are required")
    
    # Check if user already exists with this auth provider
    existing_user = get_user_by_auth_provider(auth_provider, auth_provider_id)
    if existing_user:
        raise ValueError(f"UserProfile already exists with {auth_provider}/{auth_provider_id}")
    
    # Generate a new user ID
    user_id = user_id
    if not user_id:
        user_id = ""
    
    # Use default spur variants if none provided
    if selected_spurs is None:
        selected_spurs = list(current_app.config.get('SPUR_VARIANTS', []))

    # Create user object
    user = UserProfile(
        user_id=user_id,
        email=email,
        auth_provider=auth_provider,
        auth_provider_id=auth_provider_id,
        name=name,
        age=age,
        user_context_block=redact_flagged_sentences(user_context_block) if user_context_block else None,
        selected_spurs=selected_spurs
    )
    
    try:
        db = get_firestore_db()
        user_ref = db.collection("users").document(user_id)
        user_ref.set(user.to_dict())
        
        logger.error(f"LOG.INFO: Created new user: {user_id} with {auth_provider}")
        return user
        
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to create user: {str(e)}")

def update_user(
    user_id: str,
    name: Optional[str] = None,
    age: Optional[int] = None,
    user_context_block: Optional[str] = None,
    selected_spurs: Optional[List[str]] = None,
    email: Optional[str] = None,
    auth_provider: Optional[str] = None,
    auth_provider_id: Optional[str] = None,
    using_trending_topics: Optional[bool] = None,
    model_temp_preference: Optional[float] = None
) -> UserProfile:
    """
    Update an existing user's information.
    
    Args:
        user_id: The unique user identifier
        name: User's display name (optional)
        age: User's age (optional)
        user_context_block: User's context/profile text (optional)
        selected_spurs: List of selected spur variants (optional)
        email: User's email (optional, usually shouldn't change)
        using_trending_topics: Whether the user is using trending topics (optional)
        model_temp_preference: User's model temperature preference (optional)
        
        
    Returns:
        Updated UserProfile object
        
    Raises:
        ValueError: If user doesn't exist
    """
    if not user_id:
        raise ValueError("user_id is required")
    
    # Get existing user
    user = get_user(user_id)
    if not user:
        raise ValueError(f"User not found: {user_id}")
    
    try:
        # Update fields if provided
        update_data = {}
        update_data.update({
            "updated_at": datetime.now(timezone.utc)
        })

        if name is not None:
            update_data.update({"name": name })
            user.name = name
        
        if age is not None:
            update_data.update({"age": str(age)})
            user.age = age
        
        if user_context_block is not None:
            update_data.update({"user_context_block": redact_flagged_sentences(user_context_block)})
            user.user_context_block = user_context_block
        
        if selected_spurs is not None:
            update_data.update({"selected_spurs": selected_spurs})
            user.selected_spurs = selected_spurs
        
        if email is not None:
            update_data.update({"email": email})
            user.email = email
        
        if auth_provider is not None:
            update_data.update({"auth_provider": auth_provider})
            user.auth_provider = auth_provider

        if auth_provider_id is not None:
            update_data.update({"auth_provider_id": auth_provider_id})
            user.auth_provider_id = auth_provider_id
        
        if using_trending_topics is not None:
            update_data.update({"using_trending_topics": using_trending_topics})
            user.using_trending_topics = using_trending_topics
            
        if model_temp_preference is not None:
            update_data.update({"model_temp_preference": model_temp_preference})
            user.model_temp_preference = model_temp_preference
            
    except Exception as e:
        logger.error(f"Error getting update_data for {user_id}: {str(e)}", exc_info=True)
        raise ValueError(f"Error getting update_data for user: {str(e)}")
    

    try:
        db = get_firestore_db()
        user_ref = db.collection("users").document(user_id)
        user_ref.update(update_data)
        
        logger.error(f"LOG.INFO: Updated user: {user_id}")
        return user
        
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to update user: {str(e)}")

def delete_user(user_id: str) -> Dict[str, str]:
    """
    Delete a user and all their related data from Firestore.

    This function recursively deletes all documents and subcollections under a user's
    main document to ensure all data is removed.

    Args:
        user_id: The unique user identifier.

    Returns:
        A dictionary with a status message confirming the deletion.

    Raises:
        ValueError: If the user_id is not provided or the user does not exist.
    """
    if not user_id:
        raise ValueError("user_id is required")

    user = get_user(user_id)
    if not user:
        raise ValueError(f"User not found: {user_id}")

    try:
        db = get_firestore_db()
        user_ref = db.collection("users").document(user_id)

        # Start the recursive deletion
        _delete_collection_recursively(user_ref)

        # Delete from Firebase Auth if using email provider
        if user.auth_provider == 'password':
            try:
                auth.delete_user(user.auth_provider_id)
                logger.error(f"LOG.INFO: Deleted Firebase Auth user: {user.auth_provider_id}")
            except Exception as e:
                logger.error(f"Failed to delete Firebase Auth user: {str(e)}")

        logger.error(f"LOG.INFO: Deleted user: {user_id}")
        return {"status": "User and all related data successfully deleted"}

    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to delete user: {str(e)}")


def _delete_collection_recursively(doc_ref):
    """
    Recursively delete a document and all its subcollections.

    Args:
        doc_ref: A reference to the document to delete.
    """
    # Get all subcollections of the document
    collections = doc_ref.collections()
    for collection in collections:
        # Get all documents in the subcollection
        docs = collection.stream()
        for doc in docs:
            # Recursively delete each document in the subcollection
            _delete_collection_recursively(doc.reference)

    # After all subcollections are deleted, delete the document itself
    doc_ref.delete()

def get_or_create_user_from_auth(
    user_id: str,
    email: str,
    auth_provider: str,
    auth_provider_id: str,
    name: Optional[str] = None
) -> UserProfile:
    """
    Get an existing user or create a new one based on authentication info.
    This is the main function to use during authentication flow.
    
    Args:
        email: User's email address
        auth_provider: Authentication provider
        auth_provider_id: Provider-specific ID
        name: User's display name (optional)
        
    Returns:
        UserProfile object (existing or newly created)
    """
    # First, try to find existing user
    existing_user = get_user_by_auth_provider(auth_provider, auth_provider_id)
    if existing_user:
        # Update email or name if they've changed
        needs_update = False
        if existing_user.email != email:
            existing_user.email = email
            needs_update = True
        if name and existing_user.name != name:
            existing_user.name = name
            needs_update = True
        
        if needs_update:
            return update_user(
                user_id=existing_user.user_id,
                email=email,
                name=name
            )
        
        return existing_user
    
    # Create new user
    return create_user(
        user_id=user_id,
        email=email,
        auth_provider=auth_provider,
        auth_provider_id=auth_provider_id,
        name=name
    )

# Utility functions for specific operations

def update_spur_preferences(user_id: str, selected_spurs: Optional[List[str]], using_trending_topics: Optional[bool] = False, model_temp_preference: Optional[float] = 1.05) -> UserProfile:
    """
    Update user's spur preferences.
    
    Args:
        user_id: The unique user identifier
        selected_spurs: List of selected spur variants
        using_trending_topics: Whether the user is using trending topics
        model_temp_preference: User's model temperature preference

    Returns:
        Updated UserProfile object
    """
    return update_user(user_id=user_id, selected_spurs=selected_spurs, using_trending_topics=using_trending_topics, model_temp_preference=model_temp_preference)

def get_selected_spurs(user_id: str) -> List[str]:
    """
    Get user's selected spur preferences.
    
    Args:
        user_id: The unique user identifier
        
    Returns:
        List of selected spur variants
        
    Raises:
        ValueError: If user doesn't exist
    """
    user = get_user(user_id)
    if not user:
        raise ValueError(f"UserProfile not found: {user_id}")
    
    return user.selected_spurs

def update_user_profile(user_id: str, name: str, age: int, user_context_block: Optional[str], selected_spurs: Optional[List[str]], email: Optional[str]) -> UserProfile:
    """
    Update user's profile information (typically called after onboarding).
    
    Args:
        user_id: The unique user identifier
        name: User's display name
        age: User's age
        user_context_block: User's context/profile text
        selected_spurs: List of selected spur variants

    Returns:
        Updated UserProfile object
    """
    
    return update_user(
        user_id=user_id,
        name=name,
        age=age,
        user_context_block=user_context_block,
        selected_spurs=selected_spurs,
        email=email
    )

def update_user_using_trending_topics(
    user_id: str,
    using_trending_topics: bool
) -> dict:
    """
    Update an existing user's information.
    
    Args:
        user_id: The unique user identifier
        using_trending_topics: Whether the user is using trending topics
        
    Returns:
        dict: Updated user information
        
    Raises:
        ValueError: If user doesn't exist
    """
    if not user_id:
        raise ValueError("user_id is required")
    
    # Get existing user
    user = get_user(user_id)
    if not user:
        raise ValueError(f"User not found: {user_id}")
    
    try:
        # Update fields if provided
        update_data = {}
        update_data.update({
            "updated_at": datetime.now(timezone.utc)
        })

        if using_trending_topics is not None:
            update_data.update({"using_trending_topics": using_trending_topics })

    except Exception as e:
        logger.error(f"Error getting update_data for {user_id}: {str(e)}", exc_info=True)
        raise ValueError(f"Error getting update_data for user: {str(e)}")
    

    try:
        db = get_firestore_db()
        user_ref = db.collection("users").document(user_id)
        user_ref.update(update_data)
        
        logger.error(f"LOG.INFO: Updated user: {user_id}")
        return {"user_id": user_id, "using_trending_topics": using_trending_topics}
        
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to update user: {str(e)}")

def update_user_model_temp_preference(
    user_id: str,
    model_temp_preference: float
) -> dict:
    """
    Update an existing user's information.
    
    Args:
        user_id: The unique user identifier
        model_temp_preference: The model temperature preference for the user

    Returns:
        dict: Updated user information
        
    Raises:
        ValueError: If user doesn't exist
    """
    if not user_id:
        raise ValueError("user_id is required")
    
    # Get existing user
    user = get_user(user_id)
    if not user:
        raise ValueError(f"User not found: {user_id}")
    
    try:
        # Update fields if provided
        update_data = {}
        update_data.update({
            "updated_at": datetime.now(timezone.utc)
        })

        if model_temp_preference is not None:
            update_data.update({"model_temp_preference": model_temp_preference })

    except Exception as e:
        logger.error(f"Error getting update_data for {user_id}: {str(e)}", exc_info=True)
        raise ValueError(f"Error getting update_data for user: {str(e)}")
    

    try:
        db = get_firestore_db()
        user_ref = db.collection("users").document(user_id)
        user_ref.update(update_data)
        
        logger.error(f"LOG.INFO: Updated user: {user_id}")
        return {"user_id": user_id, "model_temp_preference": model_temp_preference}

    except Exception as e:
        logger.error(f"Error updating user {user_id}: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to update user: {str(e)}")