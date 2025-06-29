from class_defs.spur_def import Spur
from flask import Blueprint, request, jsonify, g
from gpt_training.training_data_collector import save_good_spur, save_bad_spur
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
        result = save_good_spur(spur_obj)
    elif feedback_type == "thumbs_down":
        result = save_bad_spur(spur_obj)

    return jsonify(result), 200
