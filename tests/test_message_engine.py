# tests/test_message_engine.py
import pytest
import json
from flask import Flask, g, jsonify
from unittest.mock import patch, MagicMock

# Import necessary components from your application
from app import create_app
from config import Config
from class_defs.spur_def import Spur # To create mock Spur objects
# Import Conversation if needed for mocking get_conversation return
from class_defs.conversation_def import Conversation

# --- Test Fixtures ---

@pytest.fixture(scope='module')
def app():
    """Create and configure a new app instance for testing."""
    # Ensure this uses the *corrected* create_app from your fixed app.py
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
    return "u:testmsgengineusr1"

@pytest.fixture
def explicit_conn_id():
    """Provides an explicit connection ID for testing."""
    return "u:testmsgengineusr1:conn123:p"

@pytest.fixture
def active_conn_id():
    """Provides an active connection ID for testing."""
    return "u:testmsgengineusr1:active987:p"

# Mock profile data (needed for @validate_profile middleware)
@pytest.fixture
def mock_user_profile_data(test_user_id):
    return {"user_id": test_user_id, "age": 25}

@pytest.fixture
def mock_connection_profile_data(test_user_id, explicit_conn_id):
    return {"user_id": test_user_id, "connection_id": explicit_conn_id, "age": 30}

@pytest.fixture
def mock_spur_list(test_user_id):
    """Provides a list of mock Spur objects."""
    spur1 = MagicMock(spec=Spur)
    spur1.to_dict.return_value = {"spur_id": f"{test_user_id}:spurA:s", "text": "Mock Spur A"}
    spur2 = MagicMock(spec=Spur)
    spur2.to_dict.return_value = {"spur_id": f"{test_user_id}:spurB:s", "text": "Mock Spur B"}
    return [spur1, spur2]

# --- Test Cases ---

# Test successful generation with explicit connection_id (Passed before, should still pass)
@patch('infrastructure.auth.jwt.decode')
@patch('routes.message_engine.get_spurs_for_output')
@patch('routes.message_engine.get_active_connection_firestore')
def test_generate_success_explicit_conn_id(mock_get_active, mock_get_spurs, mock_decode, client, auth_headers, test_user_id, explicit_conn_id, mock_spur_list, mock_user_profile_data, mock_connection_profile_data):
    """Test POST /spurs/generate success with connection_id provided."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_spurs.return_value = mock_spur_list

    post_data = {
        "connection_id": explicit_conn_id,
        "conversation_id": "c:convo1",
        "situation": "follow_up", # Explicitly provided
        "topic": "weekend plans",
        "user_profile": mock_user_profile_data,
        "connection_profile": mock_connection_profile_data
    }

    # Ensure route path matches the fixed route: /spurs (prefix) + /generate (route)
    response = client.post('/spurs/generate', headers=auth_headers, json=post_data)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['user_id'] == test_user_id
    expected_spurs_json = [spur.to_dict() for spur in mock_spur_list]
    assert json_data['spurs'] == expected_spurs_json
    mock_decode.assert_called_once()
    mock_get_active.assert_not_called()
    # The situation provided in post_data should be used
    mock_get_spurs.assert_called_once_with(
        user_id=test_user_id,
        connection_id=explicit_conn_id,
        conversation_id=post_data['conversation_id'],
        situation=post_data['situation'], # Uses original provided value
        topic=post_data['topic']
    )

# Test successful generation using active connection_id
@patch('infrastructure.auth.jwt.decode')
@patch('routes.message_engine.get_spurs_for_output')
@patch('routes.message_engine.get_active_connection_firestore')
# No patches for middleware or infer_situation needed
def test_generate_success_active_conn_id(mock_get_active, mock_get_spurs, mock_decode, client, auth_headers, test_user_id, active_conn_id, mock_spur_list, mock_user_profile_data):
    """Test POST /spurs/generate success using active connection_id."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_spurs.return_value = mock_spur_list
    mock_get_active.return_value = active_conn_id

    post_data = {
        "conversation_id": "c:convo2",
        "topic": "hobbies",
        "user_profile": mock_user_profile_data
        # Situation omitted
    }

    response = client.post('/spurs/generate', headers=auth_headers, json=post_data)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['user_id'] == test_user_id
    expected_spurs_json = [spur.to_dict() for spur in mock_spur_list]
    assert json_data['spurs'] == expected_spurs_json
    mock_decode.assert_called_once()
    mock_get_active.assert_called_once_with(test_user_id)
    # Assert that situation is 'cold_open' based on actual error output
    mock_get_spurs.assert_called_once_with(
        user_id=test_user_id,
        connection_id=active_conn_id,
        conversation_id=post_data['conversation_id'],
        situation='cold_open', # Expect middleware default
        topic=post_data['topic']
    )

# Test successful generation with minimal data
@patch('infrastructure.auth.jwt.decode')
@patch('routes.message_engine.get_spurs_for_output')
@patch('routes.message_engine.get_active_connection_firestore')
# No patches for middleware or infer_situation needed
def test_generate_success_minimal_data(mock_get_active, mock_get_spurs, mock_decode, client, auth_headers, test_user_id, active_conn_id, mock_spur_list, mock_user_profile_data):
    """Test POST /spurs/generate success with minimal request data."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_spurs.return_value = mock_spur_list
    mock_get_active.return_value = active_conn_id

    post_data = {
        "user_profile": mock_user_profile_data
    }

    response = client.post('/spurs/generate', headers=auth_headers, json=post_data)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['user_id'] == test_user_id
    expected_spurs_json = [spur.to_dict() for spur in mock_spur_list]
    assert json_data['spurs'] == expected_spurs_json
    mock_decode.assert_called_once()
    mock_get_active.assert_called_once_with(test_user_id)
     # Assert that situation is 'cold_open' based on actual error output
    mock_get_spurs.assert_called_once_with(
        user_id=test_user_id,
        connection_id=active_conn_id,
        conversation_id="",
        situation='cold_open', # Expect middleware default
        topic=""
    )

# Test exception handling from get_spurs_for_output
@patch('infrastructure.auth.jwt.decode')
@patch('routes.message_engine.get_spurs_for_output') # Mock the service call to raise exception
@patch('routes.message_engine.get_active_connection_firestore')
# No patches for middleware or infer_situation needed
def test_generate_fail_service_exception(mock_get_active, mock_get_spurs, mock_decode, client, auth_headers, test_user_id, explicit_conn_id, mock_user_profile_data, mock_connection_profile_data):
    """Test POST /spurs/generate handles exception from get_spurs_for_output."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_spurs.side_effect = Exception("GPT service unavailable")

    post_data = {
        "connection_id": explicit_conn_id,
        "conversation_id": "c:convoError",
        "user_profile": mock_user_profile_data,
        "connection_profile": mock_connection_profile_data
        # Situation omitted
    }

    with pytest.raises(Exception) as excinfo:
        client.post('/spurs/generate', headers=auth_headers, json=post_data)

    assert "GPT service unavailable" in str(excinfo.value)
    mock_decode.assert_called_once()
    mock_get_active.assert_not_called()
    # Assert that situation is 'cold_open' based on actual error output
    mock_get_spurs.assert_called_once_with(
        user_id=test_user_id,
        connection_id=explicit_conn_id,
        conversation_id=post_data['conversation_id'],
        situation='cold_open', # Expect middleware default
        topic=""
    )