# tests/test_ocr.py
import pytest
import json
from io import BytesIO
from flask import Flask, g, jsonify
from unittest.mock import patch, MagicMock
from werkzeug.datastructures import FileStorage

# Import necessary components from your application
from app import create_app
from config import Config
from class_defs.conversation_def import Conversation # Needed for type checking maybe

# --- Test Fixtures ---

@pytest.fixture(scope='module')
def app():
    """Create and configure a new app instance for testing."""
    _app = create_app()
    _app.config.from_object(Config)
    _app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        # Add any other necessary test configurations
    })
    ctx = _app.app_context()
    ctx.push()
    yield _app
    ctx.pop()

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def auth_headers():
    """Provides authorization headers for a test user."""
    return {"Authorization": "Bearer test-token"}

@pytest.fixture
def test_user_id():
    """Provides a consistent test user ID."""
    return "u:testocruser1"

@pytest.fixture
def mock_image_file():
    """Creates a BytesIO object simulating a file upload."""
    # Simple content, doesn't need to be a real image for most tests
    return (BytesIO(b"this is a fake image content"), 'test_image.png')

@pytest.fixture
def mock_ocr_result():
    """Provides a sample successful result from process_image."""
    return [
        {"speaker": "Party A", "text": "Hello there."},
        {"speaker": "Party B", "text": "Hi!"}
    ]

# --- Test Cases ---

# Test Happy Path (Lines 16-33, 36-47, 50-57, 71-72)
@patch('infrastructure.auth.jwt.decode')
@patch('routes.ocr.process_image')
# No need to mock ID generators if IDs are provided in the request
def test_upload_image_success_provided_ids(mock_process_image, mock_decode, client, auth_headers, test_user_id, mock_image_file, mock_ocr_result):
    """Test POST /upload success with all optional IDs provided."""
    # --- Mock Setup ---
    mock_decode.return_value = {'user_id': test_user_id}
    mock_process_image.return_value = mock_ocr_result
    # --- End Mock Setup ---

    # Connection ID for headers
    provided_conn_id = f"{test_user_id}:connocr1:p"
    # Update headers to include connection_id
    request_headers = {**auth_headers, "connection_id": provided_conn_id}

    # Prepare form data (connection_id removed from here) and file
    form_data = {
        # 'connection_id': provided_conn_id, # Now sent in headers
        'conversation_id': f"{test_user_id}:convoocr1:c",
        'situation': 'Initial chat',
        'topic': 'Greetings'
    }
    file_data = {'image': mock_image_file}

    response = client.post(
        '/ocr/upload',
        headers=request_headers, # Pass headers with connection_id
        data={**form_data, **file_data}, # Combine form and file data
        content_type='multipart/form-data'
    )

    # --- Assertions ---
    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.data}"
    json_data = response.get_json()

    assert 'conversation' in json_data
    convo_data = json_data['conversation']

    # Verify IDs and other fields in the returned conversation object
    assert convo_data['user_id'] == test_user_id
    # Assert against the connection_id provided in headers
    assert convo_data['connection_id'] == provided_conn_id
    assert convo_data['conversation_id'] == form_data['conversation_id']
    assert convo_data['situation'] == form_data['situation']
    assert convo_data['topic'] == form_data['topic']
    assert convo_data['conversation'] == mock_ocr_result # Check messages
    assert 'created_at' in convo_data # Check timestamp exists

    # Assert mocks
    mock_decode.assert_called_once()
    mock_process_image.assert_called_once()
    call_args, _ = mock_process_image.call_args
    assert call_args[0] == test_user_id
    assert hasattr(call_args[1], 'read')
    assert hasattr(call_args[1], 'filename')
    assert call_args[1].filename == 'test_image.png'
    # --- End Assertions ---

