from flask import current_app
from .logger import get_logger
from uuid import uuid4
import random
import string
import os



logger = get_logger(__name__)

# anonymous_id_indicator = current_app.config['ANONYMOUS_ID_INDICATOR']
# user_id_indicator = current_app.config['USER_ID_INDICATOR'], 
# conversation_id_indicator = current_app.config['CONVERSATION_ID_INDICATOR']
# connection_id_indicator = current_app.config['CONNECTION_ID_INDICATOR']
# spur_id_indicator = current_app.config['SPUR_ID_INDICATOR']

def _generate_random_string(length: int) -> str:
	"""
	Generates a random string of fixed length.
	
	Args
		length: Length of the random string to be generated
			int
	
	Return
		random_string: Random string of specified length
			str

	"""
	letters = string.ascii_lowercase + string.ascii_uppercase + string.digits
	random_string = ''.join(random.choice(letters) for i in range(length))
	return random_string


def generate_anonymous_user_id() -> str:
	"""
	Generates a random user ID for objects to be used as training data. Appends "a".
	
	Args
		N/A
	
	Return
		anonymous_user_id: random user_id, beginning with "u:" and ending with ":a"
			str

	"""
	user_id_indicator = os.getenv('USER_ID_INDICATOR') or current_app.config['USER_ID_INDICATOR']
	anonymous_id_indicator = os.getenv('ANONYMOUS_ID_INDICATOR') or current_app.config['ANONYMOUS_ID_INDICATOR']
	return (f"{user_id_indicator}:{uuid4().hex[:12]}:{anonymous_id_indicator}")

def generate_anonymous_conversation_id(anonymous_user_id) -> str:
	"""
	Generates a random conversation ID for objects to be used as training data. Appends anonymous indicator.
	
	Args
		anonymous_user_id: random user_id to be associated with this conversation
	
	Return
		conversation_id: random conversation_id associated with random user_id, appended with ":c:a"
			str

	"""
	anonymous_id_indicator = current_app.config['ANONYMOUS_ID_INDICATOR']
	conversation_id_indicator = current_app.config['CONVERSATION_ID_INDICATOR']
	if not anonymous_user_id:
		anonymous_user_id = generate_anonymous_user_id()

	return (f"{anonymous_user_id}:{uuid4().hex[:6]}:{conversation_id_indicator}:{anonymous_id_indicator}")

def generate_anonymous_connection_id(anonymous_user_id) -> str:
	"""
	Generates a generic connection ID for objects to be used as training data. Appends anonymous indicator.
	
	Args
		anonymous_user_id: random user_id to be associated with this connection
	Return
		anonymous_connection_id: random connection_id associated with random user_id, appended with ":p:a"
			str
	"""
	anonymous_id_indicator = current_app.config['ANONYMOUS_ID_INDICATOR']
	connection_id_indicator = current_app.config['CONNECTION_ID_INDICATOR']
	if not anonymous_user_id:
		anonymous_user_id = generate_anonymous_user_id()
	return (f"{anonymous_user_id}:{uuid4().hex[:5]}:{connection_id_indicator}:{anonymous_id_indicator}")	

def generate_conversation_id(user_id="") -> str:
	"""
	Generates a string for ID of a conversation. User ID associated with the conversation is prepended, conversation_id_indicator is appended

	Args
		user_id: User ID associated with the conversation
			str
	   
	Return
		conversation_id: Conversation ID associated with the user ID, beginning with "u:" and ending with ":c"

	"""
	conversation_id_indicator = os.getenv('CONVERSATION_ID_INDICATOR') or current_app.config['CONVERSATION_ID_INDICATOR']
	conversation_id_stub = _generate_random_string(6)  # 6 characters for conversation_id_stub
	if user_id:
		return (f"{user_id}:{conversation_id_stub}:{conversation_id_indicator}")
	else:
		logger.error("Error: Missing user_id for conversation_id generation")
		return (f":{conversation_id_stub}:{conversation_id_indicator}")

	 
