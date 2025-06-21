from infrastructure.logger import get_logger
from typing import Dict
import re

# === Phrase Blacklists and Regex ===
BLACKLISTED_PHRASES = [
    "Challenge accepted",
    "Sorry not sorry",
    "Netflix and chill",
    "Roast me",
    "Literally dying"
    # Expand with others as needed
]

logger = get_logger(__name__)

EXPIRED_PHRASES = {
    # Dynamic decay phrases (tagged with expiry epoch if needed)
    ##"vibe check": "tier_1",
    ##"that’s cap": "tier_2"
}

# === Regex traps for formatting issues ===
REGEX_EMOJI_SPAM = re.compile(r"[\U0001F600-\U0001F64F]{4,}")  # basic emoji overuse
REGEX_ASCII_ART = re.compile(r"[\|\_\-/\\]{5,}")
REGEX_CAPS_LOCK = re.compile(r"[A-Z\s]{12,}")


def sanitize(text: str) -> str:
    """Clean up excess whitespace and normalize emoji spacing."""
    return re.sub(r'\s+', ' ', text).strip()


def contains_blacklisted_phrase(text: str) -> bool:
    """Check for any exact-match blacklisted phrases."""
    return any(phrase.lower() in text.lower() for phrase in BLACKLISTED_PHRASES)


def contains_expired_phrase(text: str) -> bool:
    return any(phrase.lower() in text.lower() for phrase in EXPIRED_PHRASES)


def fails_regex_safety(text: str) -> bool:
    return (
        REGEX_EMOJI_SPAM.search(text) is not None or
        REGEX_ASCII_ART.search(text) is not None or
        REGEX_CAPS_LOCK.search(text) is not None
    )


def safe_filter(text: str) -> bool:
    """
    Returns True if the message is safe.
    False if blacklisted, expired, or fails formatting regex.
    """
    if not text or not isinstance(text, str):
        err_point = __package__ or __name__
        logger.error(f"Error in filters.safe_filter (1): {err_point}")
        return False
    if contains_blacklisted_phrase(text):
        err_point = __package__ or __name__
        logger.error(f"Error in filters.safe_filter (2): {err_point}. Blacklisted phrase: {text}")
        return False
    if contains_expired_phrase(text):
        err_point = __package__ or __name__
        logger.error(f"Error in filters.safe_filter (3): {err_point}")
        return False
    if fails_regex_safety(text):
        err_point = __package__ or __name__
        logger.error(f"Error in filters.safe_filter (4): {err_point}")
        return False
    return True


def apply_phrase_filter(variants: Dict[str, str]) -> Dict[str, str]:
    """
    Run filtering logic over all SPUR variants and apply fallback if unsafe.
    This should be run in the GPT output parsing pipeline before rendering.
    """
    fallback = " "
    if variants.get("main_spur", ""):
        fallback = variants.get("main_spur", "")
    elif variants.get("warm_spur", ""):
        fallback = variants.get("warm_spur", "")
    elif variants.get("cool_spur", ""):
        fallback = variants.get("cool_spur", "")
    elif variants.get("banter_spur", ""):
        fallback = variants.get("banter_spur", "")
    
    output = {}

    for key, message in variants.items():
        if safe_filter(message):
            output[key] = sanitize(message)
        else:
            output[key] = fallback 
            err_point = __package__ or __name__
            logger.error(f"Warning: {err_point}")
    return output

def apply_tone_overrides(variants: Dict[str, str], user_profile: dict, connection_profile: dict) -> Dict[str, str]:
    """
    Adjusts or suppresses SPUR variants based on user/connection trait conflicts.
    Replaces affected variants with warm_spur fallback if necessary.
    """
    fallback = " "
    if variants.get("main_spur", ""):
        fallback = variants.get("main_spur", "")
    elif variants.get("warm_spur", ""):
        fallback = variants.get("warm_spur", "")
    elif variants.get("cool_spur", ""):
        fallback = variants.get("cool_spur", "")
    elif variants.get("banter_spur", ""):
        fallback = variants.get("banter_spur", "")
    output = variants.copy()


    return output

# Example integration (in output parser module):
# parsed_output = json.loads(gpt_response)
# safe_output = apply_phrase_filter(parsed_output)
# proceed with safe_output
