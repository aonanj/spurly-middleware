"""
Defines base and derived dataclasses for handling user and connection profiles.

BaseProfile:

    personality_traits: Optional[List[str]] - Optional list of personality traits.
    
    to_dict returns a BaseProfile object formatted as a python dictionary.

UserProfile:
    user_id: str - Unique identifier for the user.
    email: str - Email address of the user.
    name: Optional[str] - Optional name of the profile owner.
    age: [int] - age of the profile owner; must be >= 18.
    user_context_block: Optional[str] - Optional context information about the profile owner.
    selected_spurs: List[str] - List of the spurs to be generated for a user. Default is all.
    created_at: datetime - Timestamp of when the profile was created.
    updated_at: datetime - Timestamp of when the profile was last updated.
    auth_provider: str - Authentication provider (e.g., 'email', 'google.com', 'apple.com', 'facebook.com').
    auth_provider_id: str - Unique identifier for the user in the authentication provider (e.g., Firebase UID).

    from_dict converts a python dictionary into a custom UserProfile object.
    to_dict converts a UserProfile object into a python dictionary for Firestore.
    to_dict_deprecated converts a UserProfile object into a python dictionary for Firestore with deprecated handling.
    get_attr_as_str retrieves the value of an attribute from a UserProfile instance and returns it as a string.

ConnectionProfile:
    user_id: str - Unique identifier for the user associated with the connection.
    connection_id: str - Unique identifier for the connection.
    name: Optional[str] - Optional name of the connection profile owner.
    age: Optional[int] - Optional age of the connection profile owner; must be >= 18.
    connection_context_block: Optional[str] - Optional context information about the connection profile owner.
    connection_profile_text: Optional[List[str]] - OCR'd text from connection profile images.
    personality_traits: Optional[List[Dict[str, Any]]] - Optional list of personality traits for the connection.
    created_at: datetime - Timestamp of when the connection profile was created.
    updated_at: datetime - Timestamp of when the connection profile was last updated.

    from_dict converts a python dictionary into a custom ConnectionProfile object.
    to_dict converts a ConnectionProfile object into a python dictionary for Firestore.
    to_dict_deprecated converts a ConnectionProfile object into a python dictionary for Firestore with deprecated handling.
    get_attr_as_str retrieves the value of an attribute from a ConnectionProfile instance and returns it as a string.
"""

from dataclasses import dataclass, field, fields
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from dataclasses import asdict
import json

@dataclass
class UserProfile:
    """Unified UserProfile model for all authentication providers"""
    user_id: str
    email: str
    auth_provider: Optional[str]  # 'email', 'google.com', 'apple.com', 'facebook.com'
    auth_provider_id: Optional[str]  # Firebase UID or provider-specific ID
    name: Optional[str] = None
    age: Optional[int] = None
    user_context_block: Optional[str] = None
    selected_spurs: List[str] = field(default_factory=list)
    using_trending_topics: Optional[bool] = False
    model_temp_preference: Optional[float] = 1.05
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert user object to dictionary for Firestore"""
        data = asdict(self)
        data.pop('_use_trending_topics', None) 
        data.pop('_model_temp_preference', None)
        # Convert datetime objects to ISO format strings
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserProfile':
        """Create User object from dictionary"""

        # Convert ISO strings back to datetime objects if needed
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
          
        profile_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in profile_fields}
        return cls(**filtered_data)

    def isUsingTrendingTopics(self) -> bool:
        """Check if the user has opted to use trending topics"""
        return self.using_trending_topics if self.using_trending_topics is not None else False

    def getModelTempPreference(self) -> float:
        """Get the user's model temperature preference"""
        return self.model_temp_preference if self.model_temp_preference is not None else 1.0

    
    @classmethod
    def get_attr_as_str(cls, profile_instance: "UserProfile", attr_key: str) -> str:
        """
        Retrieve the value of an attribute from a given UserProfile instance
        and return it as a string.

        Args:
            profile_instance (UserProfile): The profile object to inspect.
            attr_key (str): The attribute name to retrieve.

        Returns:
            str: The attribute value converted to a string, or an empty string if
                 the attribute does not exist or is None.
        """
        value = getattr(profile_instance, attr_key, None)
        if isinstance(value, list):
            str_list = [str(item) for item in value if item is not None]
            return ", ".join(str_list) if str_list else ""
        else:
            return "" if value is None else str(value)

# Updated class_defs/profile_def.py - ConnectionProfile section

@dataclass
class ConnectionProfile:
    user_id: str
    connection_id: str
    connection_name: Optional[str] = None
    connection_age: Optional[int] = None
    connection_context_block: Optional[str] = None
    connection_profile_text: Optional[List[str]] = field(default_factory=list)
    personality_traits: Optional[List[Dict[str, Any]]] = field(default_factory=list)
    connection_profile_pic_url: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user object to dictionary for Firestore"""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        
        if data.get('personality_traits'):
            for trait in data['personality_traits']:
                if 'confidence' in trait and isinstance(trait['confidence'], float):
                    trait['confidence'] = f"{trait['confidence']:.2f}"
                    
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConnectionProfile':
        """Create User object from dictionary"""
        # Convert ISO strings back to datetime objects if needed
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        profile_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in profile_fields}
        return cls(**filtered_data)

    
    @classmethod
    def get_attr_as_str(cls, profile_instance: "ConnectionProfile", attr_key: str) -> str:
        """
        Retrieve the value of an attribute from a given ConnectionProfile instance
        and return it as a string. For 'personality_traits', it converts confidence
        scores to strings before serializing the list to a JSON string.

        Args:
            profile_instance (ConnectionProfile): The profile object to inspect.
            attr_key (str): The attribute name to retrieve.

        Returns:
            str: The attribute value converted to a string, or an empty string if
                 the attribute does not exist or is None.
        """
        value = getattr(profile_instance, attr_key, None)

        if value is None:
            return ""

        # Special handling for personality_traits to format it as a JSON string
        # with confidence scores converted from float to string.
        if attr_key == 'personality_traits' and isinstance(value, list):
            if not value:
                return "[]"
            
            # Create a copy to avoid modifying the original object's data
            traits_copy = [item.copy() for item in value if isinstance(item, dict)]
            
            for trait in traits_copy:
                if 'confidence' in trait and isinstance(trait.get('confidence'), float):
                    trait['confidence'] = f"{trait['confidence']:.2f}"
            
            return json.dumps(traits_copy, indent=4)

        if isinstance(value, list):
            # General list handling for other attributes
            str_list = [str(item) for item in value if item is not None]
            return ", ".join(str_list) if str_list else ""
        elif isinstance(value, dict):
            # General dictionary handling
            return json.dumps(value, indent=4) if value else ""
        else:
            return str(value)