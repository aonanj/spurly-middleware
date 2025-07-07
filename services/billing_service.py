"""
Service for handling OpenAI API usage tracking and billing operations.

This service provides functionality to:
- Track OpenAI API usage per user
- Calculate costs based on token usage
- Manage billing profiles and subscription tiers
- Handle usage limits and overage charges
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from infrastructure.logger import get_logger
from infrastructure.clients import get_firestore_db
from class_defs.billing_def import (
    UsageRecord, 
    BillingProfile, 
    OPENAI_PRICING, 
    SUBSCRIPTION_TIERS
)

logger = get_logger(__name__)

def calculate_openai_cost(
    model: str, 
    prompt_tokens: int, 
    completion_tokens: int
) -> float:
    """
    Calculate the cost of an OpenAI API call.
    
    Args:
        model: OpenAI model used (e.g., 'gpt-4o', 'gpt-4o-mini')
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        
    Returns:
        Cost in USD
    """
    if model not in OPENAI_PRICING:
        logger.warning(f"Unknown model {model}, using gpt-4o pricing")
        model = "gpt-4o"
    
    pricing = OPENAI_PRICING[model]
    
    # Calculate costs (pricing is per 1K tokens)
    input_cost = (prompt_tokens / 1000) * pricing["input"]
    output_cost = (completion_tokens / 1000) * pricing["output"]
    
    total_cost = input_cost + output_cost
    return round(total_cost, 6)  # Round to 6 decimal places for precision

def record_openai_usage(
    user_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    endpoint: str,
    feature: str
) -> UsageRecord:
    """
    Record an OpenAI API usage event.
    
    Args:
        user_id: User ID
        model: OpenAI model used
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        endpoint: API endpoint (e.g., 'chat/completions')
        feature: Feature that triggered the call (e.g., 'spur_generation')
        
    Returns:
        UsageRecord object
    """
    total_tokens = prompt_tokens + completion_tokens
    cost_usd = calculate_openai_cost(model, prompt_tokens, completion_tokens)
    request_id = str(uuid.uuid4())
    
    usage_record = UsageRecord(
        user_id=user_id,
        request_id=request_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        endpoint=endpoint,
        feature=feature
    )
    
    try:
        # Save to Firestore
        db = get_firestore_db()
        usage_ref = db.collection("users").document(user_id).collection("usage").document(request_id)
        usage_ref.set(usage_record.to_dict())
        
        # Update billing profile
        update_billing_profile_usage(user_id, total_tokens, cost_usd)
        
        logger.info(f"Recorded usage for user {user_id}: {total_tokens} tokens, ${cost_usd:.6f}")
        return usage_record
        
    except Exception as e:
        logger.error(f"Failed to record usage for user {user_id}: {e}", exc_info=True)
        raise

def get_or_create_billing_profile(user_id: str) -> BillingProfile:
    """
    Get or create a billing profile for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        BillingProfile object
    """
    try:
        db = get_firestore_db()
        billing_ref = db.collection("users").document(user_id).collection("billing").document("profile")
        doc = billing_ref.get()
        
        if doc.exists:
            data = doc.to_dict()
            billing_profile = BillingProfile.from_dict(data)
            
            # Check if billing cycle needs to be reset
            if datetime.now(timezone.utc) >= billing_profile.billing_cycle_end:
                billing_profile = reset_billing_cycle(billing_profile)
                billing_ref.set(billing_profile.to_dict())
            
            return billing_profile
        else:
            # Create new billing profile
            billing_profile = BillingProfile(user_id=user_id)
            billing_ref.set(billing_profile.to_dict())
            logger.info(f"Created new billing profile for user {user_id}")
            return billing_profile
            
    except Exception as e:
        logger.error(f"Failed to get/create billing profile for user {user_id}: {e}", exc_info=True)
        raise

def update_billing_profile_usage(user_id: str, tokens: int, cost: float) -> None:
    """
    Update a user's billing profile with new usage.
    
    Args:
        user_id: User ID
        tokens: Number of tokens used
        cost: Cost in USD
    """
    try:
        db = get_firestore_db()
        billing_ref = db.collection("users").document(user_id).collection("billing").document("profile")
        
        # Get current billing profile
        doc = billing_ref.get()
        if doc.exists:
            data = doc.to_dict()
            billing_profile = BillingProfile.from_dict(data)
            
            # Check if billing cycle needs reset
            if datetime.now(timezone.utc) >= billing_profile.billing_cycle_end:
                billing_profile = reset_billing_cycle(billing_profile)
            
            # Update usage
            billing_profile.current_week_tokens += tokens
            billing_profile.current_week_cost += cost
            billing_profile.updated_at = datetime.now(timezone.utc)
            
            # Update the document
            billing_ref.set(billing_profile.to_dict())
        else:
            # Create new profile if doesn't exist
            billing_profile = BillingProfile(user_id=user_id)
            billing_profile.current_week_tokens = tokens
            billing_profile.current_week_cost = cost
            billing_ref.set(billing_profile.to_dict())
        
    except Exception as e:
        logger.error(f"Failed to update billing profile for user {user_id}: {e}", exc_info=True)
        raise

def reset_billing_cycle(billing_profile: BillingProfile) -> BillingProfile:
    """
    Reset a billing profile for a new billing cycle.
    
    Args:
        billing_profile: Current billing profile
        
    Returns:
        Updated billing profile
    """
    now = datetime.now(timezone.utc)
    
    # Calculate next billing cycle (weekly)
    if billing_profile.billing_cycle_end <= now:
        # Start new billing cycle
        billing_profile.billing_cycle_start = now
        billing_profile.billing_cycle_end = now + timedelta(days=7)
        billing_profile.current_week_tokens = 0
        billing_profile.current_week_cost = 0.0
        billing_profile.updated_at = now
        
        logger.info(f"Reset billing cycle for user {billing_profile.user_id}")
    
    return billing_profile

def get_user_usage_summary(user_id: str, days: int = 30) -> Dict[str, Any]:
    """
    Get a summary of user's usage for the specified period.
    
    Args:
        user_id: User ID
        days: Number of days to look back
        
    Returns:
        Dictionary with usage summary
    """
    try:
        db = get_firestore_db()
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Get usage records
        usage_ref = db.collection("users").document(user_id).collection("usage")
        query = usage_ref.where("created_at", ">=", cutoff_date.isoformat())
        docs = query.stream()
        
        total_tokens = 0
        total_cost = 0.0
        feature_breakdown = {}
        model_breakdown = {}
        
        for doc in docs:
            data = doc.to_dict()
            usage_record = UsageRecord.from_dict(data)
            
            total_tokens += usage_record.total_tokens
            total_cost += usage_record.cost_usd
            
            # Feature breakdown
            feature = usage_record.feature
            if feature not in feature_breakdown:
                feature_breakdown[feature] = {"tokens": 0, "cost": 0.0, "requests": 0}
            feature_breakdown[feature]["tokens"] += usage_record.total_tokens
            feature_breakdown[feature]["cost"] += usage_record.cost_usd
            feature_breakdown[feature]["requests"] += 1
            
            # Model breakdown
            model = usage_record.model
            if model not in model_breakdown:
                model_breakdown[model] = {"tokens": 0, "cost": 0.0, "requests": 0}
            model_breakdown[model]["tokens"] += usage_record.total_tokens
            model_breakdown[model]["cost"] += usage_record.cost_usd
            model_breakdown[model]["requests"] += 1
        
        return {
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
            "feature_breakdown": feature_breakdown,
            "model_breakdown": model_breakdown,
            "period_days": days
        }
        
    except Exception as e:
        logger.error(f"Failed to get usage summary for user {user_id}: {e}", exc_info=True)
        return {
            "total_tokens": 0,
            "total_cost": 0.0,
            "feature_breakdown": {},
            "model_breakdown": {},
            "period_days": days
        }

def check_user_usage_limit(user_id: str) -> Dict[str, Any]:
    """
    Check if user has exceeded their usage limit.
    
    Args:
        user_id: User ID
        
    Returns:
        Dictionary with limit status
    """
    try:
        billing_profile = get_or_create_billing_profile(user_id)
        
        return {
            "user_id": user_id,
            "subscription_tier": billing_profile.subscription_tier,
            "weekly_limit": billing_profile.weekly_token_limit,
            "current_usage": billing_profile.current_week_tokens,
            "remaining_tokens": billing_profile.get_remaining_tokens(),
            "usage_percentage": billing_profile.get_usage_percentage(),
            "is_over_limit": billing_profile.is_over_limit(),
            "current_cost": billing_profile.current_week_cost,
            "billing_cycle_end": billing_profile.billing_cycle_end.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to check usage limit for user {user_id}: {e}", exc_info=True)
        return {
            "user_id": user_id,
            "error": str(e)
        }

def upgrade_subscription(user_id: str, new_tier: str) -> BillingProfile:
    """
    Upgrade a user's subscription tier.
    
    Args:
        user_id: User ID
        new_tier: New subscription tier
        
    Returns:
        Updated BillingProfile
    """
    if new_tier not in SUBSCRIPTION_TIERS:
        raise ValueError(f"Invalid subscription tier: {new_tier}")
    
    try:
        billing_profile = get_or_create_billing_profile(user_id)
        tier_config = SUBSCRIPTION_TIERS[new_tier]
        
        billing_profile.subscription_tier = new_tier
        billing_profile.weekly_token_limit = tier_config["weekly_token_limit"]
        billing_profile.updated_at = datetime.now(timezone.utc)
        
        # Save to Firestore
        db = get_firestore_db()
        billing_ref = db.collection("users").document(user_id).collection("billing").document("profile")
        billing_ref.set(billing_profile.to_dict())
        
        logger.info(f"Upgraded user {user_id} to {new_tier} tier")
        return billing_profile
        
    except Exception as e:
        logger.error(f"Failed to upgrade subscription for user {user_id}: {e}", exc_info=True)
        raise 