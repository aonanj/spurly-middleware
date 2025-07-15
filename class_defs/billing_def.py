"""
Defines dataclasses for handling OpenAI API usage tracking and billing.

UsageRecord:
    user_id: str - Unique identifier for the user.
    request_id: str - Unique identifier for the API request.
    model: str - OpenAI model used (e.g., 'gpt-4o', 'gpt-4o-mini').
    prompt_tokens: int - Number of tokens in the prompt.
    completion_tokens: int - Number of tokens in the completion.
    total_tokens: int - Total tokens used.
    cost_usd: float - Cost in USD for this request.
    endpoint: str - API endpoint used (e.g., 'chat/completions', 'moderations').
    feature: str - Feature that triggered the API call (e.g., 'spur_generation', 'trait_inference').
    created_at: datetime - Timestamp of when the request was made.

BillingProfile:
    user_id: str - Unique identifier for the user.
    subscription_tier: str - Subscription tier (e.g., 'free', 'basic', 'premium').
    weekly_token_limit: int - Weekly token allowance.
    current_week_tokens: int - Tokens used in current billing cycle.
    current_week_cost: float - Cost incurred in current billing cycle.
    billing_cycle_start: datetime - Start of current billing cycle.
    billing_cycle_end: datetime - End of current billing cycle.
    payment_method_id: Optional[str] - Payment method identifier.
    auto_renew: bool - Whether subscription auto-renews.
    created_at: datetime - Timestamp of when the billing profile was created.
    updated_at: datetime - Timestamp of when the billing profile was last updated.
"""

from dataclasses import dataclass, field, fields
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from dataclasses import asdict
import json

@dataclass
class UsageRecord:
    """Record of a single OpenAI API usage event"""
    user_id: str
    request_id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    endpoint: str
    feature: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert usage record to dictionary for Firestore"""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UsageRecord':
        """Create UsageRecord from dictionary"""
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        profile_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in profile_fields}
        return cls(**filtered_data)

@dataclass
class BillingProfile:
    """User billing profile and subscription information"""
    user_id: str
    subscription_tier: str = "free"  # free, basic, premium
    weekly_token_limit: int = 0  # Default free tier limit (weekly)
    current_week_tokens: int = 0
    current_week_cost: float = 0.0
    billing_cycle_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    billing_cycle_end: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payment_method_id: Optional[str] = None
    auto_renew: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert billing profile to dictionary for Firestore"""
        data = asdict(self)
        data['billing_cycle_start'] = self.billing_cycle_start.isoformat()
        data['billing_cycle_end'] = self.billing_cycle_end.isoformat()
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BillingProfile':
        """Create BillingProfile from dictionary"""
        # Convert ISO strings back to datetime objects
        datetime_fields = ['billing_cycle_start', 'billing_cycle_end', 'created_at', 'updated_at']
        for field_name in datetime_fields:
            if isinstance(data.get(field_name), str):
                data[field_name] = datetime.fromisoformat(data[field_name])
        
        # Handle migration from old monthly field names to new weekly field names
        if 'monthly_token_limit' in data and 'weekly_token_limit' not in data:
            data['weekly_token_limit'] = data.pop('monthly_token_limit')
        if 'current_month_tokens' in data and 'current_week_tokens' not in data:
            data['current_week_tokens'] = data.pop('current_month_tokens')
        if 'current_month_cost' in data and 'current_week_cost' not in data:
            data['current_week_cost'] = data.pop('current_month_cost')
        
        profile_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in profile_fields}
        return cls(**filtered_data)

    def get_remaining_tokens(self) -> int:
        """Get remaining tokens for current billing cycle"""
        return max(0, self.weekly_token_limit - self.current_week_tokens)
    
    def get_usage_percentage(self) -> float:
        """Get usage as percentage of weekly limit"""
        if self.weekly_token_limit == 0:
            return 0.0
        return min(100.0, (self.current_week_tokens / self.weekly_token_limit) * 100)
    
    def is_over_limit(self) -> bool:
        """Check if user has exceeded weekly token limit"""
        return self.current_week_tokens >= self.weekly_token_limit

# OpenAI pricing constants (as of 2024)
OPENAI_PRICING = {
    "gpt-4o": {
        "input": 0.0025,  # per 1K tokens
        "output": 0.01    # per 1K tokens
    },
    "gpt-4o-mini": {
        "input": 0.00015,  # per 1K tokens
        "output": 0.0006   # per 1K tokens
    },
    "gpt-4-turbo": {
        "input": 0.01,     # per 1K tokens
        "output": 0.03     # per 1K tokens
    }
}

# Subscription tier definitions (weekly limits)
SUBSCRIPTION_TIERS = {
    "free": {
        "weekly_token_limit": 0,  
        "weekly_cost": 0.0,
        "features": ["basic_spur_generation", "limited_trait_inference"]
    },
    "com.phaeton.order.spurly.subscription.basic": {
        "weekly_token_limit": 25000,   
        "weekly_cost": 4.99,  
        "features": ["20_spurs_weekly", "trait_inference", "conversation_analysis"]
    },
    "com.phaeton.order.spurly.subscription.premium": {
        "weekly_token_limit": 100000,  # 
        "weekly_cost": 7.99,  
        "features": ["80_spurs_weekly", "trait_inference", "conversation_analysis", "priority_support"]
    }
} 