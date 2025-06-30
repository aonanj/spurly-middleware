from typing import Dict
from class_defs.spur_def import Spur
from flask import g
from infrastructure.logger import get_logger
from infrastructure.clients import get_firestore_db
from infrastructure.id_generator import generate_spur_id

logger = get_logger(__name__)

def save_good_spur(good_spur: Spur) -> Dict[str, str]:
	"""
	Saves a spur that received positive feedback for training the AI model underlying the app.

	Args:
		good_spur: spur that received positive feedback
			Spur

			

	Returns:
		Dict with "status" key and "message" key indicating success of saving good_spur.
			Dict[str, str]
	"""
	good_spur_dict = good_spur.to_dict()
	user_id = getattr(g, "user_id", None)
	if not user_id:
		user_id = good_spur_dict.get("user_id", "")

	good_spur_id = ""
	if 'spur_id' not in good_spur_dict or good_spur_dict['spur_id'] == "":
		good_spur_id = generate_spur_id(user_id)
		good_spur_dict['spur_id'] = good_spur_id
	else:
		good_spur_id = good_spur_dict.get("spur_id", "")
	
	try:
		db = get_firestore_db()
		training_ref = db.collection("training").document("good_spurs").collection("batch").document(good_spur_id)
		training_ref.set(good_spur_dict)


		return {"status": "success", "message": f"Good spur successfully saved as good_spur_id: {good_spur_id}"}
	except RuntimeError as e:
		logger.error("[%s] Error: %s Save good spur failed", __name__, e)
		return {"status": "error", "message": f"Save good spur failed: {e}"}
	except Exception as e:
		logger.error("[%s] Error: %s Save good spur failed", __name__, e)
		return {"status": "error", "message": f"Save good spur failed: {e}"}

def save_bad_spur(bad_spur: Spur) -> Dict[str, str]:
	"""
	Saves a spur that received negative feedback for training the AI model underlying the app.

	Args:
		bad_spur: spur that received negative feedback
			Spur

			

	Returns:
		Dict with "status" key and "message" key indicating success of saving bad_spur.
			Dict[str, str]
	"""
	bad_spur_dict = bad_spur.to_dict()
	user_id = getattr(g, "user_id", None)
	if not user_id:
		user_id = bad_spur_dict.get("user_id", "")

	bad_spur_id = ""
	if 'spur_id' not in bad_spur_dict or bad_spur_dict['spur_id'] == "":
		bad_spur_id = generate_spur_id(user_id)
		bad_spur_dict['spur_id'] = bad_spur_id
	else:
		bad_spur_id = bad_spur_dict.get("spur_id", "")

	try:
		db = get_firestore_db()
		training_ref = db.collection("training").document("bad_spurs").collection("batch").document(bad_spur_id)
		training_ref.set(bad_spur_dict)

		return {"status": "success", "message": f"Bad spur successfully saved as bad_spur_id: {bad_spur_id}"}
	except RuntimeError as e:
		logger.error("[%s] Error: %s Save bad spur failed", __name__, e)
		return {"status": "error", "message": f"Save bad spur failed: {e}"}
	except Exception as e:
		logger.error("[%s] Error: %s Save bad spur failed", __name__, e)
		return {"status": "error", "message": f"Save bad spur failed: {e}"}