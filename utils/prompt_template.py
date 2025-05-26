from flask import current_app
from infrastructure.logger import get_logger
import json

logger = get_logger(__name__)

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
        
        spur_instructions = "\n".join(
            f"{idx + 1}. {current_app.config['SPUR_VARIANT_DESCRIPTIONS'][v]}"
            for idx, v in enumerate(valid_spurs)
        )

        json_output_structure = "{\n" + ",\n".join(f'  "{v}": "..."' for v in valid_spurs) + "\n}"

        # Final prompt
        return f"""### Instructions
            Please generate SPURs suggested for Party A to say to Party B based on the context below. There should be one spur that reflects each of the following {len(valid_spurs)} tones:

            {spur_instructions}

            Avoid repeating the original messages. Each spur should feel distinct in tone and language, with the tone and language being reflective of the context. Each message should sound as though it naturally came from Party A, given the context below regarding Party A and what is known about Party B.

            Respond in JSON with this format:
            {json_output_structure}

            ### Context
            {context_block}
            """
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        raise e
