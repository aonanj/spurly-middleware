"""
Middleware for checking usage limits before processing requests.

This module provides decorators and utilities to check if users
have exceeded their usage limits before allowing OpenAI API calls.
"""

from functools import wraps
from flask import g, jsonify
from typing import Optional
from infrastructure.logger import get_logger
from services.billing_service import check_user_usage_limit

logger = get_logger(__name__)

def check_usage_limit(estimated_tokens: int = 1000):
    """
    Decorator to check if user has sufficient tokens before processing request.
    
    Args:
        required_tokens: Estimated tokens needed for the operation
        
    Usage:
        @check_usage_limit(2000)
        def generate_spurs(user_id, ...):
            # Function that makes OpenAI API calls
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract user_id from function arguments
            user_id = None
            
            # Try to find user_id in positional arguments
            if args and isinstance(args[0], str):
                user_id = args[0]
            # Try to find user_id in keyword arguments
            elif 'user_id' in kwargs:
                user_id = kwargs['user_id']
            # Try to get from Flask g context
            elif hasattr(g, 'user_id'):
                user_id = g.user_id
            
            if not user_id:
                logger.warning(f"No user_id found for {func.__name__}, skipping usage check")
                return func(*args, **kwargs)
            
            try:
                # Check usage limits
                limit_status = check_user_usage_limit(user_id)
                
                if "error" in limit_status:
                    logger.error(f"Error checking usage limit for user {user_id}: {limit_status['error']}")
                    return func(*args, **kwargs)  # Continue anyway
                
                remaining_tokens = limit_status.get("remaining_tokens", 0)
                token_margin = remaining_tokens * 0.1  # 10% margin
        
                if remaining_tokens < (estimated_tokens - token_margin):
                    logger.error(f"User {user_id} has insufficient tokens: {remaining_tokens} < {estimated_tokens}")
                    
                    # Return error response for API endpoints
                    if hasattr(g, 'request'):
                        return jsonify({
                            "error": "Insufficient tokens",
                            "message": f"You have {remaining_tokens} tokens remaining, but {estimated_tokens} are required for this operation.",
                            "remaining_tokens": remaining_tokens,
                            "estimated_tokens": estimated_tokens,
                            "subscription_tier": limit_status.get("subscription_tier", "unknown"),
                            "upgrade_required": True
                        }), 402  # Payment Required
                    
                    # For non-API calls, raise an exception
                    raise ValueError(f"Insufficient tokens: {remaining_tokens} < {estimated_tokens}")

                return func(*args, **kwargs)
                
            except Exception as e:
                logger.error(f"Error in usage limit check for user {user_id}: {e}")
                # Continue with the function if there's an error checking limits
                return func(*args, **kwargs)
        
        return wrapper
    return decorator

def check_usage_limit_api(estimated_tokens: int = 1000):
    """
    Decorator specifically for API endpoints to check usage limits.
    
    Args:
        estimated_tokens: Estimated tokens needed for the operation
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user_id = getattr(g, "user_id", None)
            if not user_id:
                return jsonify({"error": "Invalid authentication state"}), 401
            
            try:
                # Check usage limits
                limit_status = check_user_usage_limit(user_id)
                
                if "error" in limit_status:
                    logger.error(f"Error checking usage limit for user {user_id}: {limit_status['error']}")
                    return func(*args, **kwargs)  # Continue anyway
                
                remaining_tokens = limit_status.get("remaining_tokens", 0)
                token_margin = remaining_tokens * 0.1  # 10% margin
        
                if remaining_tokens < (estimated_tokens - token_margin):
                    logger.error(f"User {user_id} has insufficient tokens: {remaining_tokens} < {estimated_tokens}")

                    return jsonify({
                        "error": "Insufficient tokens",
                        "message": f"You have {remaining_tokens} tokens remaining, but {estimated_tokens} are required for this operation.",
                        "remaining_tokens": remaining_tokens,
                        "estimated_tokens": estimated_tokens,
                        "subscription_tier": limit_status.get("subscription_tier", "unknown"),
                        "usage_percentage": limit_status.get("usage_percentage", 0),
                        "upgrade_required": True
                    }), 402  # Payment Required
                
                return func(*args, **kwargs)
                
            except Exception as e:
                logger.error(f"Error in usage limit check for user {user_id}: {e}")
                # Continue with the function if there's an error checking limits
                return func(*args, **kwargs)
        
        return wrapper
    return decorator

def estimate_spur_generation_tokens(
    conversation_messages: Optional[list] = None,
    conversation_images: Optional[list] = None,
    profile_images: Optional[list] = None
) -> int:
    """
    Estimate tokens needed for spur generation based on input complexity.
    
    Args:
        conversation_messages: List of conversation messages
        conversation_images: List of conversation images
        profile_images: List of profile images
        
    Returns:
        Estimated tokens needed
    """
    base_tokens = 2000  # Base tokens for system prompt and basic generation
    
    # Add tokens for conversation messages
    if conversation_messages:
        for message in conversation_messages:
            content = message.get('content', '')
            if isinstance(content, str):
                base_tokens += len(content) // 4  # Rough token estimation
    
    # Add tokens for images (significant cost for vision models)
    if conversation_images:
        base_tokens += len(conversation_images) * 1000  # ~1000 tokens per image
    
    if profile_images:
        base_tokens += len(profile_images) * 1000  # ~1000 tokens per image
    
    # Add buffer for completion tokens
    completion_tokens = 2000  # Conservative estimate for spur generation
    
    return base_tokens + completion_tokens

def estimate_trait_inference_tokens(num_images: int) -> int:
    """
    Estimate tokens needed for personality trait inference.
    
    Args:
        num_images: Number of images to analyze
        
    Returns:
        Estimated tokens needed
    """
    base_tokens = 1000  # Base tokens for system prompt
    image_tokens = num_images * 1000  # ~1000 tokens per image
    completion_tokens = 500  # Conservative estimate for trait inference
    
    return base_tokens + image_tokens + completion_tokens 