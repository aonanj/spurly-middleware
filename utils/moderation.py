from infrastructure.clients import get_openai_client
from infrastructure.logger import get_logger
import openai
import re

logger = get_logger(__name__)

# Static hard-block list (expandable)
BANNED_PHRASES = [
    "kill yourself", "go die", "white power", "lynch", 
    " fag", " faggot", "nigger", "darkie", "slant eyed", "wetback"
]

GIBBERISH_PATTERN = re.compile(r"[^a-zA-Z0-9\s,.!?()'\"-]{3,}")
TOO_MUCH_EMOJI = re.compile(r"[\U0001F600-\U0001F64F]{3,}")

def moderate_topic(text: str) -> dict:
    """
    Evaluates a topic string for safety.
    Returns a dict with `safe: bool` and optionally `reason: str`.
    """
    if not text or not isinstance(text, str):
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return {"safe": False, "reason": "invalid_or_blank"}

    normalized = text.strip().lower()

    # Check static banned list
    for phrase in BANNED_PHRASES:
        if phrase in normalized:
            err_point = __package__ or __name__
            logger.error(f"Error: {err_point}")
            return {"safe": False, "reason": "banned_phrase"}

    # Check gibberish / emoji spam
    if GIBBERISH_PATTERN.search(text) or TOO_MUCH_EMOJI.search(text):
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return {"safe": False, "reason": "gibberish_or_emoji"}

    # ✅ (Optional): Plug in ML moderation here later
    # if classifier_score(text) > threshold:
    #     return {"safe": False, "reason": "ml_flagged"}

    return {"safe": True}

def moderate_with_openai(text):
    try:
        response = get_openai_client().moderations.create(input=text)
        flagged = response["results"][0]["flagged"]
        return {"safe": True} if not flagged else {"safe": False, "reason": "openai_moderation"}  
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        raise e