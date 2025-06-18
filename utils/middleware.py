from flask import request, jsonify
from functools import wraps
from infrastructure.logger import get_logger
from .moderation import moderate_topic
import utils.trait_manager as trait_manager

logger = get_logger(__name__)

def sanitize_topic(topic):


    if isinstance(topic, str):
        topic = topic.strip()[:75]

    result = moderate_topic(topic)
    logger.error(f" Moderation result for topic '{topic}': {result}")
    if not result.get('safe'):
        topic = ""
        filtered = True
        return {
            "filtered": True,
            "topic": topic,
        }

    return {
        "filtered": False,
        "topic": topic,
    }


def validate_profile(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        data = request.get_json() or {}
        user_profile = data.get("user_profile", {})
        connection_profile = data.get("connection_profile", {})
        
        # Validate age field exists and is an integer >= 18
        try:
            age = int(user_profile.get("age", 0))
            if age < 18:
                err_point = __package__ or __name__
                logger.error(f"Error: {err_point}")
                raise ValueError
        except (ValueError, TypeError):
            err_point = __package__ or __name__
            logger.error(f"Error in validate_profile decorator of middleware.py: {err_point}")
            return jsonify({"error": "User age must be at least 18"}), 400

        if "age" in connection_profile:
            try:
                connection_age = int(connection_profile["age"])
                if connection_age < 18:
                    raise ValueError
            except (ValueError, TypeError):
                err_point = __package__ or __name__
                logger.error(f"Error in validate_profile decorator of middleware.py: {err_point}")
                return jsonify({"error": "connection age must be at least 18 if provided"}), 400

        return f(*args, **kwargs)
    return wrapper
