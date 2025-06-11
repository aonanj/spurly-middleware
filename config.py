from dotenv import load_dotenv
import os
import json

load_dotenv()

class Config:
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "spurly-default-key")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    APP_OATH_KEY = os.environ.get("APP_OATH_KEY", "")
    APPLE_CLIENT_ID = os.environ.get("APPLE_CLIENT_ID", "")
    
    _vision_creds_path = os.environ.get("GOOGLE_CLOUD_VISION_CREDS")
    if _vision_creds_path:
        with open(_vision_creds_path) as f:
            _vision_creds = json.load(f)
    else:
        _vision_creds = {}
    GOOGLE_CLOUD_VISION_API_KEY = _vision_creds.get("private_key", "")

    _firestore_creds_path = os.environ.get("GOOGLE_CLOUD_FIRESTORE_CREDS")
    if _firestore_creds_path:
        with open(_firestore_creds_path) as f:
            _firestore_creds = json.load(f)
    else:
        _firestore_creds = {}
    GOOGLE_CLOUD_FIRESTORE_API_KEY = _firestore_creds.get("private_key", "")

    _firebase_creds_path = os.environ.get("GOOGLE_CLOUD_FIREBASE_CREDS")
    if _firebase_creds_path:
        with open(_firebase_creds_path) as f:
            _firebase_creds = json.load(f)
    else:
        _firebase_creds = {}
    GOOGLE_CLOUD_FIREBASE_API_KEY = _firebase_creds.get("private_key", "")

    _vertex_creds_path = os.environ.get("GOOGLE_CLOUD_VERTEX_CREDS")
    if _vertex_creds_path:
        with open(_vertex_creds_path) as f:
            _vertex_creds = json.load(f)
    else:
        _vertex_creds = {}
    GOOGLE_CLOUD_VERTEX_API_KEY = _vertex_creds.get("private_key", "")

    GCS_PROFILE_PICS_BUCKET = os.environ.get("GCS_PROFILE_PICS_BUCKET", "boreal-sweep-455716-a5.firebasestorage.app")

    ## Algolia credentials
    ALGOLIA_APP_ID = os.getenv("ALGOLIA_APP_ID")
    ALGOLIA_ADMIN_KEY = os.getenv("ALGOLIA_ADMIN_KEY")
    ALGOLIA_CONVERSATIONS_INDEX = os.getenv("ALGOLIA_CONVERSATIONS_INDEX", "conversations")
    ALGOLIA_SEARCH_RESULTS_LIMIT = os.getenv("ALGOLIA_SEARCH_RESULTS_LIMIT", 20)
    ALGOLIA_WRITE_API_KEY = os.getenv("ALGOLIA_WRITE_API_KEY", "")


    

    ENABLE_AUTH = os.environ.get("ENABLE_AUTH", "True").lower() == "true"
    
    SPURLY_SYSTEM_PROMPT_PATH = os.environ.get("SPURLY_SYSTEM_PROMPT_PATH", "resources/spurly_system_prompt.txt")
    SPURLY_USER_PROMPT_PATH = os.environ.get("SPURLY_USER_PROMPT_PATH", "resources/spurly_user_prompt.txt")
    SPURLY_INFERENCE_PROMPT = os.environ.get("SPURLY_INFERENCE_PROMPT", "resources/spurly_inference_prompt.txt")

    SPUR_VARIANTS = (
        "main_spur",
        "warm_spur",
        "cool_spur",
        "banter_spur"
    )

    SPUR_VARIANT_DESCRIPTIONS = {
        "main_spur": "Natural, charismatic, confident, open, friendly. Prioritize fluid conversation and approachability.",
        "warm_spur": "Kind, inviting, sincere, lightly humorous. Emphasize receptiveness and warmth.",
        "cool_spur": "Dry humor, clever, smooth, low-key, chill, lightly ironic. Emphasize ease, calm confidence, or witty restraint.",
        "banter_spur": "Energetic, teasing, engaging, flirtatious, humorous, joking, good-natured teasing, occasionally flirty. Use fun language and soft banter—respect boundaries, but keep the conversation going."
    }

    
    SPUR_VARIANT_ID_KEYS = {
        "main_spur": "S",
        "warm_spur": "W",
        "cool_spur": "C",
        "banter_spur": "B"
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
    
    AI_MODEL = "chatgpt-4o-latest"
    AI_MESSAGES_ROLE_SYSTEM = "system"
    AI_MESSAGES_ROLE_USER = "user"
    AI_TEMPERATURE_INITIAL = 0.9
    AI_TEMPERATURE_RETRY = .65
    AI_MAX_TOKENS = 2000
    
    ##Used as part of conversation_id to flag conversations extracted via OCR
    OCR_MARKER = "OCR"
    
    DEFAULT_LOG_LEVEL = 20

