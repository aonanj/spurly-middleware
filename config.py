from dotenv import load_dotenv
import os
import json

load_dotenv()

class Config:
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "spurly-default-key")
    
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    
    APP_OATH_KEY = os.environ.get("APP_OATH_KEY", "")
    
    APPLE_CLIENT_ID = os.environ.get("APPLE_CLIENT_ID", "")
    APPLE_BUNDLE_ID = os.environ.get("APPLE_BUNDLE_ID", "")
    
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_REVERSED_CLIENT_ID = os.environ.get("GOOGLE_REVERSED_CLIENT_ID", "")
    GCS_PROFILE_PICS_BUCKET = os.environ.get("GCS_PROFILE_PICS_BUCKET", "boreal-sweep-455716-a5.firebasestorage.app")
    GOOGLE_PROJECT_ID = os.environ.get("GOOGLE_PROJECT_ID", "boreal-sweep-455716-a5")
    
    FACEBOOK_CLIENT_TOKEN = os.environ.get("FACEBOOK_CLIENT_TOKEN", "")
    FACEBOOK_APP_SECRET = os.environ.get("FACEBOOK_APP_SECRET", "")
    FACEBOOK_APP_ID = os.environ.get("FACEBOOK_APP_ID", "")
    
    
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
    SPURLY_USER_PROMPT_PATH = os.environ.get("SPURLY_USER_PROMPT_PATH", "resources/spurly_user_prompt.txt")
    SPURLY_INFERENCE_PROMPT = os.environ.get("SPURLY_INFERENCE_PROMPT", "resources/spurly_inference_prompt.txt")
    PROFILE_TEXT_SYSTEM_PROMPT = os.environ.get("PROFILE_TEXT_SYSTEM_PROMPT", "resources/get_profile_text_system_prompt.txt")
    PROFILE_TEXT_USER_PROMPT = os.environ.get("PROFILE_TEXT_USER_PROMPT", "resources/get_profile_text_user_prompt.txt")

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
        "banter_spur": "Energetic, engaging, flirtatious, humorous, joking, good-natured teasing. Use fun language and soft banter—respect boundaries, but keep the conversation going."
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
    
    AI_MODEL = "gpt-4o"
    AI_MESSAGES_ROLE_SYSTEM = "system"
    AI_MESSAGES_ROLE_USER = "user"
    AI_TEMPERATURE_INITIAL = 0.9
    AI_TEMPERATURE_RETRY = .65
    AI_MAX_TOKENS = 2000
    
    ##Used as part of conversation_id to flag conversations extracted via OCR
    OCR_MARKER = "OCR"
    
    DEFAULT_LOG_LEVEL = 20
    
    CONVERSATIONAL_WORDS = ['hi', 'hello', 'hey', 'yo', 'fail', 'refuse', 'sup', 'whats up', 'howdy', 'how are', 'good morning', 'good night', 'good afternoon', 'evening', 'morning', 'night', 'bye', 'goodbye', 'see ya', 'ttyl', 'talk soon', 'later', 'gn', 'gm', 'omw', 'brb', 'lol', 'lmao', 'rofl', 'omg', 'wtf', 'idk', 'idc', 'ikr', 'smh', 'tbh', 'imo', 'imho', 'btw', 'fyi', 'lmk', 'omw', 'asap', 'thx', 'thanks', 'no problem', 'welcome', 'sure', 'ok', 'okay', 'cool', 'kk', 'awesome', 'great', 'nice', 'sweet', 'dope', 'yup', 'yeah', 'yes', 'no', 'nah', 'maybe', 'alright', 'bet', 'for real', 'deadass', 'wanna', 'gonna', 'gotta', 'lemme', 'tell', 'text', 'call', 'haha', 'hehe', 'hahaha', 'lolol', 'ugh', 'omfg', 'jfc', 'omgosh', 'aww', 'yay', 'bruh', 'fam', 'dude', 'bro', 'sis', 'fam', 'what', 'now', 'just', 'chillin', 'bored', 'still', 'tired', 'sleepy', 'wait', 'go', 'hang', 'hang out', 'grab food', 'grab coffee', 'need', 'food', 'free', 'you', 'u up', 'what', 'else', 'you', 'busy', 'me too', 'same', 'here', 'almost', 'there', 'on time', 'got you', 'on it', 'all set', 'got it', 'makes sense', 'fair', 'enough', 'no worries', 'all good', 'no biggie', 'fine', 'worry', 'chill', 'calm', 'cool', 'hold', 'hold up', 'wait up', 'one sec', 'hold on', 'really now', 'so true', 'too real', 'no way', 'wild', 'so cool', 'too funny', 'damn bro', 'sheesh', 'man', 'bro', 'cuz', 'whoa', 'dude', 'wow', 'yikes', 'oof', 'welp', 'ok', 'whatever', 'hmm', 'ya', 'ok', 'kk', 'prob', 'maybe', 'later', 'next', 'not', 'sure', 'lemme see', 'got plans', 'go', 'down', 'Im in', 'count me', 'pass hard', 'hard pass', 'see', 'text later', 'hit me', 'ping me', 'shoot text', 'let know', 'lmk', 'me', 'message me', 'slide in', 'see ya', 'see soon', 'talk', 'later', 'soon', 'ttys', 'ttfn', 'good luck', 'have fun', 'take care', 'stay safe', 'drive safe', 'text home', 'be there', 'same here', 'you too', 'right', 'back', 'low key', 'high key', 'real', 'quick', 'one', 'real quick', 'low', 'effort', 'no cap', 'big mood', 'hot take', 'true that', 'facts', 'deep', 'soft', 'flex', 'hard stop', 'deep', 'cut', 'nice one', 'fun times', 'vibe check', 'we chill', 'stay cool', 'so done', 'too much', 'real quick', 'super chill', 'fast one', 'slow day', 'need nap', 'on break', 'off work', 'in bed', 'just woke', 'ran late', 'got home', 'food time', 'grab drink', 'quick bite', 'new drop', 'fresh fit', 'clean look', 'nice fit', 'sick beat', 'cool song', 'vibe shift', 'we good', 'all set', 'too late', 'next time', 'not now', 'later on', 'same old', 'catch up', 'hit back', 'chill day', 'easy win', 'mid', 'flex', 'somehow', 'fully', 'dead', 'so', 'random', 'this', 'again', 'big', 'deal', 'just', 'saying', 'sayin', 'say', 'bike', 'ride', 'riding', 'love', 'hate', 'want', 'need', 'think', 'feel', 'know', 'see', 'tell', 'ask', 'say', 'my', 'your', 'boo', 'fail', 'refused', 'v2', 'v4']

    SHORT_CONVERSATIONAL_WORDS = ['hi', 'hello', 'hey', 'yo', 'sup', 'bye', 'goodbye', 'see ya', 'ttyl', 'talk soon', 'later', 'gn', 'gm', 'omw', 'brb', 'lol', 'lmao', 'rofl', 'omg', 'wtf', 'idk', 'idc', 'ikr', 'smh', 'tbh', 'imo', 'imho', 'btw', 'fyi', 'lmk', 'asap', 'thx', 'thanks', 'no problem', 'welcome', 'refused', 'fail', 'ok', 'lol', 'wow', 'nice', 'cool', 'good', 'bad', 'yes', 'no', 'maybe', 'sure', 'k', 'kk']
