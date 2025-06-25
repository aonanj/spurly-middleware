from class_defs.spur_def import Spur
from flask import current_app

def validate_and_normalize_output(spur_dict, variants):
    """
    Ensures all 4 SPUR types are present and safe. Substitutes missing or invalid values
    with warm_spur. Also trims whitespace and truncates excessively long messages.
    """
    fallback = " "
    if "warm_spur" in spur_dict:
        fallback = spur_dict.get("warm_spur", "").strip()
    elif "main_spur" in spur_dict:
        fallback = spur_dict.get("main_spur", "").strip()
    elif "cool_spur" in spur_dict:
        fallback = spur_dict.get("cool_spur", "").strip()
    elif "banter_spur" in spur_dict:
        fallback = spur_dict.get("banter_spur", "").strip()

    validated = {}
    

    for variant in variants:
        value = spur_dict.get(variant, "").strip()
        if not value or not isinstance(value, str) or len(value) > 1000:
            validated[variant] = fallback
        else:
            validated[variant] = value

    return validated

COMMON_PHRASES = [
    "hope this helps",
    "let me know what you think",
    "just checking in",
    "just wanted to follow up",
    "hope you're doing well",
    "circling back",
    "just wanted to touch base",
    "how are you doing",
    "getting to know you",
    "get to know you"
]

def spurs_to_regenerate(spurs: list[Spur]) -> list[str]:
    """
    Identifies SPURs that should be regenerated based on generic or weak phrasing.
    
    Args:
        spurs (list[Spur]): List of Spur objects.

    Returns:
        list[str]: Subset of Spur objects flagged for regeneration.
    """
    spurs_to_retry = []
    for spur in spurs:
        message = getattr(spur, "text", "").lower()
        if any(phrase in message for phrase in COMMON_PHRASES):
            spurs_to_retry.append(spur.variant)
    return spurs_to_retry

CONFIDENCE_THRESHOLDS = {
    "high": 0.65,
    "medium": 0.4,
    "low": 0.25
}

def classify_confidence(score):
    if score >= CONFIDENCE_THRESHOLDS["high"]:
        return "high"
    elif score >= CONFIDENCE_THRESHOLDS["medium"]:
        return "medium"
    elif score >= CONFIDENCE_THRESHOLDS["low"]:
        return "low"
    else:
        return "very_low"