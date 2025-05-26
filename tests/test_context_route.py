# tests/test_context_route.py
import pytest
import json
from flask import Flask, g, jsonify
from unittest.mock import patch, MagicMock, create_autospec

# Import necessary components from your application
from app import create_app
from config import Config
# Import classes needed for mocking return values
from class_defs.profile_def import UserProfile, ConnectionProfile

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
    return "u:testcontextuser1"

@pytest.fixture
def test_connection_id():
    """Provides a consistent test connection ID."""
    return "u:testcontextuser1:conn123:p"

@pytest.fixture
def mock_user_profile(test_user_id):
    """Provides a mock UserProfile object."""
    # Using create_autospec ensures the mock has the expected attributes/methods
    # Or create a real instance: return UserProfile(user_id=test_user_id, age=30)
    mock_profile = create_autospec(UserProfile, instance=True)
    mock_profile.user_id = test_user_id
    mock_profile.to_dict.return_value = {"user_id": test_user_id, "name": "Mock User", "age": 30}
    return mock_profile

@pytest.fixture
def mock_connection_profile(test_user_id, test_connection_id):
    """Provides a mock ConnectionProfile object."""
    # Or create a real instance: return ConnectionProfile(user_id=test_user_id, connection_id=test_connection_id, name="Mock Conn")
    mock_profile = create_autospec(ConnectionProfile, instance=True)
    mock_profile.user_id = test_user_id
    mock_profile.connection_id = test_connection_id
    mock_profile.to_dict.return_value = {"user_id": test_user_id, "connection_id": test_connection_id, "name": "Mock Conn"}
    return mock_profile

# --- Test Cases ---

# Test POST /context/connection (set_connection_context)
# =========================================================

@patch('infrastructure.auth.jwt.decode') # For @require_auth
@patch('routes.context_route.get_current_user')
@patch('routes.context_route.get_connection_profile')
@patch('routes.context_route.set_current_connection')
def test_set_conn_context_success(mock_set_conn, mock_get_conn_profile, mock_get_user, mock_decode, client, auth_headers, test_user_id, test_connection_id, mock_user_profile, mock_connection_profile):
    """Test POST /context/connection - success path."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_user.return_value = mock_user_profile
    mock_get_conn_profile.return_value = mock_connection_profile

    response = client.post('/context/connection', headers=auth_headers, json={"connection_id": test_connection_id})

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["message"] == "Connection context set successfully."
    mock_get_user.assert_called_once()
    mock_get_conn_profile.assert_called_once_with(test_user_id, test_connection_id)
    mock_set_conn.assert_called_once_with(mock_connection_profile)

@patch('infrastructure.auth.jwt.decode')
@patch('routes.context_route.get_current_user') # Mock this to return None
@patch('routes.context_route.get_connection_profile')
@patch('routes.context_route.set_current_connection')
def test_set_conn_context_fail_no_user(mock_set_conn, mock_get_conn_profile, mock_get_user, mock_decode, client, auth_headers, test_user_id, test_connection_id):
    """Test POST /context/connection - failure when no user context (L17)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_user.return_value = None # Simulate user context not loaded

    response = client.post('/context/connection', headers=auth_headers, json={"connection_id": test_connection_id})

    assert response.status_code == 401
    json_data = response.get_json()
    assert json_data["error"] == "User context not loaded"
    mock_get_user.assert_called_once()
    mock_get_conn_profile.assert_not_called() # Should exit before this
    mock_set_conn.assert_not_called()

@patch('infrastructure.auth.jwt.decode')
@patch('routes.context_route.get_current_user')
# No need to mock get_connection_profile as it shouldn't be reached
def test_set_conn_context_fail_missing_id(mock_get_user, mock_decode, client, auth_headers, test_user_id, mock_user_profile):
    """Test POST /context/connection - failure when connection_id missing (L22)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_user.return_value = mock_user_profile

    response = client.post('/context/connection', headers=auth_headers, json={}) # Empty JSON

    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["error"] == "Missing connection_id"
    mock_get_user.assert_called_once()

@patch('infrastructure.auth.jwt.decode')
@patch('routes.context_route.get_current_user')
def test_set_conn_context_fail_no_json(mock_get_user, mock_decode, client, auth_headers, test_user_id, mock_user_profile):
    """Test POST /context/connection - failure when JSON is invalid/missing (L20-21 -> L22)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_user.return_value = mock_user_profile

    # Send invalid JSON or missing content-type to make get_json(silent=True) return None
    response = client.post('/context/connection', headers=auth_headers, data="not json")

    assert response.status_code == 400
    json_data = response.get_json()
    assert json_data["error"] == "Missing connection_id" # Because connection_id becomes None
    mock_get_user.assert_called_once()


