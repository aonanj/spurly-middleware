from flask import request, jsonify, current_app, g
from datetime import datetime, timedelta, timezone
from functools import wraps
from .logger import get_logger
import jwt

logger = get_logger(__name__)

def create_jwt(user_id:str) -> str:
    """
    Creates a JWT token to validate user session. Encodes JWT token using user_id and global setting for session expiration
    
    Args
        user_id: User ID for which created token is valid.
            str
    
    Return
        Token encoding user_id, token expiration using SECRET_KEY
            str

    """
    try:
        expiration_delta = timedelta(seconds=current_app.config['JWT_EXPIRATION'])
        expires = datetime.now(timezone.utc) + expiration_delta

        payload = {
            "user_id": user_id,
            "exp": expires,
            "iat": datetime.now(timezone.utc)
        }
        token = jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm="HS256")
        logger.log(current_app.config['DEFAULT_LOG_LEVEL'], f"JWT token successfully encoded for user: {user_id}")
        return token
    except Exception as e:
        logger.error("Create JWT token failed for user %s: %s", user_id, e, exc_info=True)
        raise jwt.PyJWKError(f"Create JWT token failed for user {user_id}: {e}") from e


def decode_jwt(token: str) -> dict:
    """
    Decodes a JWT token to validate user session. 
    
    Args
        token: JWT token encoded with a user ID 
            str
    
    Return
        Payload encoded into the JWT token, including user ID
            str

    """
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError as e:
        logger.error("[%s] Error: %s Create JWT token failed for user", __name__, e)
        raise jwt.ExpiredSignatureError
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT: {e}")
        raise jwt.InvalidTokenError
    except Exception as e: # Catch other potential issues during decoding
         logger.error(f"JWT decoding error: {e}", exc_info=True)
         raise jwt.InvalidTokenError("Token decoding failed") from e

def require_auth(f):
    """
    Wrapper (decorator) validating a session on function calls. 
    
    Args
        function: function called for which session needs validation  
            function
    
    Return
        Decorated function object that is defined inside the decorator
            Decorated function 

    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            parts = auth_header.split()

            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
            else:
                logger.error("Error: JWT token invalid for user", __name__)
                raise jwt.InvalidTokenError
            
        if not token:
            logger.error("Error: JWT token missing for user", __name__)
            raise jwt.InvalidTokenError

        try:
            payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
            g.user = payload
        except jwt.ExpiredSignatureError as e:
            logger.error("[%s] Error: %s User token is expired", __name__, e)
            raise jwt.ExpiredSignatureError
        except jwt.InvalidTokenError as e:
            logger.error("[%s] Error: %s User token is invalid", __name__, e)
            raise jwt.InvalidTokenError
        except Exception as e:
            logger.error("[%s] Error: %s User not authorized", __name__, e)
            raise e
        
        return f(*args, **kwargs)
    return decorated