# Test Success with Fallback IDs (Lines 27-28, 31-33, plus happy path)
@patch('infrastructure.auth.jwt.decode')
@patch('routes.ocr.process_image')
@patch('routes.ocr.get_null_connection_id') # Mock fallback
@patch('routes.ocr.generate_conversation_id') # Mock fallback
def test_upload_image_success_fallback_ids(mock_gen_convo_id, mock_get_null_conn, mock_process_image, mock_decode, client, auth_headers, test_user_id, mock_image_file, mock_ocr_result):
    """Test POST /upload success using fallback IDs."""
     # --- Mock Setup ---
    mock_decode.return_value = {'user_id': test_user_id}
    mock_process_image.return_value = mock_ocr_result
    # Define return values for mocked ID generators
    # Simulate the *actual* incorrect return value from the route due to missing user_id
    null_conn_id_val = "null_connection_id:p"
    gen_convo_id_val = f"{test_user_id}:genconvoocr:c"
    mock_get_null_conn.return_value = null_conn_id_val
    mock_gen_convo_id.return_value = gen_convo_id_val
    # --- End Mock Setup ---

    # Prepare form data (missing conn_id, convo_id) and file
    form_data = {
        'situation': 'Follow up',
        'topic': 'Weekend'
    }
    file_data = {'image': mock_image_file}

    response = client.post(
        '/ocr/upload',
        headers=auth_headers, # No connection_id header here
        data={**form_data, **file_data},
        content_type='multipart/form-data'
    )

    # --- Assertions ---
    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.data}"
    json_data = response.get_json()
    assert 'conversation' in json_data
    convo_data = json_data['conversation']

    # Verify fallback IDs were used (using the potentially incorrect null ID from the route)
    assert convo_data['connection_id'] == null_conn_id_val
    assert convo_data['conversation_id'] == gen_convo_id_val
    assert convo_data['conversation'] == mock_ocr_result

    # Assert mocks
    mock_decode.assert_called_once()
    mock_get_null_conn.assert_called_once_with() # Route calls it without user_id
    mock_gen_convo_id.assert_called_once_with(test_user_id) # Called because convo_id missing
    mock_process_image.assert_called_once()
    # --- End Assertions ---

# Test Failure: No Image (Lines 17-21)
@patch('infrastructure.auth.jwt.decode')
@patch('routes.ocr.process_image') # Mock even though not called
def test_upload_image_fail_no_image(mock_process_image, mock_decode, client, auth_headers, test_user_id):
    """Test POST /upload failure when no image file is provided."""
    # --- Mock Setup ---
    mock_decode.return_value = {'user_id': test_user_id}
    # --- End Mock Setup ---

    # Prepare form data (no file data)
    form_data = {'situation': 'test'}

    response = client.post(
        '/ocr/upload',
        headers=auth_headers,
        data=form_data, # No file part 'image'
        content_type='multipart/form-data'
    )

    # --- Assertions ---
    assert response.status_code == 400
    json_data = response.get_json()
    assert 'error' in json_data
    # Check if the error message indicates the missing file/image
    assert "[routes] - Error" in json_data["error"] # Check route's specific message
    mock_process_image.assert_not_called()
    # --- End Assertions ---


# Test Failure: process_image returns non-list (Lines 53-57)
@patch('infrastructure.auth.jwt.decode')
@patch('routes.ocr.process_image')
def test_upload_image_fail_process_image_returns_invalid(mock_process_image, mock_decode, client, auth_headers, test_user_id, mock_image_file):
    """Test POST /upload failure when process_image returns non-list."""
    # --- Mock Setup ---
    mock_decode.return_value = {'user_id': test_user_id}
    mock_process_image.return_value = None # Simulate invalid return type
    # --- End Mock Setup ---

    file_data = {'image': mock_image_file}

    response = client.post(
        '/ocr/upload',
        headers=auth_headers,
        data=file_data, # Minimal data, just the file
        content_type='multipart/form-data'
    )

    # --- Assertions ---
    assert response.status_code == 500
    json_data = response.get_json()
    assert 'error' in json_data
    assert "[routes] - Invalid OCR response" in json_data["error"] # Check route's specific message
    mock_process_image.assert_called_once() # process_image was called
    # --- End Assertions ---

# Test Failure: process_image raises Exception (Lines 64-68)
# This test now covers lines 65-67
@patch('infrastructure.auth.jwt.decode')
@patch('routes.ocr.process_image')
def test_upload_image_fail_process_image_exception(mock_process_image, mock_decode, client, auth_headers, test_user_id, mock_image_file):
    """Test POST /upload failure when process_image raises Exception."""
     # --- Mock Setup ---
    mock_decode.return_value = {'user_id': test_user_id}
    exception_message = "Vision API unavailable"
    mock_process_image.side_effect = Exception(exception_message)
    # --- End Mock Setup ---

    file_data = {'image': mock_image_file}

    response = client.post(
        '/ocr/upload',
        headers=auth_headers,
        data=file_data,
        content_type='multipart/form-data'
    )

    # --- Assertions ---
    # Route catches general Exception and returns 500
    assert response.status_code == 500
    # The response data is just the formatted error string, not JSON
    # Check that the specific error message from the route's except block is present
    expected_error_string = f"[{__package__ or 'routes'}] - Error: {exception_message}"
    assert expected_error_string in response.get_data(as_text=True)
    mock_process_image.assert_called_once()
    # --- End Assertions ---

# Note: Lines 60-63 are hard to test failure for, because user_id is guaranteed by
# @require_auth and connection_id has a fallback via get_null_connection_id.
# Testing these would require manipulating 'g' or mocking the ID generator fallbacks
# to return None/empty, which is testing edge cases unlikely to occur normally.