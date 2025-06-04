# infrastructure/clients.py

from algoliasearch.search.client import SearchClientSync
import firebase_admin
from firebase_admin import initialize_app, firestore, get_app, credentials
from flask import current_app
from google.oauth2 import service_account
import openai
import os

# Local application imports
from .logger import get_logger # Use relative import if logger is in the same directory
from google.cloud import vision
from google.cloud.firestore import Client as FirestoreClient
# --- Global Client Variables ---
# Initialize clients to None initially

_vision_client = None
_openai_client = None
_algolia_client = None
_algolia_index = None 
_firestore_db = None


# --- Initialization Function ---
def init_clients(app):
    """
    Initializes API clients, including OpenAI, Google Cloud services;
    sets global environment constants based on Flask app config.

    Args:
        app: Flask app object providing configuration.
    """


    logger = get_logger(__name__)
    logger.info("Initializing external clients...")
    global _firestore_db

    # --- Firebase Admin ---
    try:
        if not firebase_admin._apps:
            cred_path = os.getenv("GOOGLE_CLOUD_FIREBASE_CREDS")
            if not cred_path or not os.path.exists(cred_path):
                 raise FileNotFoundError(f"Firebase Admin key file not found at: {cred_path}")
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {'storageBucket': 'boreal-sweep-455716-a5.firebasestorage.app'})
            logger.info("Firebase Admin initialized.")
        else:
             logger.info("Firebase Admin already initialized.")
    except Exception as e:
        logger.error("Failed to initialize Firebase Admin: %s", e, exc_info=True)
        raise RuntimeError("Firebase Admin client has not been initialized.")

    # --- Firestore Client ---
    try:
        firestore_cred_path = os.getenv("GOOGLE_CLOUD_FIRESTORE_CREDS")
        if not firestore_cred_path or not os.path.exists(firestore_cred_path):
             raise FileNotFoundError(f"Firestore key file not found at: {firestore_cred_path}")
        firestore_creds = service_account.Credentials.from_service_account_file(firestore_cred_path)
        # Ensure project_id is correctly inferred or explicitly provided
        _firestore_db = firestore.client()
        logger.info("Firestore client initialized.")
    except Exception as e:
        logger.error("Failed to initialize Firestore client: %s", e, exc_info=True)
        raise RuntimeError("Firestore client has not been initialized.")

    # --- Google Cloud Vision Client ---
    try:
        vision_cred_path = os.getenv("GOOGLE_CLOUD_VISION_CREDS")
        if not vision_cred_path or not os.path.exists(vision_cred_path):
             raise FileNotFoundError(f"Vision API key file not found at: {vision_cred_path}")
        vision_creds = service_account.Credentials.from_service_account_file(vision_cred_path)
        _vision_client = vision.ImageAnnotatorClient(credentials=vision_creds)
        logger.info("Google Cloud Vision client initialized.")
    except Exception as e:
        logger.error("Failed to initialize Google Cloud Vision client: %s", e, exc_info=True)
        raise RuntimeError("Vision client has not been initialized.")

    # --- Algolia Search Client ---
    try:
        algolia_app_id = os.getenv("ALGOLIA_APP_ID")
        algolia_search_api_key = os.getenv("ALGOLIA_SEARCH_API_KEY")
        algolia_index_name = os.getenv("ALGOLIA_INDEX_NAME")

        if not all([algolia_app_id, algolia_search_api_key, algolia_index_name]):
            raise ValueError("Algolia configuration (APP_ID, SEARCH_API_KEY, INDEX_NAME) missing.")

        _algolia_client = SearchClientSync(algolia_app_id, algolia_search_api_key)
        logger.info(f"Algolia client initialized for index: {algolia_index_name}")
    except Exception as e:
        logger.error("Failed to initialize Algolia client: %s", e, exc_info=True)
        # Decide if this should be a fatal error (raise RuntimeError) or allow fallback
        logger.warning("Algolia client failed to initialize. Keyword search will be unavailable.")
        _algolia_client = None
        _algolia_index = None # Ensure index is None if client fails

    # --- OpenAI Client ---
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in configuration.")
        # Initialize the main OpenAI client object
        _openai_client = openai.OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized.")
        # If you were using separate clients before, you now access methods via this client:
        # e.g., openai_client.chat.completions.create(...)
        # e.g., openai_client.moderations.create(...)
    except Exception as e:
        logger.error("Failed to initialize OpenAI client: %s", e, exc_info=True)
        raise RuntimeError("OpenAI client has not been initialized.")

    logger.info("All external clients initialized successfully.")
def get_firestore_db() -> FirestoreClient:
    """ Safely returns the initialized Firestore client instance. """
    global _firestore_db
    if not _firestore_db:
        try:
            _firestore_db = firestore.client()
        except Exception as e:
            raise RuntimeError("Firestore client has not been initialized.")
    return _firestore_db


def get_vision_client() -> vision.ImageAnnotatorClient:
    """ Safely returns the initialized Google Cloud Vision client instance. """
    global _vision_client
    if not _vision_client:
        try:
            _vision_client = vision.ImageAnnotatorClient()
        except Exception as e:
            raise RuntimeError("Vision client has not been initialized.")
    return _vision_client

def get_openai_client() -> openai.OpenAI:
    """ Safely returns the initialized OpenAI client instance. """
    global _openai_client
    if not _openai_client:
        try:
            _openai_client = openai.OpenAI()
        except Exception as e:
            raise RuntimeError("OpenAI client has not been initialized.")
    return _openai_client

def get_algolia_client():
    """ Safely returns the initialized Algolia index instance. """
    if _algolia_client is None:
           return None
    return _algolia_client