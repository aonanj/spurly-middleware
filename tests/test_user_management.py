# tests/test_user_management.py
import pytest
import json
from flask import Flask, g, jsonify
# IMPORTANT: Import patch from unittest.mock
from unittest.mock import patch, MagicMock

# Import necessary components from your application
from app import create_app
from config import Config
from class_defs.profile_def import UserProfile
import routes.onboarding
import routes.user_management

# --- Test Fixtures ---

@pytest.fixture(scope='module')
def app():
    """Create and configure a new app instance for testing."""
    _app = create_app()
    _app.config.from_object(Config)
    _app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key", # Use a fixed secret key for tests
        "JWT_EXPIRATION": 3600 # Short expiration for tests if needed
    })

    # Push an application context
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
    # This token is just a placeholder, the actual auth check is mocked below
    return {"Authorization": "Bearer test-token"}

@pytest.fixture
def test_user_id():
    """Provides a consistent test user ID."""
    return "u:testmanageuser1"

# --- Test Cases ---

# Test GET /user
# Patch jwt.decode where it's USED in infrastructure.auth
@patch('infrastructure.auth.jwt.decode')
@patch('routes.user_management.get_user_profile')
# Add mock_decode to the function signature
def test_get_user_success(mock_get_profile, mock_decode, client, app, auth_headers, test_user_id):
    """Test successful retrieval of user profile."""
    # Configure the mock for jwt.decode
    mock_decode.return_value = {'user_id': test_user_id, 'exp': 9999999999, 'iat': 0} # Simulate successful decode

    # Mock the service function return value
    mock_profile_data = {
        "user_id": test_user_id,
        "age": 28,
        "name": "Test Manager",
        "selected_spurs": ["main_spur", "warm_spur"]
        # Add other fields as necessary based on UserProfile definition
    }
    # The service function returns a UserProfile object
    mock_get_profile.return_value = UserProfile.from_dict(mock_profile_data)

    # No need to manually set g.user here, the mocked decorator handle will do it
    response = client.get('/user/user', headers=auth_headers) # Route is /user/user

    assert response.status_code == 200
    assert response.content_type == 'application/json'
    json_data = response.get_json()
    # The route returns jsonify(profile), where profile is the UserProfile object
    # UserProfile doesn't have a default to_dict, so we compare key fields
    # Accessing __dict__ works for simple dataclasses if no custom to_dict exists
    assert json_data['user_id'] == mock_profile_data['user_id']
    assert json_data['age'] == mock_profile_data['age']
    assert json_data['name'] == mock_profile_data['name']
    assert json_data['selected_spurs'] == mock_profile_data['selected_spurs']

    # Assertions on mocks
    mock_decode.assert_called_once_with(
        "test-token", # The token string from auth_headers
        app.config['SECRET_KEY'],
        algorithms=["HS256"]
    )
    mock_get_profile.assert_called_once_with(test_user_id)


# Test POST /user (Update)
# Patch jwt.decode where it's USED in infrastructure.auth
@patch('infrastructure.auth.jwt.decode')
@patch('routes.user_management.update_user_profile')
# Add mock_decode to the function signature
def test_update_user_success(mock_update_profile, mock_decode, client, app, auth_headers, test_user_id):
    """Test successful update of user profile."""
    # Configure the mock for jwt.decode
    mock_decode.return_value = {'user_id': test_user_id, 'exp': 9999999999, 'iat': 0} # Simulate successful decode

    update_data = {
        "name": "Updated Name",
        "age": 31,
        "job": "Developer",
        "greenlights": ["coding", "testing"]
    }
    # Mock the return value of update_user_profile (it returns a Flask Response)
    # Let's mock the data *within* the jsonify response
    mock_update_profile.return_value = jsonify({
        "user_id": test_user_id,
        "user_profile": {**update_data, "user_id": test_user_id} # Simulate returned data
    })

    response = client.post('/user/user', headers=auth_headers, json=update_data)

    assert response.status_code == 200 # Expecting 200 based on route code
    assert response.content_type == 'application/json'
    json_data = response.get_json()
    assert json_data['user_id'] == test_user_id
    assert json_data['user_profile']['name'] == update_data['name']
    assert json_data['user_profile']['age'] == update_data['age']
    assert json_data['user_profile']['job'] == update_data['job']
    assert json_data['user_profile']['greenlights'] == update_data['greenlights']

    # Assert mocks
    mock_decode.assert_called_once() # Called by the decorator
    # Assert that the service function was called correctly by the route
    # The route calls update_user_profile(user_id, data_dict)
    mock_update_profile.assert_called_once_with(test_user_id, update_data)

# These tests don't need jwt.decode mock if validation fails before auth check
# (or if auth check happens first and fails, but here we assume it passes for validation tests)
# If auth is checked first, you might need the jwt.decode mock here too. Assuming validation first for now.
# Add @patch('infrastructure.auth.jwt.decode') if needed based on execution order.
def test_update_user_fail_age_low(client, app, auth_headers, test_user_id):
    """Test profile update failure when age is below 18."""
    update_data = {"age": 17, "name": "Too Young"}

    # Simulate auth passing IF it runs before validation in your app flow
    with patch('infrastructure.auth.jwt.decode') as mock_decode:
        mock_decode.return_value = {'user_id': test_user_id, 'exp': 9999999999, 'iat': 0}
        response = client.post('/user/user', headers=auth_headers, json=update_data)

    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    # Check error message source from the route
    assert "[routes] - Error" in json_data["error"]

