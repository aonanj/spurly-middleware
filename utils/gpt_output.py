from .filters import apply_phrase_filter, apply_tone_overrides, safe_filter
from flask import current_app
from infrastructure.logger import get_logger
import json

logger = get_logger(__name__)

def parse_gpt_output(gpt_response: str, user_profile: dict, connection_profile: dict) -> dict:
    """
    Parse GPT response into usable SPUR variants with safety filtering and fallbacks.
    """
    try:
        user_id = user_profile.get("user_id")
        
        # Step 1: Sanitize and parse JSON-like GPT output
        cleaned = gpt_response.strip('`\n ').replace("```json", "").replace("```", "")
        parsed = json.loads(cleaned)
        
        

        # Step 2: Check all expected fields are present
        fallback_message = ""
        spur_keys = user_profile.get("spur_variants", [])  
        if 'warm_spur' in spur_keys and safe_filter(parsed.get('warm_spur', '')):
            fallback_message = parsed.get('warm_spur', '')
        elif 'main_spur' in spur_keys and safe_filter(parsed.get('main_spur', '')):
            fallback_message = parsed.get('main_spur', '')
        elif 'cool_spur' in spur_keys and safe_filter(parsed.get('cool_spur', '')):
            fallback_message = parsed.get('cool_spur', '')
        elif 'banter_spur' in spur_keys  and safe_filter(parsed.get('banter_spur', '')):
            fallback_message = parsed.get('banter_spur', '')

        for key in spur_keys:
            if key not in parsed or not parsed.get(key):
                parsed[key] = fallback_message

        # Step 3: Apply phrase filter and sanitization
        sanitized_output = apply_phrase_filter(fallback_message, parsed)

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
