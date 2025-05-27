from dotenv import load_dotenv
import os
import json

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "spurly-default-key")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    APP_OATH_KEY = os.environ.get("APP_OATH_KEY", "")
    
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

    ## Algolia credentials
    ALGOLIA_APP_ID = os.getenv("ALGOLIA_APP_ID")
    ALGOLIA_ADMIN_KEY = os.getenv("ALGOLIA_ADMIN_KEY")
    ALGOLIA_CONVERSATIONS_INDEX = os.getenv("ALGOLIA_CONVERSATIONS_INDEX", "conversations")
    ALGOLIA_SEARCH_RESULTS_LIMIT = os.getenv("ALGOLIA_SEARCH_RESULTS_LIMIT", 20)
    ALGOLIA_WRITE_API_KEY = os.getenv("ALGOLIA_WRITE_API_KEY", "")


    

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