def test_update_user_fail_age_type(client, app, auth_headers, test_user_id):
    """Test profile update failure when age is not an integer."""
    update_data = {"age": "thirty", "name": "Invalid Age Type"}

    # Simulate auth passing IF it runs before validation
    with patch('infrastructure.auth.jwt.decode') as mock_decode:
        mock_decode.return_value = {'user_id': test_user_id, 'exp': 9999999999, 'iat': 0}
        response = client.post('/user/user', headers=auth_headers, json=update_data)

    assert response.status_code == 400 # Age validation happens before service call
    json_data = response.get_json()
    assert "error" in json_data
    assert "[routes] - Error" in json_data["error"]


# Test DELETE /user
# Patch jwt.decode where it's USED in infrastructure.auth
@patch('infrastructure.auth.jwt.decode')
@patch('routes.user_management.delete_user_profile')
# Add mock_decode to the function signature
def test_delete_user_success(mock_delete_profile, mock_decode, client, app, auth_headers, test_user_id):
    """Test successful deletion of user profile."""
    # Configure the mock for jwt.decode
    mock_decode.return_value = {'user_id': test_user_id, 'exp': 9999999999, 'iat': 0} # Simulate successful decode

    # Mock the service function to return a truthy value (dict indicates success)
    mock_delete_profile.return_value = {"status": "user profile successfully deleted"}

    response = client.delete('/user/user', headers=auth_headers)

    assert response.status_code == 200
    json_data = response.get_json()
    assert "message" in json_data
    assert "deleted successfully" in json_data["message"]

    # Assert mocks
    mock_decode.assert_called_once() # Called by the decorator
    mock_delete_profile.assert_called_once_with(test_user_id)

# Patch jwt.decode where it's USED in infrastructure.auth
@patch('infrastructure.auth.jwt.decode')
@patch('routes.user_management.delete_user_profile')
# Add mock_decode to the function signature
def test_delete_user_fail_service(mock_delete_profile, mock_decode, client, app, auth_headers, test_user_id):
    """Test user deletion failure if service returns falsey."""
    # Configure the mock for jwt.decode
    mock_decode.return_value = {'user_id': test_user_id, 'exp': 9999999999, 'iat': 0} # Simulate successful decode

    # Mock the service function to return something falsey (e.g., None or False)
    mock_delete_profile.return_value = None # Or False, simulating failure

    response = client.delete('/user/user', headers=auth_headers)

    assert response.status_code == 200 # Route returns 200 even on logical failure
    json_data = response.get_json()
    assert "message" in json_data
    assert "ERROR - user profile not deleted" in json_data["message"]

    # Assert mocks
    mock_decode.assert_called_once()
    mock_delete_profile.assert_called_once_with(test_user_id)

# Patch jwt.decode where it's USED in infrastructure.auth
@patch('infrastructure.auth.jwt.decode')
@patch('routes.user_management.delete_user_profile')
# Add mock_decode to the function signature
def test_delete_user_fail_exception(mock_delete_profile, mock_decode, client, app, auth_headers, test_user_id):
    """Test user deletion failure if service raises exception."""
    # Configure the mock for jwt.decode
    mock_decode.return_value = {'user_id': test_user_id, 'exp': 9999999999, 'iat': 0} # Simulate successful decode

    # Mock the service function to raise an exception
    mock_delete_profile.side_effect = Exception("Database error")

    response = client.delete('/user/user', headers=auth_headers)

    assert response.status_code == 500 # Exception triggers 500 error
    json_data = response.get_json()
    assert "error" in json_data
    assert "[routes] - Error: Database error" in json_data["error"]

    # Assert mocks
    mock_decode.assert_called_once()
    mock_delete_profile.assert_called_once_with(test_user_id)

# Add these test functions to tests/test_user_management.py

@patch('infrastructure.auth.jwt.decode')
@patch('routes.user_management.update_user_profile') # Mock the function that will fail
def test_update_user_fail_exception(mock_update_profile, mock_decode, client, app, auth_headers, test_user_id):
    """Test POST /user general exception handling (expecting 401)."""
    # Configure the mock for jwt.decode
    mock_decode.return_value = {'user_id': test_user_id, 'exp': 9999999999, 'iat': 0}
    # Configure update_user_profile to raise a generic exception
    mock_update_profile.side_effect = Exception("Unexpected update error")

    update_data = {"name": "Data that causes failure"} # Data content doesn't matter here

    response = client.post('/user/user', headers=auth_headers, json=update_data)

    # Assertions for the except block in update_user_bp
    assert response.status_code == 401 # Route returns 401 in this specific except block
    assert response.content_type == 'application/json'
    json_data = response.get_json()
    assert "error" in json_data
    # Check the specific error format from that block
    assert "[routes] - Error" in json_data["error"] # Check source only, msg depends on exception

    # Assert mocks
    mock_decode.assert_called_once()
    mock_update_profile.assert_called_once_with(test_user_id, update_data)


@patch('infrastructure.auth.jwt.decode')
@patch('routes.user_management.get_user_profile') # Mock the function that will fail
def test_get_user_fail_exception(mock_get_profile, mock_decode, client, app, auth_headers, test_user_id):
    """Test GET /user general exception handling (expecting 500)."""
    # Configure the mock for jwt.decode
    mock_decode.return_value = {'user_id': test_user_id, 'exp': 9999999999, 'iat': 0}
    # Configure get_user_profile to raise a generic exception
    mock_get_profile.side_effect = Exception("Unexpected get error")

    response = client.get('/user/user', headers=auth_headers)

    # Assertions for the except block in get_user_bp
    assert response.status_code == 500 # Route returns 500 in this specific except block
    assert response.content_type == 'application/json'
    json_data = response.get_json()
    assert "error" in json_data
    assert "[routes] - Error: Unexpected get error" in json_data["error"]

    # Assert mocks
    mock_decode.assert_called_once()
    mock_get_profile.assert_called_once_with(test_user_id)