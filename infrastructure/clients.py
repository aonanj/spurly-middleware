# infrastructure/clients.py

#from algoliasearch.search.client import SearchClientSync
import firebase_admin
from firebase_admin import firestore, credentials
from google.oauth2 import service_account
import openai
import os

# Local application imports
# Use relative import if logger is in the same directory
from google.cloud import vision
from google.cloud.firestore import Client as FirestoreClient
from .logger import get_logger 
# --- Global Client Variables ---
# Initialize clients to None initially

_vision_client = None
_openai_client = None
_firestore_db = None

logger = get_logger(__name__)

# --- Initialization Function ---
def init_clients(app):
    """
    Initializes API clients, including OpenAI, Google Cloud services;
    sets global environment constants based on Flask app config.

    Args:
        app: Flask app object providing configuration.
    """
    logger.error("LOG.INFO: Initializing external clients...")
    global _firestore_db

    # --- Firebase Admin ---
    try:
        if not firebase_admin._apps:
            cred_path = os.environ.get("GOOGLE_CLOUD_FIREBASE_CREDS")
            if not cred_path or not os.path.exists(cred_path):
                ##DEBUG
                cred_path = ""
                 ##raise FileNotFoundError(f"Firebase Admin key file not found at: {cred_path}")
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {'storageBucket': 'boreal-sweep-455716.firebasestorage.app'})
            logger.error("LOG.INFO: Firebase Admin initialized.")
        else:
             logger.error("LOG.INFO: Firebase Admin already initialized.")
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
        logger.error("LOG.INFO: Firestore client initialized.")
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
        logger.error("LOG.INFO: Google Cloud Vision client initialized.")
    except Exception as e:
        logger.error("Failed to initialize Google Cloud Vision client: %s", e, exc_info=True)
        raise RuntimeError("Vision client has not been initialized.")

    # --- OpenAI Client ---
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in configuration.")
        # Initialize the main OpenAI client object
        _openai_client = openai.OpenAI(api_key=api_key)
        logger.error("LOG.INFO: OpenAI client initialized.")
        # If you were using separate clients before, you now access methods via this client:
        # e.g., openai_client.chat.completions.create(...)
        # e.g., openai_client.moderations.create(...)
    except Exception as e:
        logger.error("Failed to initialize OpenAI client: %s", e, exc_info=True)
        raise RuntimeError("OpenAI client has not been initialized.")

    logger.error("LOG.INFO: All external clients initialized successfully.")
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
