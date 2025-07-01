from .filters import sanitize
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

        spur_keys = user_profile.get("spur_variants", [])  
        
        for key in spur_keys:
            if key in parsed and isinstance(parsed.get(key, ""), str):
                parsed[key] = sanitize(parsed.get(key, "").strip())

        return parsed

    except (json.JSONDecodeError, TypeError) as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error in gpt_ouput.parse_gpt_output: %s", err_point, e)
        return {
            "main_spur": "",
            "warm_spur": "",
            "cool_spur": "",
            "banter_spur": ""
        }
