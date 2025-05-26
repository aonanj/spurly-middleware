"""
Defines a dataclass named Spur with the following fields:
    user_id: User ID (string)
    spur_id: Spur ID (string)
    conversation_id: Conversation ID (string). Concatenates user_id, ":", and a UUID4.
    conversation: List of message dictionaries representing the conversation between the user and a connection.
    connection_id: Optional identifier for the connection (string) involved in the conversation.
    situation: Optional description of the contextual situation of the conversation (string).
    topic: Optional subject or theme of the conversation (string).
    variant: spur variant type of this spur.
    text: text of the spur.
    created_at: Datetime indicating when spur was generated.
    
    to_dict returns a Spur object formatted as a python dictionary.
    from_dict converts a python dictionary into a custom Spur object.

"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

@dataclass
class Spur:
    user_id: str
    spur_id: str
    created_at: datetime
    conversation_id: Optional[str] = None
    connection_id: Optional[str] = None
    situation: Optional[str] = None
    topic: Optional[str] = None
    variant: Optional[str] = None
    tone: Optional[str] = None
    text: Optional[str] = None

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "spur_id": self.spur_id,
            "conversation_id": self.conversation_id,
            "connection_id": self.connection_id,
            "situation": self.situation,
            "topic": self.topic,
            "variant": self.variant,
            "tone": self.tone,
            "text": self.text,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z") if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data):
        created_at_str = data.get("created_at")

        return cls(
            user_id=data["user_id"],
            spur_id=data["spur_id"],
            conversation_id=data.get("conversation_id"),
            connection_id=data.get("connection_id"),
            situation=data.get("situation"),
            topic=data.get("topic"),
            variant=data.get("variant"),
            tone=data.get("tone"),
            text=data.get("text"),
            created_at=datetime.fromisoformat(created_at_str.replace("Z", "+00:00")) or datetime.now(timezone.utc)
        )

    @classmethod
    def get_attr(cls, spur_instance: "Spur", attr_key: str):
        """
        Retrieve the value of an attribute from a given Spur instance.

        Args:
            spur_instance (Spur): The Spur object to inspect.
            attr_key (str): The attribute name to retrieve.

        Returns:
            Any: The attribute value, or None if the attribute does not exist.
        """
        return getattr(spur_instance, attr_key, None)