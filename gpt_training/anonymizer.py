from class_defs.conversation_def import Conversation
from class_defs.spur_def import Spur
from datetime import datetime, timezone
from flask import current_app, jsonify
from infrastructure.clients import get_firestore_db
from infrastructure.id_generator import generate_anonymous_user_id, generate_anonymous_conversation_id, generate_anonymous_connection_id, generate_anonymous_spur_id
from infrastructure.logger import get_logger
from services.connection_service import get_connection_profile
from services.user_service import get_user

logger = get_logger(__name__)

def anonymize_conversation(original_conversation: Conversation) -> str:
	"""
	Replaces speaker labels with generic labels 'Person A' and 'Person B' for user and connection respectively.
	Maintains message order and speaker attribution.

	Args:
		original_conversation: Conversation object including the conversation data to be anonymized
			Conversation

	Returns:
		status: string indicating success of anonymizing and saving original_conversation.
			str
	"""
	try:
		if not original_conversation or not isinstance(original_conversation, Conversation):
			logger.error("Invalid conversation format. Conversation object expected.")
			raise TypeError("Invalid conversation format. Conversation object expected.")

		conversation_dict = original_conversation.to_dict()
		conversation_messages = original_conversation.conversation
		
		user_id = conversation_dict.get("user_id", "")
		user_profile = get_user(user_id)

		connection_id = original_conversation.connection_id or ""
		connection_profile = None
				
		if not all("text" in message and "speaker" in message for message in conversation_messages):
			logger.error("Invalid conversation format. Keys 'text' and 'speaker' expected.")
			raise ValueError("Invalid conversation format. Keys 'text' and 'speaker' expected.")

		user_label = "Person A"
		connection_label = "Person B"

		anonymized_messages = []
		for message in conversation_messages:
			original_speaker = message.get("speaker", "").lower()
			text = message.get("text", "").lower()

			if original_speaker == "user":
				speaker_label = user_label
			elif original_speaker == "connection":
				speaker_label = connection_label
			else:
				speaker_label = "Unknown"

			anonymized_messages.append({
				"speaker": speaker_label,
				"text": text
			})
			
		anonymous_user_id = generate_anonymous_user_id()
		anonymous_conversation_id = generate_anonymous_conversation_id(anonymous_user_id)
		anonymous_connection_id = generate_anonymous_connection_id(anonymous_user_id)
		situation = conversation_dict.get("situation", "")
		topic = conversation_dict.get("topic", "")
		spurs = conversation_dict.get("spurs", None)
		created_at = conversation_dict.get("created_at", datetime.now(timezone.utc))

			
		anonymized_conversation = Conversation (
			user_id=anonymous_user_id,
			conversation_id=anonymous_conversation_id,
			created_at=created_at,
			conversation=anonymized_messages,
			connection_id=anonymous_connection_id,
			situation=situation,
			topic=topic,
			spurs=spurs,
		)
		save_anonymized_conversation(anonymized_conversation)
		return (f"Conversation successfully anonymized with anonymized_conversation_id: {anonymous_conversation_id}")

	except Exception as e:
		logger.error("[%s] Error: %s Anonymizing conversation failed", __name__, e)
		raise ValueError(f"Anonymizing conversation failed: {e}") from e

def save_anonymized_conversation(anonymized_conversation: Conversation):
	"""
	Saves an anonymized conversation for training the AI model underlying the app.

	Args:
		anonymized_conversation: Conversation object including the anonymized conversation data to be saved
			Conversation

	Returns:
		status: string indicating success of anonymizing and saving original_conversation.
			
	"""
	
	anonymized_conversation_dict = Conversation.to_dict(anonymized_conversation)
	anonymized_conversation_id = anonymized_conversation_dict.get("conversation_id", generate_anonymous_conversation_id(None))
	
	try:
		db = get_firestore_db()
		training_ref = db.collection("training").document("conversations").collection("batch").document(anonymized_conversation_id)
		
		training_ref.set(anonymized_conversation_dict)
		return jsonify(f"Anonymized conversation successfully anonymized with id: {anonymized_conversation_id}")
	except RuntimeError as e:
		logger.error("[%s] Error: %s Save anonymized conversation failed", __name__, e)
		raise RuntimeError(f"Save anonymized conversation failed: {e}") from e
	except Exception as e:
		logger.error("[%s] Error: %s Save anonymized conversation failed", __name__, e)
		raise ValueError(f"Save anonymized conversation failed: {e}") from e

def anonymize_spur(original_spur: Spur, is_quality_spur: bool)->str:
	"""
	Anonymizes a spur to use as training data. user_id, spur_id, conversation_id, connection_id, and created_at are replaced with generic values.

	Args:
		original_spur: spur to be anonymized.
			Spur object
		is_quality_spur: indicates whether original_spur received positive feedback or negative feedback.
			bool
		
	Returns
		status: string indicating success of anonymizing and saving original_spur.
			str

	"""
	try:
		if not Spur or not isinstance(original_spur, Spur):
			logger.error("Invalid spur. Cannot anonymize spur. No spur data saved.")

		spur_dict = Spur.to_dict(original_spur)
		
		anonymous_user_id = generate_anonymous_user_id()
		anonymous_spur_id = generate_anonymous_spur_id(anonymous_user_id)
		anonymous_conversation_id = generate_anonymous_conversation_id(anonymous_user_id)
		anonymous_connection_id = generate_anonymous_connection_id(anonymous_user_id)
		
		spur_dict['user_id'] = anonymous_user_id
		spur_dict['spur_id'] = anonymous_spur_id
		spur_dict['connection_id'] = anonymous_connection_id
		spur_dict['conversation_id'] = anonymous_conversation_id
		spur_dict['created_at'] = datetime.now(timezone.utc)
		
		save_anonymized_spur(Spur.from_dict(spur_dict), is_quality_spur)

		return (f"Spur successfully anonymized with ID: {anonymous_spur_id}")

	except Exception as e:
		logger.error("[%s] Error: %s Anonymizing spur failed", __name__, e)
		raise ValueError(f"Anonymizing spur failed: {e}") from e


def save_anonymized_spur(anonymized_spur: Spur, is_quality_spur) -> str:
	"""
	Saves an anonymized spur for training the AI model underlying the app.

	Args:
		anonymized_spur: anonymized spur
			Spur
		is_quality_spur: indicates whether original_spur received positive feedback or negative feedback.
			bool
			

	Returns:
		status: string indicating success of saving anonymized_spur.
			str
	"""

	anonymized_spur_dict = anonymized_spur.to_dict()
	anonymized_spur_id = anonymized_spur_dict.get("spur_id", generate_anonymous_spur_id(None))
	try:
		db = get_firestore_db()
		if is_quality_spur:
			training_ref = db.collection("training").document("quality_spurs").collection("batch").document(anonymized_spur_id)
			training_ref.set(anonymized_spur_dict)
		elif not is_quality_spur:
			training_ref = db.collection("training").document("bad_spurs").collection("batch").document(anonymized_spur_id)
			training_ref.set(anonymized_spur_dict)


		return (f"Anonymized spur successfully saved as anonymized_spur_id: {anonymized_spur_id}")
	except RuntimeError as e:
		logger.error("[%s] Error: %s Save anonymized spur failed", __name__, e)
		raise RuntimeError(f"Save anonymized spur failed: {e}") from e
	except Exception as e:
		logger.error("[%s] Error: %s Save anonymized spur failed", __name__, e)
		raise ValueError(f"Save anonymized spur failed: {e}") from e