"""
Utility for automatically tracking OpenAI API usage.

This module provides decorators and utilities to automatically track
OpenAI API calls and their token usage for billing purposes.
"""

import functools
from typing import Callable
from infrastructure.logger import get_logger
from services.billing_service import record_openai_usage

logger = get_logger(__name__)

def track_openai_usage(feature: str, endpoint: str = "chat/completions"):
    """
    Decorator to automatically track OpenAI API usage.
    
    Args:
        feature: Feature name (e.g., 'spur_generation', 'trait_inference')
        endpoint: API endpoint (e.g., 'chat/completions', 'moderations')
    
    Usage:
        @track_openai_usage('spur_generation')
        def generate_spurs(user_id, ...):
            # Function that makes OpenAI API calls
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract user_id from function arguments
            user_id = None
            
            # Try to find user_id in positional arguments
            if args and isinstance(args[0], str):
                user_id = args[0]
            # Try to find user_id in keyword arguments
            elif 'user_id' in kwargs:
                user_id = kwargs['user_id']
            
            if not user_id:
                logger.warning(f"No user_id found for {feature}, skipping usage tracking")
                return func(*args, **kwargs)
            
            try:
                # Call the original function
                result = func(*args, **kwargs)
                
                # If the function returns an OpenAI response object, track usage
                if hasattr(result, 'usage') and result.usage:
                    usage = result.usage
                    record_openai_usage(
                        user_id=user_id,
                        model=getattr(result, 'model', 'unknown'),
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens,
                        endpoint=endpoint,
                        feature=feature
                    )
                elif hasattr(result, 'choices') and result.choices:
                    # For chat completions, try to extract usage from response
                    try:
                        # This is a fallback for when usage is not directly available
                        # You might need to adjust based on your OpenAI client version
                        if hasattr(result, 'model'):
                            model = result.model
                        else:
                            model = 'gpt-4o'  # Default fallback
                        
                        # Estimate tokens if not available (rough approximation)
                        # This is not ideal but provides some tracking
                        estimated_tokens = 100  # Conservative estimate
                        record_openai_usage(
                            user_id=user_id,
                            model=model,
                            prompt_tokens=estimated_tokens,
                            completion_tokens=estimated_tokens,
                            endpoint=endpoint,
                            feature=feature
                        )
                    except Exception as e:
                        logger.warning(f"Failed to track usage for {feature}: {e}")
                
                return result
                
            except Exception as e:
                logger.error(f"Error in {feature} for user {user_id}: {e}")
                raise
        
        return wrapper
    return decorator

def track_openai_usage_manual(
    user_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    feature: str,
    endpoint: str = "chat/completions"
) -> None:
    """
    Manually track OpenAI API usage when automatic tracking is not possible.
    
    Args:
        user_id: User ID
        model: OpenAI model used
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        feature: Feature name
        endpoint: API endpoint
    """
    try:
        record_openai_usage(
            user_id=user_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            endpoint=endpoint,
            feature=feature
        )
    except Exception as e:
        logger.error(f"Failed to manually track usage for user {user_id}: {e}")

def estimate_tokens_from_text(text: str) -> int:
    """
    Rough estimation of tokens from text.
    This is a simple approximation - OpenAI's actual tokenization may differ.
    
    Args:
        text: Text to estimate tokens for
        
    Returns:
        Estimated number of tokens
    """
    if not text:
        return 0
    
    # Rough approximation: 1 token ≈ 4 characters for English text
    return len(text) // 4

def estimate_tokens_from_messages(messages: list) -> int:
    """
    Estimate tokens from a list of messages (for chat completions).
    
    Args:
        messages: List of message dictionaries with 'role' and 'content'
        
    Returns:
        Estimated number of tokens
    """
    total_tokens = 0
    
    for message in messages:
        if isinstance(message, dict):
            # Add tokens for role
            total_tokens += len(message.get('role', '')) // 4
            
            # Add tokens for content
            content = message.get('content', '')
            if isinstance(content, str):
                total_tokens += estimate_tokens_from_text(content)
            elif isinstance(content, list):
                # Handle multimodal content (text + images)
                for item in content:
                    if isinstance(item, dict):
                        if item.get('type') == 'text':
                            total_tokens += estimate_tokens_from_text(item.get('text', ''))
                        elif item.get('type') == 'image_url':
                            # Images add significant tokens (rough estimate)
                            total_tokens += 1000  # Conservative estimate for image processing
    
    return total_tokens 