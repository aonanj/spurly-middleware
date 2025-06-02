import jwt
from functools import wraps
from flask import request, g, jsonify, current_app
import logging
from typing import Dict, Any
from infrastructure.logger import get_logger

logger = get_logger(__name__)

def verify_token(f):
    """
    Decorator to verify JWT token and extract user information.
    Sets g.user with the decoded token data.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None

        # Get token from Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                # Expected format: "Bearer <token>"
                token = auth_header.split(' ')[1]
            except IndexError:
                return jsonify({'error': 'Invalid authorization header format'}), 401

        if not token:
            return jsonify({'error': f'Authorization token is missing. path: {request.path}, method: {request.method}'}), 401

        try:
            # Decode the token
            secret_key = current_app.config.get('JWT_SECRET_KEY')
            if not secret_key:
                logger.error("JWT_SECRET_KEY not configured")
                return jsonify({'error': 'Server configuration error'}), 500

            # Decode and verify the token
            payload = jwt.decode(token, secret_key, algorithms=['HS256'])

            # Set user info in g for use in the route
            g.user = {
                'user_id': payload.get('user_id'),
                'email': payload.get('email'),
                'name': payload.get('name')
            }

            # Verify user_id exists
            if not g.user['user_id']:
                return jsonify({'error': 'Invalid token: missing user_id'}), 401

        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid token: {str(e)}")
            return jsonify({'error': 'Invalid token'}), 401
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            return jsonify({'error': 'Token verification failed'}), 401

        return f(*args, **kwargs)

    return decorated_function


def handle_errors(f):
    """
    Decorator to handle exceptions in routes.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Unhandled error in {f.__name__}: {str(e)}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    return decorated_function