from datetime import datetime
from flask import Blueprint, request, jsonify, g
from infrastructure.auth import require_auth
from infrastructure.logger import get_logger
from services.spur_service import get_spur, get_saved_spurs, delete_saved_spur, save_spur


logger = get_logger(__name__)

spurs_bp = Blueprint("spurs", __name__)

@spurs_bp.route("/", methods=["GET"])
@require_auth
def fetch_saved_spurs_bp():
    user_id = g.user['user_id']
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return jsonify({'error': f"[{err_point}] - Error:"}), 400

    filters = {}
    for field in ["variant", "situation"]:
        value = request.args.get(field)
        if value:
            filters[field] = value

    for date_field in ["date_from", "date_to"]:
        date_str = request.args.get(date_field)
        if date_str:
            try:
                filters[date_field] = datetime.fromisoformat(date_str)
            except ValueError as e:
                err_point = __package__ or __name__
                logger.error(f"Error: {err_point}")
                return jsonify({'error': f"[{err_point}] - Error:"}), 400

    if request.args.get("keyword"):
        filters["keyword"] = request.args.get("keyword")

    sort = request.args.get("sort", "desc")
    if sort in ["asc", "desc"]:
        filters["sort"] = sort

    result = get_saved_spurs(user_id, filters)
    return jsonify(result)

@spurs_bp.route("/", methods=["POST"])
@require_auth
def save_spur_bp():
    data = request.get_json()
    user_id = g.user['user_id']
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return jsonify({'error': f"[{err_point}] - Error:"}), 400

    result = save_spur(user_id, data)
    return jsonify(result)


@spurs_bp.route("/<spur_id>", methods=["DELETE"])
@require_auth
def delete_saved_spurs_bp(spur_id):
    user_id = g.user['user_id']
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return jsonify({'error': f"[{err_point}] - Error:"}), 400

    result = delete_saved_spur(user_id, spur_id)
    return jsonify(result)

@spurs_bp.route("/<spur_id>", methods=["GET"])
@require_auth
def get_spur_bp(spur_id):
    user_id = g.user['user_id']
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return jsonify({'error': f"{err_point} - Error:"}), 400
    result = get_spur(spur_id)
    return jsonify(result)