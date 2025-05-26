"""
Defines base and derived dataclasses for handling user and connection profiles.

BaseProfile:
    name: Optional[str] - Optional name of the profile owner.
    age: [int] - age of the profile owner; must be >= 18.
    context_info: Optional[str] - Optional context information about the profile owner.
    personality_traits: Optional[List[str]] - Optional list of personality traits.
    
    to_dict returns a BaseProfile object formatted as a python dictionary.

UserProfile (inherits from BaseProfile):
    user_id: str - Unique identifier for the user.
    selected_spurs: List[str] - List of the spurs to be generated for a user. Default is all.

    from_dict converts a python dictionary into a custom UserProfile object.

ConnectionProfile (inherits from BaseProfile):
    connection_id: str - Unique identifier for the connection.
    user_id: str - Identifier for the associated user (each connection is linked to one user).
    profile_text_content: Optional[List[str]] - OCR'd text from connection profile images.
    profile_image_urls: Optional[List[str]] - URLs of connection profile pictures.
    

    from_dict converts a python dictionary into a custom ConnectionProfile object.
"""

from dataclasses import dataclass, field, fields
from typing import Optional, List, Dict, Any

@dataclass
class BaseProfile:
    name: Optional[str] = None
    age: Optional[int] = None
    context_info: Optional[str] = None

    def to_dict(self):
        # Ensure default_factory lists are included even if empty
        d = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, list) and not value and callable(f.default_factory):
                 d[f.name] = f.default_factory()
            else:
                 d[f.name] = value
        return d

@dataclass
class UserProfile(BaseProfile):
    user_id: str = ""
    selected_spurs: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data):
        # Filter out keys not in UserProfile to avoid errors if extra keys are present
        profile_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in profile_fields}
        return cls(**filtered_data)

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
        return "" if value is None else str(value)

@dataclass
class ConnectionProfile(BaseProfile):
    connection_id: str = ""
    # The associated user's ID; every connection must be linked to a user.
    user_id: str = ""
    # New fields for OCR'd text and profile picture URLs
    profile_text_content: Optional[List[str]] = field(default_factory=list)
    personality_traits: Optional[List[Dict[str, Any]]] = field(default_factory=list)


    @classmethod
    def from_dict(cls, data):
        # Filter out keys not in ConnectionProfile to avoid errors if extra keys are present
        profile_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in profile_fields}
        return cls(**filtered_data)

    @classmethod
    def get_attr_as_str(cls, profile_instance: "ConnectionProfile", attr_key: str) -> str:
        """
        Retrieve the value of an attribute from a given ConnectionProfile instance
        and return it as a string.

        Args:
            profile_instance (ConnectionProfile): The profile object to inspect.
            attr_key (str): The attribute name to retrieve.

        Returns:
            str: The attribute value converted to a string, or an empty string if
                 the attribute does not exist or is None.
        """
        value = getattr(profile_instance, attr_key, None)
        return "" if value is None else str(value)