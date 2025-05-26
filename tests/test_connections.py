# tests/test_connections.py
import pytest
import json
from flask import Flask, g, jsonify
from unittest.mock import patch, MagicMock
# Import BytesIO to simulate file uploads
from io import BytesIO

# Import necessary components from your application
from app import create_app
from config import Config
# Import the service functions we need to mock (adjust path if necessary)
# Note: We will patch them where they are *used* (in routes.connections)
# from services import connection_service

# --- Test Fixtures ---

@pytest.fixture(scope='module')
def app():
    """Create and configure a new app instance for testing."""
    _app = create_app()
    _app.config.from_object(Config)
    _app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        # If exceptions weren't propagating, you might need:
        # "PROPAGATE_EXCEPTIONS": True
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
    return "u:testconnuser99"

@pytest.fixture
def test_connection_id():
    """Provides a consistent test connection ID."""
    return "u:testconnuser99:abcde:p"

# --- Test Cases ---

# Test POST /connection/save
# NOTE: This route still seems to expect JSON based on routes/connections.py line 26
# If it was changed to form-data, this test would need updating too.
@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.save_connection_profile')
def test_save_connection_success(mock_save, mock_decode, client, auth_headers, test_user_id, test_connection_id):
    """Test POST /connection/save - success."""
    mock_decode.return_value = {'user_id': test_user_id}
    # Assuming save_connection_profile now takes a ConnectionProfile object
    # If it still takes a dict, keep the original mock_save assertion
    mock_save.return_value = {"status": "connection profile saved", "connection_id": test_connection_id}
    save_data_dict = {"connection_id": test_connection_id, "user_id": test_user_id, "name": "Test Connection"}

    response = client.post('/connection/connection/save', headers=auth_headers, json=save_data_dict)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "connection profile saved"
    assert json_data["connection_id"] == test_connection_id
    # The route passes request.get_json() directly to save_connection_profile
    mock_save.assert_called_once_with(save_data_dict)


# Test GET /connection/fetch-all
@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.get_user_connections')
def test_fetch_user_connections_success(mock_get_all, mock_decode, client, auth_headers, test_user_id):
    """Test GET /connection/fetch-all - success."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_return_data = [{"connection_id": "id1", "name": "Conn 1"}, {"connection_id": "id2", "name": "Conn 2"}]
    # Assume get_user_connections returns dicts or objects convertible to dicts
    mock_get_all.return_value = mock_return_data

    response = client.get('/connection/connection/fetch-all', headers=auth_headers)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data == mock_return_data
    mock_get_all.assert_called_once_with(test_user_id)

# Test POST /connection/set-active (with connection_id)
@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.set_active_connection_firestore')
def test_set_active_connection_success_with_id(mock_set_active, mock_decode, client, auth_headers, test_user_id, test_connection_id):
    """Test POST /connection/set-active with explicit connection_id."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_set_active.return_value = {"status": "active connection set", "connection_id": test_connection_id}
    post_data = {"connection_id": test_connection_id}

    response = client.post('/connection/connection/set-active', headers=auth_headers, json=post_data)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "active connection set"
    assert json_data["connection_id"] == test_connection_id
    mock_set_active.assert_called_once_with(test_user_id, test_connection_id)

# Test POST /connection/set-active (without connection_id -> hits get_null_connection_id)
# Also need to mock get_null_connection_id where it's used
@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.set_active_connection_firestore')
@patch('routes.connections.get_null_connection_id')
def test_set_active_connection_success_null_id(mock_get_null, mock_set_active, mock_decode, client, auth_headers, test_user_id):
    """Test POST /connection/set-active without connection_id (uses null)."""
    mock_decode.return_value = {'user_id': test_user_id}
    null_conn_id = f"{test_user_id}:null_connection_id:p"
    mock_get_null.return_value = null_conn_id
    mock_set_active.return_value = {"status": "active connection set", "connection_id": null_conn_id}
    post_data = {} # No connection_id provided

    response = client.post('/connection/connection/set-active', headers=auth_headers, json=post_data)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "active connection set"
    assert json_data["connection_id"] == null_conn_id
    mock_get_null.assert_called_once_with(test_user_id) # Verify get_null was called
    mock_set_active.assert_called_once_with(test_user_id, null_conn_id)

