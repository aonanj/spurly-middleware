from infrastructure.clients import get_openai_client
from infrastructure.logger import get_logger
import openai
from openai import OpenAI
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
        logger.error(f"Error in moderation.moderate_topic. No input text: {err_point}")
        return {"safe": False, "reason": "invalid_or_blank"}

    normalized = text.strip().lower()
    if not _is_moderated_safe_with_openai(normalized):
        err_point = __package__ or __name__
        logger.error(f"Error in moderation.moderate_topic. calling moderate_safe_with_openai: {err_point}")
        return {"safe": False, "reason": "openai_moderation"}
    # Check static banned list
    for phrase in BANNED_PHRASES:
        if phrase in normalized:
            err_point = __package__ or __name__
            logger.error(f"Error in moderation.moderate_topic. banned_phrases: {err_point}")
            return {"safe": False, "reason": "banned_phrase"}

    # Check gibberish / emoji spam
    if GIBBERISH_PATTERN.search(text) or TOO_MUCH_EMOJI.search(text):
        err_point = __package__ or __name__
        logger.error(f"Error in moderation.moderate_topic. gibberish pattern: {err_point}")
        return {"safe": False, "reason": "gibberish_or_emoji"}

    # ✅ (Optional): Plug in ML moderation here later
    # if classifier_score(text) > threshold:
    #     return {"safe": False, "reason": "ml_flagged"}

    return {"safe": True}

def _is_moderated_safe_with_openai(text):
    try:
        chat_client = OpenAI()
        resp = chat_client.moderations.create(
            input=text,
            model="omni-moderation-latest"
        )
        flagged = resp.results[0].flagged
        return True if not flagged else False
    except openai.APIError as e:
        logger.error(f"OpenAI API error: {e}")
        return False