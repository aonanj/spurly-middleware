"""
Defines a dataclass named Conversation with the following fields:
    user_id: User ID (string)
    conversation_id: Conversation ID (string). Concatenates user_id, ":", and a UUID4.
    conversation: List of message dictionaries representing the conversation between the user and a connection.
    connection_id: Optional identifier for the connection (string) involved in the conversation.
    situation: Optional description of the contextual situation of the conversation (string).
    topic: Optional subject or theme of the conversation (string).
    spurs: Optional additional metadata or prompts (dictionary) related to the conversation.
    created_at: Datetime indicating when the conversation was initiated.
    
    to_dict returns a Conversation object formatted as a python dictionary.
    from_dict converts a python dictionary into a custom Conversation object.
"""

from dataclasses import dataclass
from dataclasses import field as attr_field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

@dataclass
class Conversation:
    user_id: str
    conversation_id: str
    created_at: datetime
    conversation: List[Dict[str, Any]] = attr_field(default_factory=list) 
    spurs: Optional[Dict[str, Any]] = attr_field(default_factory=dict) 
    connection_id: Optional[str] = None
    situation: Optional[str] = None
    topic: Optional[str] = None


    def to_dict(self):
        return {
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "conversation": self.conversation,
            "connection_id": self.connection_id,
            "situation": self.situation,
            "topic": self.topic,
            "spurs": self.spurs,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z") if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data):
        created_at_str = data.get("created_at")

        return cls(
            user_id=data["user_id"],
            conversation_id=data["conversation_id"],
            conversation=data.get("conversation", []),
            connection_id=data.get("connection_id"),
            situation=data.get("situation"),
            topic=data.get("topic"),
            spurs=data.get("spurs", {}),
            created_at=datetime.fromisoformat(created_at_str.replace("Z", "+00:00")) or datetime.now(timezone.utc)
        )

    @classmethod
    def get_attr(cls, convo_instance: "Conversation", attr_key: str):
        """
        Retrieve the value of an attribute from a given Conversation instance.

        Args:
            convo_instance (Conversation): The conversation object to inspect.
            attr_key (str): The attribute name to retrieve.

        Returns:
            Any: The attribute value, or None if the attribute does not exist.
        """
        return getattr(convo_instance, attr_key, None)

    def conversation_as_string(self) -> str:
        """
        Returns the conversation as a formatted string.
        Each message in the conversation list is expected to be a dictionary
        with at least a 'sender' and 'text' key. Adjust if your actual structure differs.
        """
        lines = []
        for message in self.conversation:
            sender = message.get("sender", "Unknown")
            text = message.get("text", "")
            lines.append(f"{sender}: {text}")
        return "\n".join(lines)