# Test GET /connection/get-active
@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.get_active_connection_firestore')
def test_get_active_connection_success(mock_get_active, mock_decode, client, auth_headers, test_user_id, test_connection_id):
    """Test GET /connection/get-active - success."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_active.return_value = test_connection_id # Service returns the ID string

    response = client.get('/connection/connection/get-active', headers=auth_headers)

    assert response.status_code == 200
    # The route directly jsonifies the result string from the service
    assert response.get_data(as_text=True) == f'"{test_connection_id}"\n' # JSON encoded string

    mock_get_active.assert_called_once_with(test_user_id)

# Test DELETE /connection/clear-active
@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.clear_active_connection_firestore')
def test_clear_active_connection_success(mock_clear_active, mock_decode, client, auth_headers, test_user_id):
    """Test DELETE /connection/clear-active - success."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_clear_active.return_value = {"status": "active connection cleared"}

    response = client.delete('/connection/connection/clear-active', headers=auth_headers)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data == {"status": "active connection cleared"}
    mock_clear_active.assert_called_once_with(test_user_id)

# Test POST /connection/create
@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.create_connection_profile') # Target the service function directly
def test_create_connection_success(mock_create_service, mock_decode, client, auth_headers, test_user_id):
    """Test POST /connection/create - success with form data."""
    mock_decode.return_value = {'user_id': test_user_id}
    created_conn_id = f"{test_user_id}:create1:p"
    # Mock service return value (adjust based on actual service format)
    mock_create_service.return_value = {
        "status": "connection profile created",
        "connection_id": created_conn_id,
        "connection_profile": "Formatted profile string..." # Or the dict if service returns that
    }
    # Example form data (no files or links in this test)
    create_form_data = {"name": "New Connection", "age": "33"} # Form data values are strings

    # Send as form data using the 'data' parameter
    response = client.post(
        '/connection/connection/create',
        headers=auth_headers,
        data=create_form_data,
        content_type='multipart/form-data' # Important!
    )

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["status"] == "connection profile created"
    assert json_data["connection_id"] == created_conn_id

    # Assert the service function call
    # The route extracts data, images (empty), links (empty) and calls the service
    mock_create_service.assert_called_once_with(create_form_data, [], [])


# Test GET /connection/fetch-single
@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.get_connection_profile')
def test_fetch_single_connection_success(mock_get_single, mock_decode, client, auth_headers, test_user_id, test_connection_id):
    """Test GET /connection/fetch-single - success."""
    mock_decode.return_value = {'user_id': test_user_id}
    # Mock the service to return a profile object (or dict if that's what it does)
    # Let's assume it returns a dict for simplicity here
    mock_profile_data = {"connection_id": test_connection_id, "name": "Single Conn", "user_id": test_user_id}
    mock_get_single.return_value = mock_profile_data

    response = client.get(f'/connection/connection/fetch-single?connection_id={test_connection_id}', headers=auth_headers)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data == mock_profile_data
    mock_get_single.assert_called_once_with(test_user_id, test_connection_id)

