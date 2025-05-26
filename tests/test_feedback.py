# tests/test_feedback.py
import pytest
import json
from flask import Flask, g, jsonify
from unittest.mock import patch, MagicMock, ANY # ANY is useful for objects

# Import necessary components from your application
from app import create_app
from config import Config
from class_defs.spur_def import Spur # Import Spur class

# --- Test Fixtures ---

@pytest.fixture(scope='module')
def app():
    """Create and configure a new app instance for testing."""
    _app = create_app()
    _app.config.from_object(Config)
    _app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
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
    return "u:testfeedbackuser1"

@pytest.fixture
def sample_spur_dict(test_user_id):
    """Provides a sample spur dictionary as might be sent in the request."""
    # Needs fields required by Spur.from_dict
    return {
        "user_id": test_user_id,
        "spur_id": f"{test_user_id}:feedbackspur:s",
        "created_at": "2024-01-01T10:00:00Z", # Example ISO string
        "text": "Sample spur text",
        "variant": "warm",
        "situation": "test_sit",
        "topic": "test_topic",
        "tone": "neutral",
        "conversation_id": f"{test_user_id}:convofeedback:c",
        "connection_id": f"{test_user_id}:connfeedback:p"
        # Add/adjust fields based on Spur.from_dict requirements
    }

# --- Test Cases ---

@patch('infrastructure.auth.jwt.decode')
@patch('routes.feedback.Spur.from_dict') # Patch class method where it's used
@patch('routes.feedback.save_spur')
@patch('routes.feedback.anonymize_spur')
def test_feedback_success_thumbs_up(mock_anonymize, mock_save, mock_from_dict, mock_decode, client, auth_headers, test_user_id, sample_spur_dict):
    """Test POST /feedback - success path for 'thumbs_up'."""
    mock_decode.return_value = {'user_id': test_user_id}
    # This is the data the client sends, which request.get_json() will return inside the route
    post_data = {"spur": sample_spur_dict, "feedback": "thumbs_up"}
    # Make Spur.from_dict return a mock Spur object
    mock_spur_obj = MagicMock(spec=Spur)
    mock_from_dict.return_value = mock_spur_obj
    # Make save_spur return a value
    save_result = {"status": "spur saved", "spur_id": sample_spur_dict["spur_id"]}
    mock_save.return_value = save_result

    # Client sends the JSON data
    response = client.post('/feedback/feedback', headers=auth_headers, json=post_data)

    assert response.status_code == 200
    # Route returns the result from save_spur
    assert response.get_json() == save_result
    mock_from_dict.assert_called_once_with(sample_spur_dict)
    mock_save.assert_called_once_with(test_user_id, mock_spur_obj)
    mock_anonymize.assert_called_once_with(mock_spur_obj, True) # Adjusted based on route code L25

@patch('infrastructure.auth.jwt.decode')
@patch('routes.feedback.Spur.from_dict')
@patch('routes.feedback.save_spur')
@patch('routes.feedback.anonymize_spur')
def test_feedback_success_thumbs_down(mock_anonymize, mock_save, mock_from_dict, mock_decode, client, auth_headers, test_user_id, sample_spur_dict):
    """Test POST /feedback - success path for 'thumbs_down'."""
    mock_decode.return_value = {'user_id': test_user_id}
    # Client sends JSON data
    post_data = {"spur": sample_spur_dict, "feedback": "thumbs_down"}
    # Make Spur.from_dict return a mock Spur object
    mock_spur_obj = MagicMock(spec=Spur)
    mock_from_dict.return_value = mock_spur_obj

    response = client.post('/feedback/feedback', headers=auth_headers, json=post_data)

    assert response.status_code == 200
    # Route initializes result=[] and returns it if not thumbs_up
    assert response.get_json() == []
    mock_from_dict.assert_called_once_with(sample_spur_dict)
    mock_save.assert_not_called() # Should not be called for thumbs_down
    mock_anonymize.assert_called_once_with(mock_spur_obj, False) # Corrected based on route code L27

@patch('infrastructure.auth.jwt.decode')
def test_feedback_fail_missing_spur(mock_decode, client, auth_headers, test_user_id):
    """Test POST /feedback - failure missing 'spur' field."""
    mock_decode.return_value = {'user_id': test_user_id}
    # Client sends JSON data lacking 'spur'
    post_data = {"feedback": "thumbs_up"} # Missing 'spur'

    response = client.post('/feedback/feedback', headers=auth_headers, json=post_data)

    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["error"] == "Missing required feedback fields"

@patch('infrastructure.auth.jwt.decode')
def test_feedback_fail_missing_feedback_type(mock_decode, client, auth_headers, test_user_id, sample_spur_dict):
    """Test POST /feedback - failure missing 'feedback' field."""
    mock_decode.return_value = {'user_id': test_user_id}
    # Client sends JSON data lacking 'feedback'
    post_data = {"spur": sample_spur_dict} # Missing 'feedback'

    response = client.post('/feedback/feedback', headers=auth_headers, json=post_data)

    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["error"] == "Missing required feedback fields"

@patch('infrastructure.auth.jwt.decode')
@patch('routes.feedback.Spur.from_dict') # Mock the method that fails
@patch('routes.feedback.save_spur')     # Ensure downstream mocks exist even if not called
@patch('routes.feedback.anonymize_spur')
def test_feedback_fail_bad_spur_data(mock_anonymize, mock_save, mock_from_dict, mock_decode, client, auth_headers, test_user_id):
    """Test POST /feedback - failure on bad spur data for Spur.from_dict."""
    mock_decode.return_value = {'user_id': test_user_id}
    # Simulate client sending bad spur data
    bad_spur_data = {"invalid": "data", "spur_id": "badspur"} # Missing required fields for Spur.from_dict
    post_data = {"spur": bad_spur_data, "feedback": "thumbs_up"}
    # Configure Spur.from_dict to raise an exception
    mock_from_dict.side_effect = KeyError("Missing 'created_at'")

    # Expect exception to propagate as route has no try/except here
    with pytest.raises(KeyError) as excinfo:
        client.post('/feedback/feedback', headers=auth_headers, json=post_data)

    assert "Missing 'created_at'" in str(excinfo.value)
    mock_from_dict.assert_called_once_with(bad_spur_data)
    mock_save.assert_not_called()
    mock_anonymize.assert_not_called()

@patch('infrastructure.auth.jwt.decode')
def test_feedback_fail_no_json_data(mock_decode, client, auth_headers, test_user_id):
    """Test POST /feedback - failure when no JSON data is sent."""
    mock_decode.return_value = {'user_id': test_user_id}

    # Send request without JSON payload or Content-Type header
    response = client.post('/feedback/feedback', headers=auth_headers)

    # Expect Flask/Werkzeug to return 415 Unsupported Media Type
    assert response.status_code == 415
    # Optional: Check the body for a relevant message if needed, but 415 is key
    # assert b"Unsupported Media Type" in response.data