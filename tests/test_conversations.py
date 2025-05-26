# tests/test_conversations.py
import pytest
import json
from flask import Flask, g, jsonify
from unittest.mock import patch, MagicMock
from datetime import datetime # Needed for date tests

# Import necessary components from your application
from app import create_app
from config import Config

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
    return "u:testconvoroute1"

# FIX: Correct fixture definition - accept dependency as argument
@pytest.fixture
def test_conversation_id(test_user_id):
    """Provides a consistent test conversation ID."""
    return f"{test_user_id}:convo123:c"

# FIX: Correct fixture definition - accept dependency as argument
@pytest.fixture
def test_spur_id(test_user_id):
    """Provides a consistent test spur ID."""
    return f"{test_user_id}:spurabc:s"

# --- Helper for Date String ---
def get_iso_date_str(dt=None):
    """ Returns an ISO format date string like YYYY-MM-DD """
    if dt is None:
        dt = datetime.utcnow()
    return dt.strftime('%Y-%m-%d')

# --- Test Cases ---

# == Tests for /conversations routes ==

@patch('infrastructure.auth.jwt.decode')
@patch('routes.conversations.get_conversations') # Mock service function
def test_get_conversations_success_no_filters(mock_get_convos, mock_decode, client, auth_headers, test_user_id):
    """Test GET /conversations - success with no filters (L26, L41-42)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_convos.return_value = [{"id": "convo1"}, {"id": "convo2"}]

    response = client.get('/conversations/conversations', headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == [{"id": "convo1"}, {"id": "convo2"}]
    mock_get_convos.assert_called_once_with(test_user_id, {}) # Empty filters expected

@patch('infrastructure.auth.jwt.decode')
@patch('routes.conversations.get_conversations')
def test_get_conversations_success_with_keyword(mock_get_convos, mock_decode, client, auth_headers, test_user_id):
    """Test GET /conversations - success with keyword filter (L28-29)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_convos.return_value = [{"id": "convo_kw"}]
    keyword = "searchterm"

    response = client.get(f'/conversations/conversations?keyword={keyword}', headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == [{"id": "convo_kw"}]
    mock_get_convos.assert_called_once_with(test_user_id, {"keyword": keyword})

@patch('infrastructure.auth.jwt.decode')
@patch('routes.conversations.get_conversations')
def test_get_conversations_success_with_dates(mock_get_convos, mock_decode, client, auth_headers, test_user_id):
    """Test GET /conversations - success with date filters (L30-L34)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_convos.return_value = [{"id": "convo_date"}]
    date_from_str = "2024-01-15"
    date_to_str = "2024-01-31"
    expected_filters = {
        "date_from": datetime.fromisoformat(date_from_str),
        "date_to": datetime.fromisoformat(date_to_str)
    }

    response = client.get(f'/conversations/conversations?date_from={date_from_str}&date_to={date_to_str}', headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == [{"id": "convo_date"}]
    mock_get_convos.assert_called_once_with(test_user_id, expected_filters)

@patch('infrastructure.auth.jwt.decode')
def test_get_conversations_fail_invalid_date_from(mock_decode, client, auth_headers, test_user_id):
    """Test GET /conversations - failure with invalid date_from (L36-L38)."""
    mock_decode.return_value = {'user_id': test_user_id}
    invalid_date = "not-a-date"

    response = client.get(f'/conversations/conversations?date_from={invalid_date}', headers=auth_headers)

    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    # FIX: Check for specific error message content
    assert "Invalid isoformat string" in json_data["error"]

@patch('infrastructure.auth.jwt.decode')
def test_get_conversations_fail_invalid_date_to(mock_decode, client, auth_headers, test_user_id):
    """Test GET /conversations - failure with invalid date_to (L36-L38)."""
    mock_decode.return_value = {'user_id': test_user_id}
    invalid_date = "not-a-date" # Corrected invalid date example for simplicity

    response = client.get(f'/conversations/conversations?date_to={invalid_date}', headers=auth_headers)

    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    # FIX: Check for specific error message content
    assert "Invalid isoformat string" in json_data["error"]

@patch('infrastructure.auth.jwt.decode')
@patch('routes.conversations.save_conversation') # Mock service function
def test_save_conversation_success(mock_save_convo, mock_decode, client, auth_headers, test_user_id, test_conversation_id):
    """Test POST /conversations - success (L47-L54)."""
    mock_decode.return_value = {'user_id': test_user_id}
    post_data = {"conversation": [{"text": "hi"}]}
    mock_save_convo.return_value = {"status": "saved", "conversation_id": test_conversation_id}

    response = client.post('/conversations/conversations', headers=auth_headers, json=post_data)

    assert response.status_code == 200
    assert response.get_json() == {"status": "saved", "conversation_id": test_conversation_id}
    mock_save_convo.assert_called_once_with(post_data)

@patch('infrastructure.auth.jwt.decode')
@patch('routes.conversations.get_conversation') # Mock service function
def test_get_conversation_success(mock_get_convo, mock_decode, client, auth_headers, test_user_id, test_conversation_id):
    """Test GET /conversations/<id> - success (L59-L65)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_convo.return_value = {"id": test_conversation_id, "messages": []}

    response = client.get(f'/conversations/conversations/{test_conversation_id}', headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == {"id": test_conversation_id, "messages": []}
    mock_get_convo.assert_called_once_with(test_conversation_id)

@patch('infrastructure.auth.jwt.decode')
@patch('routes.conversations.delete_conversation') # Mock service function
def test_delete_conversation_success(mock_delete_convo, mock_decode, client, auth_headers, test_user_id, test_conversation_id):
    """Test DELETE /conversations/<id> - success (L70-L76)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_delete_convo.return_value = {"status": "deleted"}

    response = client.delete(f'/conversations/conversations/{test_conversation_id}', headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == {"status": "deleted"}
    mock_delete_convo.assert_called_once_with(test_conversation_id)


# == Tests for /saved-spurs routes ==

@patch('infrastructure.auth.jwt.decode')
@patch('routes.conversations.get_saved_spurs') # Mock service function
def test_fetch_saved_spurs_success_no_filters(mock_get_spurs, mock_decode, client, auth_headers, test_user_id):
    """Test GET /saved-spurs - success with no filters (L81-L87, L109-111)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_spurs.return_value = [{"id": "spur1"}, {"id": "spur2"}]
    # FIX: The route adds default sort='desc' even if no query params are given
    expected_filters = {"sort": "desc"}

    response = client.get('/conversations/saved-spurs', headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == [{"id": "spur1"}, {"id": "spur2"}]
    # FIX: Assert with the implicitly added 'sort' filter
    mock_get_spurs.assert_called_once_with(test_user_id, expected_filters)

@patch('infrastructure.auth.jwt.decode')
@patch('routes.conversations.get_saved_spurs')
def test_fetch_saved_spurs_success_with_variant_situation(mock_get_spurs, mock_decode, client, auth_headers, test_user_id):
    """Test GET /saved-spurs - success with variant/situation filters (L88-L91)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_spurs.return_value = [{"id": "spur_vs"}]
    variant = "warm"
    situation = "follow_up"
    # FIX: The route also includes the default 'sort' filter if not specified
    expected_filters = {"variant": variant, "situation": situation} # Initial expectation
    # Let's verify what the route *actually* builds if sort isn't given
    # sort = request.args.get("sort", "desc") -> sort becomes "desc"
    # if sort in ["asc", "desc"]: filters["sort"] = sort -> filters["sort"] = "desc"
    expected_filters_with_sort = {"variant": variant, "situation": situation, "sort": "desc"}


    response = client.get(f'/conversations/saved-spurs?variant={variant}&situation={situation}', headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == [{"id": "spur_vs"}]
    # FIX: Assert with the implicitly added 'sort' filter
    mock_get_spurs.assert_called_once_with(test_user_id, expected_filters_with_sort)


@patch('infrastructure.auth.jwt.decode')
@patch('routes.conversations.get_saved_spurs')
def test_fetch_saved_spurs_success_with_dates_keyword_sort(mock_get_spurs, mock_decode, client, auth_headers, test_user_id):
    """Test GET /saved-spurs - success with dates, keyword, sort filters (L93-97, L102-103, L105-107)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_get_spurs.return_value = [{"id": "spur_all_filters"}]
    date_from_str = "2024-02-01"
    date_to_str = "2024-02-29"
    keyword = "coffee"
    sort = "asc"
    expected_filters = {
        "date_from": datetime.fromisoformat(date_from_str),
        "date_to": datetime.fromisoformat(date_to_str),
        "keyword": keyword,
        "sort": sort
    }

    response = client.get(f'/conversations/saved-spurs?date_from={date_from_str}&date_to={date_to_str}&keyword={keyword}&sort={sort}', headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == [{"id": "spur_all_filters"}]
    mock_get_spurs.assert_called_once_with(test_user_id, expected_filters)

@patch('infrastructure.auth.jwt.decode')
def test_fetch_saved_spurs_fail_invalid_date_from(mock_decode, client, auth_headers, test_user_id):
    """Test GET /saved-spurs - failure with invalid date_from (L98-L101)."""
    mock_decode.return_value = {'user_id': test_user_id}
    invalid_date = "not-a-real-date"

    response = client.get(f'/conversations/saved-spurs?date_from={invalid_date}', headers=auth_headers)

    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    # FIX: Check the specific error format for this route's except block
    assert "[routes] - Error:" in json_data["error"]

@patch('infrastructure.auth.jwt.decode')
def test_fetch_saved_spurs_fail_invalid_date_to(mock_decode, client, auth_headers, test_user_id):
    """Test GET /saved-spurs - failure with invalid date_to (L98-L101)."""
    mock_decode.return_value = {'user_id': test_user_id}
    invalid_date = "2024-13-01" # Invalid month

    response = client.get(f'/conversations/saved-spurs?date_to={invalid_date}', headers=auth_headers)

    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    # FIX: Check the specific error format for this route's except block
    assert "[routes] - Error:" in json_data["error"]

@patch('infrastructure.auth.jwt.decode')
@patch('routes.conversations.save_spur') # Mock service function
def test_save_spur_success(mock_save_spur_svc, mock_decode, client, auth_headers, test_user_id, test_spur_id):
    """Test POST /saved-spurs - success (L116-L124)."""
    mock_decode.return_value = {'user_id': test_user_id}
    post_data = {"text": "saved spur text", "variant": "warm"}
    mock_save_spur_svc.return_value = {"status": "spur saved", "spur_id": test_spur_id}

    response = client.post('/conversations/saved-spurs', headers=auth_headers, json=post_data)

    assert response.status_code == 200
    assert response.get_json() == {"status": "spur saved", "spur_id": test_spur_id}
    mock_save_spur_svc.assert_called_once_with(test_user_id, post_data)

@patch('infrastructure.auth.jwt.decode')
@patch('routes.conversations.delete_saved_spur') # Mock service function
def test_delete_saved_spur_success(mock_delete_spur_svc, mock_decode, client, auth_headers, test_user_id, test_spur_id):
    """Test DELETE /saved-spurs/<id> - success (L130-L137)."""
    mock_decode.return_value = {'user_id': test_user_id}
    mock_delete_spur_svc.return_value = {"status": "spur deleted"}

    response = client.delete(f'/conversations/saved-spurs/{test_spur_id}', headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == {"status": "spur deleted"}
    mock_delete_spur_svc.assert_called_once_with(test_user_id, test_spur_id)