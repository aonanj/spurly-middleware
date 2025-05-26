# utils/prompt_loader.py
from flask import current_app
from infrastructure.logger import get_logger # Assuming logger setup

logger = get_logger(__name__)

def load_system_prompt() -> str:
	"""
		Gets the system prompt used to prime the model
	"""
	system_prompt_path = current_app.config.get('SPURLY_SYSTEM_PROMPT_PATH') # Use .get for safety

	if not system_prompt_path:
		logger.error("SPURLY_SYSTEM_PROMPT_PATH not found in Flask config.")
		# Raise an error or return a default prompt string
		raise ValueError("System prompt path configuration is missing.")

	try:
		with open(system_prompt_path, "r", encoding="utf-8") as f:
			return f.read().strip()
	except FileNotFoundError:
		logger.error("System prompt file not found at path: %s", system_prompt_path)
        	# Raise an error or return a default prompt string
		raise FileNotFoundError(f"System prompt file not found: {system_prompt_path}")
	except IOError as e:
		logger.error("Error reading system prompt file at path %s: %s", system_prompt_path, e)	
        	# Raise an error or return a default prompt string
		raise IOError(f"Error reading system prompt file: {e}") from e
	except Exception as e:
		logger.error("Unexpected error loading system prompt: %s", e, exc_info=True)
		raise # Re-raise unexpected errors