from .filters import apply_phrase_filter, apply_tone_overrides
from flask import current_app
from infrastructure.logger import get_logger
import json

logger = get_logger(__name__)

def parse_gpt_output(gpt_response: str, user_profile: dict, connection_profile: dict) -> dict:
    """
    Parse GPT response into usable SPUR variants with safety filtering and fallbacks.
    """
    try:
        # Step 1: Sanitize and parse JSON-like GPT output
        cleaned = gpt_response.strip('`\n ').replace("```json", "").replace("```", "")
        parsed = json.loads(cleaned)

        # Step 2: Check all expected fields are present
        spur_keys = current_app.config['SPUR_VARIANTS']
        fallback = parsed.get("warm_spur") or parsed.get("main_spur") or ""
        for key in spur_keys:
            if key not in parsed or not parsed.get(key):
                parsed[key] = fallback

        # Step 3: Apply phrase filter and sanitization
        safe_output = apply_phrase_filter(parsed)
        sanitized_output = apply_tone_overrides(safe_output, user_profile, connection_profile)

        warm_fallback = sanitized_output.get("warm_spur")
        fallback_flags = {
            key: warm_fallback and sanitized_output[key] == warm_fallback and key != "warm_spur"
            for key in sanitized_output
        }
        
        logger.error({
            "event": "spurly_generation_log",
            "fallback_flags": fallback_flags,
            "input_profile_summary": {
                "user_tone": user_profile.get("tone"),
                "connection_flirt": connection_profile.get("flirt_level"),
                "connection_drinking": connection_profile.get("drinking"),
            },
            "filter_hits": [k for k, v in fallback_flags.items() if v],
        })

        return sanitized_output

    except (json.JSONDecodeError, TypeError) as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error in gpt_ouput.parse_gpt_output: %s", err_point, e)
        return {
            "main_spur": "",
            "warm_spur": "",
            "cool_spur": "",
            "banter_spur": ""
        }
