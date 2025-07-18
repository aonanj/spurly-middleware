from infrastructure.logger import get_logger
import re

# === Phrase Blacklists and Regex ===
BLACKLISTED_PHRASES = [
    "challenge accepted",
    "sorry not sorry",
    "netflix and chill",
    "roast me",
    "literally dying", 
    "i can't even",
    "yolo",
    "fomo",
    "epic fail",
    "bling bling",
    "flossy",
    "vibes are immaculate",
    "vibe check",
    "slay queen",
    "on fleek",
    "cool beans",
    "what she said",
    "hot take"
]

logger = get_logger(__name__)

EXPIRED_PHRASES = [
    "hope this helps",
    "let me know what you think",
    "just checking in",
    "just wanted to follow up",
    "just following up",
    "just wanted to reach out",
    "just wanted to check in",
    "just wanted to see",
    "hope you're doing well",
    "circling back",
    "just wanted to touch base",
    "how are you doing",
    "getting to know you",
    "get to know you",
    "just wanted to say",
    "just wanted to share",
    "just wanted to let you know",
    "nice to meet you",
    "nice meeting you",
    "looking forward to hearing from you",
    "look forward to",
    "you seem like",
    "you look like",
    "you strike me as",
    "nice chatting",
    "you strike me as",
    "nice talking",
]

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
        logger.error(f"Error in filters.safe_filter (1): {err_point}; Invalid text input: {text}")
        return False
    if contains_blacklisted_phrase(text):
        err_point = __package__ or __name__
        logger.error(f"Error in filters.safe_filter (2): {err_point}; Blacklisted phrase: {text}")
        return False
    if contains_expired_phrase(text):
        err_point = __package__ or __name__
        logger.error(f"Error in filters.safe_filter (3): {err_point}; Expired phrase: {text}")
        return False
    if fails_regex_safety(text):
        err_point = __package__ or __name__
        logger.error(f"Error in filters.safe_filter (4): {err_point}; Regex safety fail: {text}")
        return False
    return True