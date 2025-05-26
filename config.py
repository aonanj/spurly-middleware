from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "spurly-default-key")
    GOOGLE_CLOUD_VISION_API_KEY = os.environ.get("GOOGLE_CLOUD_VISION_API_KEY", "")
    GOOGLE_CLOUD_FIRESTORE_API_KEY = os.environ.get("GOOGLE_CLOUD_FIRESTORE_API_KEY", "")
    GOOGLE_CLOUD_FIREBASE_API_KEY = os.environ.get("GOOGLE_CLOUD_FIREBASE_API_KEY", "")
    GOOGLE_CLOUD_VERTEX_API_KEY = os.environ.get("GOOGLE_CLOUD_VERTEX_API_KEY", "")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

    ## Algolia credentials
    ALGOLIA_APP_ID = os.getenv("ALGOLIA_APP_ID")
    ALGOLIA_ADMIN_KEY = os.getenv("ALGOLIA_ADMIN_KEY")
    ALGOLIA_CONVERSATIONS_INDEX = os.getenv("ALGOLIA_CONVERSATIONS_INDEX", "conversations")
    ALGOLIA_SEARCH_RESULTS_LIMIT = os.getenv("ALGOLIA_SEARCH_RESULTS_LIMIT", 20)


    

    ENABLE_AUTH = os.environ.get("ENABLE_AUTH", "True").lower() == "true"
    
    SPURLY_SYSTEM_PROMPT_PATH = os.environ.get("SPURLY_SYSTEM_PROMPT_PATH", "resources/spurly_system_prompt.txt")

    SPUR_VARIANTS = (
        "main_spur",
        "warm_spur",
        "cool_spur",
        "banter_spur"
    )

    SPUR_VARIANT_DESCRIPTIONS = {
        "main_spur": "Friendly (emotionally open, upbeat, optimistic, receptive, engaging)",
        "warm_spur": "Warm (lighthearted, kind, empathetic, sincere, thoughtful)",
        "cool_spur": "Cool (carefree, casual, cool and calm, dry, occasionally sarcastic)",
        "banter_spur": "banter (humorous, joking, good-natured teasing, occasionally flirty)",
    }
    
    SPUR_VARIANT_ID_KEYS = {
        "main_spur": "S",
        "warm_spur": "W",
        "cool_spur": "C",
        "banter_spur": "P"
        }

    JWT_EXPIRATION = 60 * 60 * 24 * 7  # 1 week

    ID_DELIMITER = ":"    
    NULL_CONNECTION_ID = "null_connection_id_p"
    ANONYMOUS_ID_INDICATOR = "a"
    USER_ID_INDICATOR = "u"
    CONVERSATION_ID_INDICATOR = "c"   
    CONNECTION_ID_INDICATOR = "p"
    SPUR_ID_INDICATOR = "s"
       

    LOGGER_LEVEL = os.environ.get("LOGGER_LEVEL", "INFO")
    
    AI_MODEL = os.environ.get("GPT_MODEL_NAME", "gpt-4o")
    AI_MESSAGES_ROLE_SYSTEM = "system"
    AI_MESSAGES_ROLE_USER = "user"
    AI_TEMPERATURE_INITIAL = 0.9
    AI_TEMPERATURE_RETRY = .65
    AI_MAX_TOKENS = 600
    
    ##Used as part of conversation_id to flag conversations extracted via OCR
    OCR_MARKER = "OCR"
    
    DEFAULT_LOG_LEVEL = 20

    GCS_PROFILE_PICS_BUCKET = 'your-actual-gcs-bucket-name'