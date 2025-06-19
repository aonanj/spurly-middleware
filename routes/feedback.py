from class_defs.spur_def import Spur
from flask import Blueprint, request, jsonify, g
from gpt_training.anonymizer import anonymize_spur
from infrastructure.token_validator import verify_token, handle_all_errors
from services.spur_service import save_spur

feedback_bp = Blueprint("feedback", __name__)

@feedback_bp.route("/feedback", methods=["POST"])
@handle_all_errors
@verify_token
def feedback():
    data = request.get_json()
    
    user_id = getattr(g, "user_id", None)
    spur = data.get("spur")  # should be a dict representing a Spur
    feedback_type = data.get("feedback")  # "thumbs_up" or "thumbs_down"

    if not user_id or not spur or not feedback_type:
        return jsonify({"error": "Missing required feedback fields"}), 400

    spur_obj = Spur.from_dict(spur)

    result = []
    if feedback_type == "thumbs_up":
        result = save_spur(user_id, spur_obj.to_dict())
        anonymize_spur(spur_obj, True)
    elif feedback_type == "thumbs_down":
        anonymize_spur(spur_obj, False)

    return jsonify(result)
