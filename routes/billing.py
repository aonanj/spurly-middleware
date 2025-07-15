"""
API routes for billing and usage management.

This module provides endpoints for:
- Getting user usage statistics
- Checking usage limits
- Managing subscription tiers
- Viewing billing history
"""

from flask import Blueprint, request, jsonify, g
from infrastructure.token_validator import verify_token, handle_all_errors, verify_app_check_token
from infrastructure.logger import get_logger
from services.billing_service import (
    get_user_usage_summary,
    check_user_usage_limit,
    upgrade_subscription,
    get_or_create_billing_profile
)
from class_defs.billing_def import SUBSCRIPTION_TIERS

logger = get_logger(__name__)

billing_bp = Blueprint("billing", __name__)

@billing_bp.route("/api/billing/usage", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def get_usage():
    """
    Get current user's usage statistics.
    
    Query parameters:
        days (int, optional): Number of days to look back (default: 30)
    
    Returns:
        JSON response with usage summary
    """
    user_id = getattr(g, "user_id", None)
    if not user_id:
        return jsonify({"error": "Invalid authentication state"}), 401
    
    try:
        # Get days parameter
        days = request.args.get("days", 7, type=int)
        if days <= 0 or days > 365:
            days = 30  # Default to 30 days if invalid
        
        usage_summary = get_user_usage_summary(user_id, days)
        
        return jsonify({
            "success": True,
            "usage": usage_summary
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting usage for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to get usage statistics"}), 500

@billing_bp.route("/api/billing/limits", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def get_limits():
    """
    Get current user's usage limits and status.
    
    Returns:
        JSON response with limit information
    """
    user_id = getattr(g, "user_id", None)
    if not user_id:
        return jsonify({"error": "Invalid authentication state"}), 401
    
    try:
        limit_status = check_user_usage_limit(user_id)
        
        if "error" in limit_status:
            return jsonify({"error": limit_status["error"]}), 500
        
        return jsonify({
            "success": True,
            "limits": limit_status
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting limits for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to get usage limits"}), 500

@billing_bp.route("/api/billing/subscription", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def get_subscription():
    """
    Get current user's subscription information.
    
    Returns:
        JSON response with subscription details
    """
    user_id = getattr(g, "user_id", None)
    if not user_id:
        return jsonify({"error": "Invalid authentication state"}), 401
    
    try:
        billing_profile = get_or_create_billing_profile(user_id)
        
        return jsonify({
            "success": True,
            "subscription": {
                "tier": billing_profile.subscription_tier,
                "weekly_limit": billing_profile.weekly_token_limit,
                "current_usage": billing_profile.current_week_tokens,
                "remaining_tokens": billing_profile.get_remaining_tokens(),
                "usage_percentage": billing_profile.get_usage_percentage(),
                "current_cost": billing_profile.current_week_cost,
                "billing_cycle_start": billing_profile.billing_cycle_start.isoformat(),
                "billing_cycle_end": billing_profile.billing_cycle_end.isoformat(),
                "auto_renew": billing_profile.auto_renew
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting subscription for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to get subscription information"}), 500

@billing_bp.route("/api/billing/subscription", methods=["POST"])
@handle_all_errors
@verify_token
@verify_app_check_token
def upgrade_subscription_route():
    """
    Upgrade user's subscription tier.
    
    Expected JSON payload:
    {
        "tier": "basic" | "premium"
    }
    
    Returns:
        JSON response with updated subscription
    """
    user_id = getattr(g, "user_id", None)
    if not user_id:
        return jsonify({"error": "Invalid authentication state"}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    
    new_tier = data.get("tier")
    if not new_tier:
        return jsonify({"error": "Tier is required"}), 400
    
    if new_tier not in SUBSCRIPTION_TIERS:
        return jsonify({"error": f"Invalid tier. Must be one of: {list(SUBSCRIPTION_TIERS.keys())}"}), 400
    
    try:
        billing_profile = upgrade_subscription(user_id, new_tier)
        
        return jsonify({
            "success": True,
            "message": f"Successfully upgraded to {new_tier} tier",
            "subscription": {
                "tier": billing_profile.subscription_tier,
                "weekly_limit": billing_profile.weekly_token_limit,
                "current_usage": billing_profile.current_week_tokens,
                "remaining_tokens": billing_profile.get_remaining_tokens(),
                "usage_percentage": billing_profile.get_usage_percentage(),
                "current_cost": billing_profile.current_week_cost,
                "billing_cycle_start": billing_profile.billing_cycle_start.isoformat(),
                "billing_cycle_end": billing_profile.billing_cycle_end.isoformat()
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error upgrading subscription for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to upgrade subscription"}), 500

@billing_bp.route("/api/billing/tiers", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def get_available_tiers():
    """
    Get available subscription tiers and their features.
    
    Returns:
        JSON response with tier information
    """
    try:
        # Remove sensitive information from tiers
        public_tiers = {}
        for tier_name, tier_config in SUBSCRIPTION_TIERS.items():
            public_tiers[tier_name] = {
                "weekly_token_limit": tier_config["weekly_token_limit"],
                "weekly_cost": tier_config["weekly_cost"],
                "features": tier_config["features"]
            }
        
        return jsonify({
            "success": True,
            "tiers": public_tiers
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting available tiers: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to get tier information"}), 500

@billing_bp.route("/api/billing/history", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def get_billing_history():
    """
    Get user's billing history (usage records).
    
    Query parameters:
        days (int, optional): Number of days to look back (default: 30)
        limit (int, optional): Maximum number of records to return (default: 50, max: 100)
    
    Returns:
        JSON response with billing history
    """
    user_id = getattr(g, "user_id", None)
    if not user_id:
        return jsonify({"error": "Invalid authentication state"}), 401
    
    try:
        # Get query parameters
        days = request.args.get("days", 30, type=int)
        limit = request.args.get("limit", 50, type=int)
        
        if days <= 0 or days > 365:
            days = 30
        if limit <= 0 or limit > 100:
            limit = 50
        
        # Get usage summary for the period
        usage_summary = get_user_usage_summary(user_id, days)
        
        return jsonify({
            "success": True,
            "history": {
                "period_days": days,
                "total_tokens": usage_summary["total_tokens"],
                "total_cost": usage_summary["total_cost"],
                "feature_breakdown": usage_summary["feature_breakdown"],
                "model_breakdown": usage_summary["model_breakdown"]
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting billing history for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to get billing history"}), 500 