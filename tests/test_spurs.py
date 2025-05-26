# tests/test_spurs.py
import pytest
import json
from datetime import datetime
from flask import Flask, g, jsonify
from unittest.mock import patch, MagicMock

# Import necessary components from your application
from app import create_app
from config import Config
# Import specific functions/classes if needed for mocking return values
# from class_defs.spur_def import Spur

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
    return "u:testspursuser1"

@pytest.fixture
def test_spur_id():
    """Provides a consistent test spur ID."""
    return "u:testspursuser1:spurabc:s"

# --- Test Cases ---

# == Test GET /spurs/ (fetch_saved_spurs_bp) == # Updated URL
@patch('infrastructure.auth.jwt.decode')
@patch('routes.spurs.get_saved_spurs') # Target function in the spurs route file
def test_fetch_saved_spurs_no_filters(mock_get_saved, mock_decode, client, auth_headers, test_user_id):
    """Test GET /spurs/ success with no filters.""" # Updated URL in docstring
    mock_decode.return_value = {'user_id': test_user_id}
    mock_spurs = [{"spur_id": "s1", "text": "Spur 1"}, {"spur_id": "s2", "text": "Spur 2"}]
    mock_get_saved.return_value = mock_spurs

    response = client.get('/spurs/', headers=auth_headers) # Updated URL

    assert response.status_code == 200
    assert response.get_json() == mock_spurs
    # Default sort is 'desc' if not provided
    mock_get_saved.assert_called_once_with(test_user_id, {'sort': 'desc'})

@patch('infrastructure.auth.jwt.decode')
@patch('routes.spurs.get_saved_spurs')
def test_fetch_saved_spurs_with_filters(mock_get_saved, mock_decode, client, auth_headers, test_user_id):
    """Test GET /spurs/ success with various filters.""" # Updated URL in docstring
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_saved.return_value = [{"spur_id": "s3", "text": "Filtered Spur"}]
    date_from_str = "2024-03-10"
    date_to_str = "2024-03-20"
    expected_filters = {
        'variant': 'warm',
        'situation': 'follow_up',
        'date_from': datetime.fromisoformat(date_from_str),
        'date_to': datetime.fromisoformat(date_to_str),
        'keyword': 'hello',
        'sort': 'asc'
    }

    query_string = f"?variant=warm&situation=follow_up&date_from={date_from_str}&date_to={date_to_str}&keyword=hello&sort=asc"
    response = client.get(f'/spurs/{query_string}', headers=auth_headers) # Updated URL

    assert response.status_code == 200
    assert response.get_json() == [{"spur_id": "s3", "text": "Filtered Spur"}]
    mock_get_saved.assert_called_once_with(test_user_id, expected_filters)

@patch('infrastructure.auth.jwt.decode')
@patch('routes.spurs.get_saved_spurs') # Mock to prevent actual call
def test_fetch_saved_spurs_invalid_date_from(mock_get_saved, mock_decode, client, auth_headers, test_user_id):
    """Test GET /spurs/ failure with invalid date_from.""" # Updated URL in docstring
    mock_decode.return_value = {'user_id': test_user_id}

    response = client.get('/spurs/?date_from=not-a-date', headers=auth_headers) # Updated URL

    assert response.status_code == 400
    json_data = response.get_json()
    assert 'error' in json_data
    # Check the specific error message format from the route
    assert "[routes] - Error:" in json_data["error"]
    mock_get_saved.assert_not_called()

@patch('infrastructure.auth.jwt.decode')
@patch('routes.spurs.get_saved_spurs') # Mock to prevent actual call
def test_fetch_saved_spurs_invalid_date_to(mock_get_saved, mock_decode, client, auth_headers, test_user_id):
    """Test GET /spurs/ failure with invalid date_to.""" # Updated URL in docstring
    mock_decode.return_value = {'user_id': test_user_id}

    response = client.get('/spurs/?date_to=2024-13-01', headers=auth_headers) # Updated URL, Invalid month

    assert response.status_code == 400
    json_data = response.get_json()
    assert 'error' in json_data
    # Check the specific error message format from the route
    assert "[routes] - Error:" in json_data["error"]
    mock_get_saved.assert_not_called()


# == Test POST /spurs/ (save_spur_bp) == # Updated URL

@patch('infrastructure.auth.jwt.decode')
@patch('routes.spurs.save_spur') # Target function in the spurs route file
def test_save_spur_success(mock_save, mock_decode, client, auth_headers, test_user_id, test_spur_id):
    """Test POST /spurs/ success.""" # Updated URL in docstring
    mock_decode.return_value = {'user_id': test_user_id}
    # Ensure post_data includes fields needed by the service layer (save_spur)
    # which likely instantiates a Spur object internally.
    post_data = {
        "spur_id": test_spur_id,
        "user_id": test_user_id,
        "text": "Saved this spur",
        "variant": "cool",
        "created_at": datetime.now().isoformat() + "Z", # Needed for Spur.from_dict
        # Add other required fields if save_spur service expects them
    }
    mock_save.return_value = {"status": "spur saved", "spur_id": test_spur_id}

    response = client.post('/spurs/', headers=auth_headers, json=post_data) # Updated URL

    assert response.status_code == 200, f"Response data: {response.data}"
    assert response.get_json() == {"status": "spur saved", "spur_id": test_spur_id}
    # The route passes user_id and the raw data dict to the service
    mock_save.assert_called_once_with(test_user_id, post_data)


# == Test DELETE /spurs/<spur_id> (delete_saved_spurs_bp) == # Updated URL

@patch('infrastructure.auth.jwt.decode')
@patch('routes.spurs.delete_saved_spur') # Target function in the spurs route file
def test_delete_saved_spur_success(mock_delete, mock_decode, client, auth_headers, test_user_id, test_spur_id):
    """Test DELETE /spurs/<spur_id> success.""" # Updated URL in docstring
    mock_decode.return_value = {'user_id': test_user_id}
    mock_delete.return_value = {"status": "spur deleted"}

    response = client.delete(f'/spurs/{test_spur_id}', headers=auth_headers) # Updated URL

    assert response.status_code == 200
    assert response.get_json() == {"status": "spur deleted"}
    mock_delete.assert_called_once_with(test_user_id, test_spur_id)


# == Test GET /spurs/<spur_id> (get_spur_bp) == # Updated URL

@patch('infrastructure.auth.jwt.decode')
@patch('routes.spurs.get_spur') # Target function in the spurs route file
def test_get_spur_success(mock_get, mock_decode, client, auth_headers, test_user_id, test_spur_id):
    """Test GET /spurs/<spur_id> success.""" # Updated URL in docstring
    mock_decode.return_value = {'user_id': test_user_id}
    # Assume get_spur returns a dict representation of the Spur
    spur_data = {"spur_id": test_spur_id, "text": "Fetched spur", "user_id": test_user_id}
    mock_get.return_value = spur_data

    response = client.get(f'/spurs/{test_spur_id}', headers=auth_headers) # Updated URL

    assert response.status_code == 200
    assert response.get_json() == spur_data
    mock_get.assert_called_once_with(test_spur_id)