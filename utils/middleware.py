from flask import request, jsonify
from functools import wraps
from infrastructure.logger import get_logger
from .moderation import moderate_topic
import utils.trait_manager as trait_manager

logger = get_logger(__name__)

def sanitize_topic(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        context = getattr(request, "context", request.get_json() or {})
        topic = context.get("topic", "")
        filtered = False

        if isinstance(topic, str):
            topic = topic.strip()[:75]

        result = moderate_topic(topic)
        if not result["safe"]:
            topic = ""
            filtered = True

        context["topic"] = topic
        context["topic_filtered"] = filtered
        setattr(request, "context", context)

        return f(*args, **kwargs)
    return wrapper


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
            logger.error(f"Error: {err_point}")
            return jsonify({"error": "User age must be at least 18"}), 400

        if "age" in connection_profile:
            try:
                connection_age = int(connection_profile["age"])
                if connection_age < 18:
                    raise ValueError
            except (ValueError, TypeError):
                err_point = __package__ or __name__
                logger.error(f"Error: {err_point}")
                return jsonify({"error": "connection age must be at least 18 if provided"}), 400

        return f(*args, **kwargs)
    return wrapper

def enrich_context(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        data = request.get_json() or {}
        conversation = data.get("conversation", [])
        
        if not data.get("situation"):
            try:
                inferred = trait_manager.infer_situation(conversation)
            except Exception as e:
                err_point = __package__ or __name__
                logger.error("[%s] Error: %s", err_point, e)
                inferred = {"situation": "cold_open", "confidence": "low"}
            data["situation"] = inferred.get("situation", "cold_open")
            data["situation_confidence"] = inferred.get("confidence", "low")
        
        # Attach enriched data to request context
        
        setattr(request, "context", data)
        
        return f(*args, **kwargs)
    
    return wrapper