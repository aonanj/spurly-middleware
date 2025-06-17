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

        valid_spurs = [v for v in selected_spurs if v in current_app.config['SPUR_VARIANT_DESCRIPTIONS']]
        if not valid_spurs:
            err_point = __package__ or __name__
            logger.error(f"Error: {err_point}")
            raise ValueError("No valid SPUR variants selected.")
        
        spur_instructions = ""
        
        user_prompt_path = current_app.config.get('SPURLY_USER_PROMPT_PATH') # Use .get for safety

        if not user_prompt_path:
            logger.error("SPURLY_USER_PROMPT_PATH not found in Flask config.")
            # Raise an error or return a default prompt string
            raise ValueError("User prompt path configuration is missing.")

        try:
            with open(user_prompt_path, "r", encoding="utf-8") as f:
                spur_instructions = f.read().strip()
        except FileNotFoundError:
            logger.error("User prompt file not found at path: %s", user_prompt_path)
            # Raise an error or return a default prompt string
            raise FileNotFoundError(f"User prompt file not found: {user_prompt_path}")
        except IOError as e:
            logger.error("Error reading user prompt file at path %s: %s", user_prompt_path, e)
            # Raise an error or return a default prompt string
            raise IOError(f"Error reading user prompt file: {e}") from e
        except Exception as e:
            logger.error("Unexpected error loading user prompt: %s", e, exc_info=True)
            raise  # Re-raise unexpected errors

        spur_instructions += "\n\n### SPUR VARIANTS AND DESCRIPTIONS ###\n"

        spur_instructions += "\n".join(
            f"{idx + 1}. {v}: {current_app.config['SPUR_VARIANT_DESCRIPTIONS'][v]}"
            for idx, v in enumerate(valid_spurs)
        )

        json_output_structure = "{\n" + ",\n".join(f'  "{v}": "..."' for v in valid_spurs) + "\n}"

        spur_instructions += f"\n\n### OUTPUT FORMAT ###\nRespond in JSON in the following format: \n {json_output_structure}"

        spur_instructions += f"\n\n### CONTEXT ###\n{context_block}\n\n"
        # Final prompt
        return spur_instructions
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        raise e