@patch('infrastructure.auth.jwt.decode')
@patch('routes.context_route.get_current_user')
@patch('routes.context_route.get_connection_profile') # Mock this to return None
@patch('routes.context_route.set_current_connection')
def test_set_conn_context_fail_profile_not_found(mock_set_conn, mock_get_conn_profile, mock_get_user, mock_decode, client, auth_headers, test_user_id, test_connection_id, mock_user_profile):
    """Test POST /context/connection - failure when profile not found (L26)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_user.return_value = mock_user_profile
    mock_get_conn_profile.return_value = None # Simulate profile not found

    response = client.post('/context/connection', headers=auth_headers, json={"connection_id": test_connection_id})

    assert response.status_code == 404
    json_data = response.get_json()
    assert json_data["error"] == "Connection profile not found"
    mock_get_user.assert_called_once()
    mock_get_conn_profile.assert_called_once_with(test_user_id, test_connection_id)
    mock_set_conn.assert_not_called() # Should exit before this


# Test DELETE /context/connection (clear_connection_context)
# ===========================================================

@patch('infrastructure.auth.jwt.decode') # For @require_auth
@patch('routes.context_route.clear_current_connection') # Mock the context function
def test_clear_conn_context_success(mock_clear_conn, mock_decode, client, auth_headers, test_user_id):
    """Test DELETE /context/connection - success path (L35-36)."""
    mock_decode.return_value = {'user_id': test_user_id}

    response = client.delete('/context/connection', headers=auth_headers)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["message"] == "Connection context cleared."
    mock_clear_conn.assert_called_once()

# Test GET /context/ (get_context)
# =================================

@patch('infrastructure.auth.jwt.decode') # For @require_auth
@patch('routes.context_route.get_current_user')
@patch('routes.context_route.get_current_connection')
def test_get_context_success_both_present(mock_get_conn, mock_get_user, mock_decode, client, auth_headers, test_user_id, mock_user_profile, mock_connection_profile):
    """Test GET /context/ - success with user and connection (L41-47)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_user.return_value = mock_user_profile
    mock_get_conn.return_value = mock_connection_profile

    response = client.get('/context/', headers=auth_headers)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["user_profile"] == mock_user_profile.to_dict()
    assert json_data["connection_profile"] == mock_connection_profile.to_dict()
    mock_get_user.assert_called_once()
    mock_get_conn.assert_called_once()

@patch('infrastructure.auth.jwt.decode') # For @require_auth
@patch('routes.context_route.get_current_user')
@patch('routes.context_route.get_current_connection')
def test_get_context_success_user_only(mock_get_conn, mock_get_user, mock_decode, client, auth_headers, test_user_id, mock_user_profile):
    """Test GET /context/ - success with user only (L41-47)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_user.return_value = mock_user_profile
    mock_get_conn.return_value = None # No connection context set

    response = client.get('/context/', headers=auth_headers)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["user_profile"] == mock_user_profile.to_dict()
    assert json_data["connection_profile"] is None # Expect null for connection
    mock_get_user.assert_called_once()
    mock_get_conn.assert_called_once()

@patch('infrastructure.auth.jwt.decode') # For @require_auth
@patch('routes.context_route.get_current_user')
@patch('routes.context_route.get_current_connection')
def test_get_context_success_no_context(mock_get_conn, mock_get_user, mock_decode, client, auth_headers, test_user_id):
    """Test GET /context/ - success with no user or connection (L41-47)."""
    # This covers the user=None case, even if unlikely post-auth
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_user.return_value = None # Simulate no user context
    mock_get_conn.return_value = None # Simulate no connection context

    response = client.get('/context/', headers=auth_headers)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["user_profile"] is None
    assert json_data["connection_profile"] is None
    mock_get_user.assert_called_once()
    mock_get_conn.assert_called_once()