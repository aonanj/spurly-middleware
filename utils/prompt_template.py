from flask import current_app
from infrastructure.logger import get_logger
import json

logger = get_logger(__name__)

def get_system_prompt() -> str:
    """
    Retrieves the system prompt used to prime the model.
    """
    system_prompt_path = current_app.config.get('SPURLY_SYSTEM_PROMPT_PATH')  # Use .get for safety

    if not system_prompt_path:
        logger.error("SPURLY_SYSTEM_PROMPT_PATH not found in Flask config.")
        raise ValueError("System prompt path configuration is missing.")

    try:
        with open(system_prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error("System prompt file not found at path: %s", system_prompt_path)
        raise FileNotFoundError(f"System prompt file not found: {system_prompt_path}")
    except IOError as e:
        logger.error("Error reading system prompt file at path %s: %s", system_prompt_path, e)
        raise IOError(f"Error reading system prompt file: {e}") from e
    except Exception as e:
        logger.error("Unexpected error loading system prompt: %s", e, exc_info=True)
        raise  # Re-raise unexpected errors

def build_prompt(selected_spurs: list[str], context_block: str) -> str:
    try:
        """
        Constructs the dynamic GPT prompt using system rules + conversation context.
        """
        
        user_prompt = context_block
        
        spur_descriptions = current_app.config.get('SPUR_VARIANT_DESCRIPTIONS', {})
        for k, v in spur_descriptions.items():
            if k in selected_spurs:
                user_prompt += f"\n   -{k}: {v}"

        
        user_prompt += "\n\n Your response should be formatted as a JSON object with the following structure:\n"
        json_output_structure = "\n {\n" 
        for k, v in spur_descriptions.items():
            if k in selected_spurs:
                json_output_structure += f'     "{k}": "<generated message suggestion for {k}>",\n'
        json_output_structure += "  }\n"
        
        user_prompt += json_output_structure
        user_prompt += "\n\n Your output must be strictly formatted as above. Do NOT include any text or characters outside of the JSON object. No explanations, no additional text, no markdown formatting. Just the JSON object."
        
        # Final prompt
        return user_prompt
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error in prompt_template.build_prompt: %s", err_point, e)
        raise e