# Test PATCH /connection/update
@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.update_connection_profile') # Target the service function
def test_update_connection_success(mock_update_service, mock_decode, client, auth_headers, test_user_id, test_connection_id):
    """Test PATCH /connection/update - success with form data."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_update_service.return_value = {"status": "connection profile updated"}
    update_form_data = {
        "connection_id": test_connection_id, # ID must be in form data
        "name": "Updated Conn Name",
        "age": "45" # Form data values are strings
    }
    # Route extracts non-id fields for the actual update call data
    expected_update_data_for_service = {k: v for k, v in update_form_data.items() if k != "connection_id"}

    # Send as form data using the 'data' parameter
    response = client.patch(
        '/connection/connection/update',
        headers=auth_headers,
        data=update_form_data,
        content_type='multipart/form-data' # Important!
    )

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data == {"status": "connection profile updated"}

    # Assert the service function call
    # The route calls update_connection_profile(user_id, connection_id, update_data, image_bytes, links)
    mock_update_service.assert_called_once_with(
        test_user_id,
        test_connection_id,
        expected_update_data_for_service, # The dict of fields excluding connection_id
        [], # image_bytes (empty in this test)
        []  # links (empty in this test)
    )


@patch('infrastructure.auth.jwt.decode')
def test_update_connection_fail_missing_id(mock_decode, client, auth_headers, test_user_id):
    """Test PATCH /connection/update - failure due to missing connection_id."""
    mock_decode.return_value = {'user_id': test_user_id}
    update_form_data = {
        # Missing connection_id
        "name": "Updated Conn Name",
        "age": "45"
    }

    response = client.patch(
        '/connection/connection/update',
        headers=auth_headers,
        data=update_form_data,
        content_type='multipart/form-data'
    )

    # Assert the 400 error from the 'if not user_id or not connection_id:' check in the route
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    # Check the error message source marker from the route's logger/jsonify
    assert "[routes] - Error:" in json_data["error"] # Adjust if source name is different


# Test DELETE /connection/delete
# NOTE: This route expects JSON based on routes/connections.py line 117
# If it was changed to form-data, this test would need updating.
@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.delete_connection_profile')
def test_delete_connection_success(mock_delete, mock_decode, client, auth_headers, test_user_id, test_connection_id):
    """Test DELETE /connection/delete - success."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_delete.return_value = {"status": "connection profile deleted"}
    delete_payload = {"connection_id": test_connection_id} # ID needed in JSON payload

    response = client.delete('/connection/connection/delete', headers=auth_headers, json=delete_payload)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data == {"status": "connection profile deleted"}
    mock_delete.assert_called_once_with(test_user_id, test_connection_id)

@patch('infrastructure.auth.jwt.decode')
def test_delete_connection_fail_missing_id(mock_decode, client, auth_headers, test_user_id):
    """Test DELETE /connection/delete - failure due to missing connection_id."""
    mock_decode.return_value = {'user_id': test_user_id}
    delete_payload = {} # Missing connection_id in JSON

    response = client.delete('/connection/connection/delete', headers=auth_headers, json=delete_payload)

    # Assert the 400 error from the 'if not user_id or not connection_id:' check in the route
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    # Check the error message source marker
    assert "[routes] - Error:" in json_data["error"] # Adjust if source name differs


# --- Exception Tests ---

@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.save_connection_profile')
def test_save_connection_exception(mock_save, mock_decode, client, auth_headers, test_user_id):
    """Test POST /connection/save - handles service exception."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_save.side_effect = Exception("Service unavailable")
    save_data = {"name": "Test"} # Assumes save still takes JSON

    # Use pytest.raises to assert that the specific exception is raised
    with pytest.raises(Exception) as excinfo:
        client.post('/connection/connection/save', headers=auth_headers, json=save_data)

    # Check the exception message
    assert "Service unavailable" in str(excinfo.value)

    # Verify mocks were called
    mock_decode.assert_called_once()
    mock_save.assert_called_once_with(save_data)


@patch('infrastructure.auth.jwt.decode')
@patch('routes.connections.get_user_connections')
def test_fetch_user_connections_exception(mock_get_all, mock_decode, client, auth_headers, test_user_id):
    """Test GET /connection/fetch-all - handles service exception."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_all.side_effect = Exception("Database error")

    # Use pytest.raises to assert that the specific exception is raised
    with pytest.raises(Exception) as excinfo:
        client.get('/connection/connection/fetch-all', headers=auth_headers)

    # Check the exception message
    assert "Database error" in str(excinfo.value)

    # Verify mocks were called
    mock_decode.assert_called_once()
    mock_get_all.assert_called_once_with(test_user_id)