def generate_connection_id(user_id: str) -> str:
	"""
	Generates a string for ID of a connection. User ID associated with the connection is prepended, connection_id_indicator is appended

	Args
		user_id: User ID associated with the connection
			str

	Return
		connection_id: Connection ID, beginning with "u:" and ending with ":p"
			str
	"""
	connection_id_indicator = current_app.config.get('CONNECTION_ID_INDICATOR')
	if not connection_id_indicator or connection_id_indicator == "":
		connection_id_indicator = "p"
	connection_id_stub = _generate_random_string(6)
	if user_id and connection_id_indicator:
		return (f"{user_id}:{connection_id_stub}:{connection_id_indicator}")
	else:	
		logger.error("Error: Missing user_id for connection_id generation")		 
		return (f":{connection_id_stub}:{connection_id_indicator}")
	

def get_null_connection_id(user_id="") -> str:
	"""
	Generates a string for ID when no connection is loaded in context (i.e., null connection). User ID associated with the connection is prepended, connection_id_indicator is appended, null_connection_indicator is appended

	Args
		user_id: User ID associated with the connection
			str

	Return
		connection_id: Connection ID, beginning with "u:" and ending with ":p"
			str
	"""
	null_connection_id = os.getenv('NULL_CONNECTION_ID') or current_app.config['NULL_CONNECTION_ID']
	if not null_connection_id or null_connection_id.strip() == "":
		logger.error("Error: NULL_CONNECTION_ID is not set in config.")
		null_connection_id = "null_connection_id_p"
	if user_id:
		return (f"{user_id}:{null_connection_id}")
	else:
		logger.error("Error: Missing user_id for connection_id generation")		 
		return null_connection_id

def generate_anonymous_spur_id(anonymous_user_id) -> str:
	"""
	Generates a generic spur ID for objects to be used as training data. Appends anonymous indicator.

	Args
		anonymous_user_id: random user_id to be associated with this spur

	Return
		anonymous_spur_id: Anonymous spur id, beginning with "u:" and ending with ":s:a"
			str
	"""
	anonymous_id_indicator = current_app.config['ANONYMOUS_ID_INDICATOR']
	spur_id_indicator = current_app.config['SPUR_ID_INDICATOR']
	if not anonymous_user_id:
		anonymous_user_id = generate_anonymous_user_id()

	return (f"{anonymous_user_id}:{uuid4().hex[:7]}:{spur_id_indicator}:{anonymous_id_indicator}")

def generate_spur_id(user_id="") -> str:
	"""
	Generates a string for ID of a spur. User ID associated with the spur is prepended, spur_id_indicator is appended

	Args
		user_id: User ID associated with the spur
			str

	Return
		spur_id: Spur ID, beginning with "u:" and ending with ":s"
			str
	"""
	spur_id_indicator = os.getenv('SPUR_ID_INDICATOR') or "s"
	spur_id_stub = _generate_random_string(6)  # 7 characters for spur_id_stub
	if user_id:
		return (f"{user_id}:{spur_id_stub}:{spur_id_indicator}")
	elif not user_id:
		logger.error("Error: Missing user_id for connection_id generation")		 
		return (f":{spur_id_stub}:{spur_id_indicator}")
	return ""

def extract_user_id_from_other_id(other_id: str) -> str:
    """
    Gets the user_id portion from conversation_id, connection_id, or spur_id.

    Args
        other_id: conversation_id, connection_id, or spur_id the user_id is to be extracted from
            str
    Return
        user_id: user_id extracted from the partioned other_id (all characters up to the first delimiter)
            str

    """
    
    id_delimiter = current_app.config['ID_DELIMITER']
    user_id = other_id.partition(id_delimiter)[0]
    
    if not user_id or not other_id:
        logger.error("Error: Failed to get conversation - missing user_id or conversation_id ", __name__)
        return ""

    return user_id