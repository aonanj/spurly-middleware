import pytest
import json
from flask import Flask, current_app # Import current_app
from unittest.mock import patch, MagicMock
from werkzeug.exceptions import InternalServerError
from class_defs.profile_def import BaseProfile
from dataclasses import fields

from app import create_app
from config import Config
# Import the class being checked
from class_defs.profile_def import UserProfile
import routes.onboarding
import routes.user_management

# Assuming your Flask app is created in 'app.py' by a function called 'create_app'
# And your onboarding blueprint is in 'routes/onboarding.py'
from app import create_app
# Make sure config is loaded for the test app
from config import Config

@pytest.fixture(scope='module') # Changed scope for efficiency
def app():
    """Create and configure a new app instance for testing."""
    _app = create_app()
    _app.config.from_object(Config) # Ensure config is loaded
    _app.config.update({
        "TESTING": True,
        # You might need to mock client initializations if they run at import time
        # or prevent them from running during tests if they interfere.
    })

    # --- FIX: Push an application context ---
    ctx = _app.app_context()
    ctx.push()

    yield _app # Use the app within the context

    ctx.pop() # Clean up the context when done

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

# --- Test Cases ---

# --- Update the test ---
# Patch format_user_profile where it's LOOKED UP (in routes.onboarding)
@patch('routes.onboarding.format_user_profile')
# Patch save_user_profile where it's LOOKED UP (in routes.onboarding)
@patch('routes.onboarding.save_user_profile')
@patch('routes.onboarding.create_jwt')
@patch('routes.onboarding.generate_user_id')
def test_onboarding_success_minimal(mock_gen_id, mock_create_jwt, mock_save_profile, mock_format_profile, client, app): # Added app fixture
    """Test successful onboarding with minimal valid data."""
    test_user_id = "u:testuserid123"
    test_token = "test.jwt.token"
    mock_gen_id.return_value = test_user_id
    mock_create_jwt.return_value = test_token
    # Mock save_user_profile to return a success dictionary
    mock_save_profile.return_value = {"status": "user profile successfully saved"}
    # Mock format_user_profile to return a predictable string for assertion
    expected_profile_string = f"user_id: {test_user_id}\nAge: 25\nSelected Spurs: main_spur, warm_spur, cool_spur, playful_spur" # Example expected format
    mock_format_profile.return_value = expected_profile_string

    data = {"age": 25}
    response = client.post('/onboarding/onboarding', json=data)

    # Assertions
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}. Response: {response.get_data(as_text=True)}"
    assert response.content_type == 'application/json'
    json_data = response.get_json()
    assert json_data['user_id'] == test_user_id
    assert json_data['token'] == test_token # Check token is returned
    assert json_data['user_profile'] == expected_profile_string # Check against mocked format

    # Mock Call Assertions
    mock_gen_id.assert_called_once()
    mock_create_jwt.assert_called_once_with(test_user_id)

    # Check save_user_profile call
    mock_save_profile.assert_called_once()
    # Expected call: save_user_profile(user_id, profile_data_dict)
    call_args, call_kwargs = mock_save_profile.call_args
    assert call_args[0] == test_user_id # Check user_id passed
    saved_data_arg = call_args[1] # Check the dict passed
    assert isinstance(saved_data_arg, UserProfile)
    assert saved_data_arg.age == 25
    assert saved_data_arg.user_id == test_user_id # Check user_id in dict
    # Get default spurs from app config within the test context
    assert saved_data_arg.selected_spurs == list(app.config['SPUR_VARIANTS'])
    # Check optional fields weren't added incorrectly if not provided
    assert saved_data_arg.name is None # 'name' wasn't in input data
    assert saved_data_arg.greenlights == []


    # Check format_user_profile call
    mock_format_profile.assert_called_once()
    format_call_args, format_call_kwargs = mock_format_profile.call_args
    assert isinstance(format_call_args[0], UserProfile) # Check it got a UserProfile object
    assert format_call_args[0].user_id == test_user_id
    assert format_call_args[0].age == 25
    assert format_call_args[0].selected_spurs == list(app.config['SPUR_VARIANTS'])


@patch('routes.onboarding.format_user_profile')
@patch('routes.onboarding.generate_user_id') # Correct order might matter (apply bottom-up)
@patch('routes.onboarding.create_jwt')
@patch('routes.onboarding.save_user_profile')
# Add mock_format_profile to the function signature
def test_onboarding_success_with_details(mock_save_profile, mock_create_jwt, mock_gen_id, mock_format_profile, client, app): # Added app fixture and mock_format_profile
    """Test successful onboarding with more profile details."""
    test_user_id = "u:testuserid456"
    mock_gen_id.return_value = test_user_id
    mock_create_jwt.return_value = "test.jwt.token.more"
    # Mock save return value
    mock_save_profile.return_value = {"status": "user profile successfully saved"}

    # --- Add mock return value for format_user_profile ---
    expected_profile_str = (
        f"user_id: {test_user_id}\nAge: 30\nName: Test User\n"
        f"Gender: Non-binary\nJob: Tester\n"
        f"Greenlight Topics: Hiking, Testing\nRedlight Topics: Bugs\n" # Example format
        f"Selected Spurs: main_spur, warm_spur, cool_spur, playful_spur" # Include default spurs
    )
    mock_format_profile.return_value = expected_profile_str
    # --- End Add ---

    data = {
        "age": 30,
        "name": "Test User",
        "gender": "Non-binary",
        "job": "Tester",
        "greenlight_topics": ["Hiking", "Testing"],
        "redlight_topics": ["Bugs"]
    }
    response = client.post('/onboarding/onboarding', json=data)

    # --- Update Assertions ---
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}. Response: {response.get_data(as_text=True)}"
    json_data = response.get_json()
    assert json_data['user_id'] == test_user_id
    # Assert against the mocked return value for the profile string
    assert json_data["user_profile"] == expected_profile_str
    # Assert token is returned (assuming it should be)
    assert json_data['token'] == "test.jwt.token.more"

    # Check mocks were called
    mock_save_profile.assert_called_once() # Add checks for args if needed

    # --- Add check for format_user_profile call ---
    mock_format_profile.assert_called_once()
    # Check the object passed to format_user_profile
    format_call_args, _ = mock_format_profile.call_args
    assert isinstance(format_call_args[0], UserProfile)
    # Check attributes on the passed object
    assert format_call_args[0].user_id == test_user_id
    assert format_call_args[0].age == 30
    assert format_call_args[0].name == "Test User"
    assert format_call_args[0].gender == "Non-binary"
    assert format_call_args[0].job == "Tester"
    assert format_call_args[0].greenlights == ["Hiking", "Testing"]
    assert format_call_args[0].redlights == ["Bugs"]
    # Check default selected spurs were added correctly during object creation
    assert format_call_args[0].selected_spurs == list(app.config['SPUR_VARIANTS'])
    # Check other fields are None or default list
    assert format_call_args[0].pronouns is None
    assert format_call_args[0].personality_traits == []
    # --- End Add check ---


@patch('routes.onboarding.format_user_profile')
@patch('routes.onboarding.generate_user_id')
@patch('routes.onboarding.create_jwt')
@patch('routes.onboarding.save_user_profile')
# Add mock_format_profile to the function signature
def test_onboarding_success_with_selected_spurs(mock_save_profile, mock_create_jwt, mock_gen_id, mock_format_profile, client, app): # Added app fixture and mock_format_profile
    """Test successful onboarding specifying selected spurs."""
    test_user_id = "u:testuserid789"
    test_token = "test.jwt.token.spurs"
    mock_gen_id.return_value = test_user_id
    mock_create_jwt.return_value = test_token
    mock_save_profile.return_value = {"status": "user profile successfully saved"} # Mock success dict

    # Add mock return value for format_user_profile
    # The formatted string should reflect the *actual* selected spurs now if format_user_profile is correct
    expected_profile_str = (
        f"user_id: {test_user_id}\nAge: 22\nSelected Spurs: warm_spur, cool_spur" # Example format
    )
    mock_format_profile.return_value = expected_profile_str

    data = {
        "age": 22,
        "selected_spurs": ["warm_spur", "cool_spur"] # User selects only these
    }
    response = client.post('/onboarding/onboarding', json=data)

    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}. Response: {response.get_data(as_text=True)}"
    json_data = response.get_json()
    assert json_data['user_id'] == test_user_id
    assert json_data['token'] == test_token
    # Assert against the mocked formatted profile string
    assert json_data['user_profile'] == expected_profile_str


    # --- Update Mock Call Assertions ---
    mock_save_profile.assert_called_once()
    args, kwargs = mock_save_profile.call_args
    assert args[0] == test_user_id

    # Check the second argument IS a UserProfile object
    profile_arg = args[1]
    assert isinstance(profile_arg, UserProfile)

    # REMOVE the old assertion checking the string representation
    # assert "selected_spurs: ('main_spur', 'warm_spur', 'cool_spur', 'playful_spur')" in profile_arg # <-- REMOVE THIS

    # ADD assertion to check the actual attribute value
    assert profile_arg.selected_spurs == ["warm_spur", "cool_spur"]
    assert profile_arg.age == 22 # Check other attributes if needed
    assert profile_arg.user_id == test_user_id

    # Check format_user_profile mock call
    mock_format_profile.assert_called_once()
    format_call_args, _ = mock_format_profile.call_args
    assert isinstance(format_call_args[0], UserProfile)
    assert format_call_args[0].selected_spurs == ["warm_spur", "cool_spur"] # Verify correct object passed for formatting
    # --- End Update ---


def test_onboarding_fail_age_too_low(client):
    """Test onboarding failure when age is below 18."""
    data = {"age": 17}
    response = client.post('/onboarding/onboarding', json=data)
    # Based on the code, it returns 401 for age validation errors
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    assert "[routes.onboarding] - Error: Age must be an integer between 18 and 99" in json_data["error"] # Check for the error source indication

def test_onboarding_fail_age_invalid_type(client):
    """Test onboarding failure when age is not an integer."""
    data = {"age": "twenty"}
    response = client.post('/onboarding/onboarding', json=data)
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    assert "[routes.onboarding] - Error: Age must be an integer between 18 and 99" in json_data["error"]

def test_onboarding_fail_age_missing(client):
    """Test onboarding failure when age is missing."""
    data = {"name": "Test"} # Age is missing
    response = client.post('/onboarding/onboarding', json=data)
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    assert "Missing age in request data" in json_data["error"]


@patch('routes.onboarding.format_user_profile')
@patch('routes.onboarding.save_user_profile')
@patch('routes.onboarding.create_jwt')
@patch('routes.onboarding.generate_user_id') # Mock the function that fails
def test_onboarding_fail_generate_id_exception(mock_gen_id, mock_create_jwt, mock_save_profile, mock_format_profile, client, app):
    """Test onboarding failure if generate_user_id raises an exception."""
    mock_gen_id.side_effect = Exception("ID Generation Error") # Simulate failure

    data = {"age": 25}
    response = client.post('/onboarding/onboarding', json=data)

    assert response.status_code == 500
    json_data = response.get_json()
    assert "error" in json_data
    assert "[routes.onboarding] - Error: ID Generation Error" in json_data["error"]
    # Ensure downstream mocks were NOT called
    mock_create_jwt.assert_not_called()
    mock_save_profile.assert_not_called()
    mock_format_profile.assert_not_called()

@patch('routes.onboarding.format_user_profile')
@patch('routes.onboarding.save_user_profile')
@patch('routes.onboarding.create_jwt') # Mock the function that fails
@patch('routes.onboarding.generate_user_id')
def test_onboarding_fail_create_jwt_exception(mock_gen_id, mock_create_jwt, mock_save_profile, mock_format_profile, client, app):
    """Test onboarding failure if create_jwt raises an exception."""
    test_user_id = "u:testuserid123"
    mock_gen_id.return_value = test_user_id
    mock_create_jwt.side_effect = Exception("JWT Creation Error") # Simulate failure

    data = {"age": 25}
    response = client.post('/onboarding/onboarding', json=data)

    assert response.status_code == 500
    json_data = response.get_json()
    assert "error" in json_data
    assert "[routes.onboarding] - Error: JWT Creation Error" in json_data["error"]
    # Ensure downstream mocks were NOT called
    mock_save_profile.assert_not_called()
    mock_format_profile.assert_not_called()

@patch('routes.onboarding.format_user_profile')
@patch('routes.onboarding.save_user_profile') # Mock the function that fails
@patch('routes.onboarding.create_jwt')
@patch('routes.onboarding.generate_user_id')
def test_onboarding_fail_save_profile_error_dict(mock_gen_id, mock_create_jwt, mock_save_profile, mock_format_profile, client, app):
    """Test onboarding failure if save_user_profile returns an error dictionary."""
    test_user_id = "u:testuserid123"
    test_token = "test.jwt.token"
    mock_gen_id.return_value = test_user_id
    mock_create_jwt.return_value = test_token
    # Simulate save_user_profile returning an error dictionary
    mock_save_profile.return_value = {"error": "Database connection failed", "status_code": 503}

    data = {"age": 25}
    response = client.post('/onboarding/onboarding', json=data)

    # The route specifically catches this and returns the error + status code
    assert response.status_code == 503
    json_data = response.get_json()
    assert "error" in json_data
    assert "Profile save failed: Database connection failed" in json_data["error"]
    # Ensure format_user_profile was NOT called after save failed
    mock_format_profile.assert_not_called()

@patch('routes.onboarding.format_user_profile') # Mock the function that fails
@patch('routes.onboarding.save_user_profile')
@patch('routes.onboarding.create_jwt')
@patch('routes.onboarding.generate_user_id')
def test_onboarding_fail_format_profile_exception(mock_gen_id, mock_create_jwt, mock_save_profile, mock_format_profile, client, app):
    """Test onboarding handles failure during profile formatting."""
    test_user_id = "u:testuserid123"
    test_token = "test.jwt.token"
    mock_gen_id.return_value = test_user_id
    mock_create_jwt.return_value = test_token
    mock_save_profile.return_value = {"status": "user profile successfully saved"} # Save succeeds
    # Simulate failure in format_user_profile
    mock_format_profile.side_effect = Exception("Formatting blew up")

    data = {"age": 25}
    response = client.post('/onboarding/onboarding', json=data)

    # The route catches this specific exception and returns 200, but with a modified profile string
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['user_id'] == test_user_id
    assert json_data['token'] == test_token
    # Check for the specific error message embedded in the profile string
    assert "(Profile formatting error)" in json_data['user_profile']
    assert f"user_id: {test_user_id}" in json_data['user_profile'] # Check user_id is still there
    assert f"Age: 25" in json_data['user_profile'] # Check age is still there

    # Ensure mocks were called up to the point of failure
    mock_gen_id.assert_called_once()
    mock_create_jwt.assert_called_once()
    mock_save_profile.assert_called_once()
    mock_format_profile.assert_called_once() # It was called, but raised exception

@patch('routes.onboarding.format_user_profile')
@patch('routes.onboarding.save_user_profile')
@patch('routes.onboarding.create_jwt')
@patch('routes.onboarding.generate_user_id')
def test_onboarding_success_invalid_spurs_type(mock_gen_id, mock_create_jwt, mock_save_profile, mock_format_profile, client, app):
    """Test onboarding uses default spurs if 'selected_spurs' has invalid type."""
    test_user_id = "u:testuserid_invalidspurs"
    test_token = "test.jwt.token.invalidspurs"
    mock_gen_id.return_value = test_user_id
    mock_create_jwt.return_value = test_token
    mock_save_profile.return_value = {"status": "user profile successfully saved"}
    # Mock format_user_profile - it should receive the default spurs
    expected_profile_string = f"user_id: {test_user_id}\nAge: 26\nSelected Spurs: main_spur, warm_spur, cool_spur, playful_spur"
    mock_format_profile.return_value = expected_profile_string

    data = {"age": 26, "selected_spurs": "this-is-not-a-list"} # Invalid type for spurs
    response = client.post('/onboarding/onboarding', json=data)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['user_id'] == test_user_id
    assert json_data['token'] == test_token
    assert json_data['user_profile'] == expected_profile_string

    # Crucially, check that save_user_profile was called with the DEFAULT spurs
    mock_save_profile.assert_called_once()
    call_args, _ = mock_save_profile.call_args
    saved_profile_obj = call_args[1]
    assert isinstance(saved_profile_obj, UserProfile)
    assert saved_profile_obj.selected_spurs == list(app.config['SPUR_VARIANTS']) # Check default was used

    # Check that format_user_profile was also called with the default spurs
    mock_format_profile.assert_called_once()
    format_call_args, _ = mock_format_profile.call_args
    assert isinstance(format_call_args[0], UserProfile)
    assert format_call_args[0].selected_spurs == list(app.config['SPUR_VARIANTS'])

def test_onboarding_fail_empty_json(client):
    """Test onboarding failure when empty JSON data is sent."""
    response = client.post('/onboarding/onboarding', json={})
    # request.get_json() returns {}, which fails 'age' not in data check

    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    assert "Missing age in request data" in json_data["error"]

@patch('routes.onboarding.format_user_profile')
@patch('routes.onboarding.save_user_profile')
@patch('routes.onboarding.create_jwt')
@patch('routes.onboarding.generate_user_id')
def test_onboarding_success_all_optional_fields(mock_gen_id, mock_create_jwt, mock_save_profile, mock_format_profile, client, app):
    """Test successful onboarding with all optional profile details provided."""
    test_user_id = "u:testuserid_allfields"
    test_token = "test.jwt.token.allfields"
    mock_gen_id.return_value = test_user_id
    mock_create_jwt.return_value = test_token
    mock_save_profile.return_value = {"status": "user profile successfully saved"}

    # Prepare data with all optional fields from BaseProfile and relevant UserProfile fields
    # Note: user_id and selected_spurs are handled separately by the route
    all_optional_data = {
        "age": 42, # Required
        "name": "Max Fields",
        "gender": "Male",
        "pronouns": "he/him",
        "school": "Test University",
        "job": "Coverage Analyst",
        "drinking": "Socially",
        "ethnicity": "Testican",
        "hometown": "Fieldsville",
        "greenlight_topics": ["testing", "coverage"], # Request key
        "redlight_topics": ["bugs", "flakiness"],     # Request key
        "personality_traits": ["thorough", "persistent"]
    }

    # Mock format_user_profile - create expected string based on input data
    # (This formatting depends heavily on your format_user_profile implementation)
    expected_profile_str = (
        f"user_id: {test_user_id}\nAge: 42\nName: Max Fields\nGender: Male\nPronouns: he/him\n"
        f"School: Test University\nJob: Coverage Analyst\nDrinking: Socially\nEthnicity: Testican\n"
        f"Hometown: Fieldsville\nGreenlight Topics: testing, coverage\nRedlight Topics: bugs, flakiness\n"
        f"Personality_traits: thorough, persistent\n" # Note: key might not be capitalized by default formatter
        f"Selected Spurs: main_spur, warm_spur, cool_spur, playful_spur" # Default spurs
    )
    mock_format_profile.return_value = expected_profile_str


    response = client.post('/onboarding/onboarding', json=all_optional_data)

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['user_id'] == test_user_id
    assert json_data['token'] == test_token
    assert json_data['user_profile'] == expected_profile_str # Check against mocked format

    # Check save_user_profile call - verify all fields were correctly placed in the UserProfile object
    mock_save_profile.assert_called_once()
    call_args, _ = mock_save_profile.call_args
    assert call_args[0] == test_user_id
    saved_profile: UserProfile = call_args[1]
    assert isinstance(saved_profile, UserProfile)
    assert saved_profile.user_id == test_user_id
    assert saved_profile.age == 42
    assert saved_profile.name == "Max Fields"
    assert saved_profile.gender == "Male"
    assert saved_profile.pronouns == "he/him"
    assert saved_profile.school == "Test University"
    assert saved_profile.job == "Coverage Analyst"
    assert saved_profile.drinking == "Socially"
    assert saved_profile.ethnicity == "Testican"
    assert saved_profile.hometown == "Fieldsville"
    assert saved_profile.greenlights == ["testing", "coverage"] # Profile key
    assert saved_profile.redlights == ["bugs", "flakiness"]     # Profile key
    assert saved_profile.personality_traits == ["thorough", "persistent"]
    assert saved_profile.selected_spurs == list(app.config['SPUR_VARIANTS']) # Default

    # Check format_user_profile call
    mock_format_profile.assert_called_once()
    format_call_args, _ = mock_format_profile.call_args
    # Verify the object passed to formatter matches the one saved
    assert format_call_args[0] == saved_profile


@patch('routes.onboarding.format_user_profile')
@patch('routes.onboarding.save_user_profile') # Mock the function that fails
@patch('routes.onboarding.create_jwt')
@patch('routes.onboarding.generate_user_id')
def test_onboarding_fail_save_profile_error_tuple(mock_gen_id, mock_create_jwt, mock_save_profile, mock_format_profile, client, app):
    """Test onboarding failure if save_user_profile returns an error tuple."""
    test_user_id = "u:testuserid_tuplefail"
    test_token = "test.jwt.token.tuplefail"
    mock_gen_id.return_value = test_user_id
    mock_create_jwt.return_value = test_token
    # Simulate save_user_profile returning an error tuple
    mock_save_profile.return_value = ({"error": "DB tuple fail"}, 500)

    data = {"age": 25}
    response = client.post('/onboarding/onboarding', json=data)

    # The route specifically catches this tuple return and uses its contents
    assert response.status_code == 500
    json_data = response.get_json()
    assert "error" in json_data
    assert "Profile save failed: DB tuple fail" in json_data["error"]
    # Ensure format_user_profile was NOT called after save failed
    mock_format_profile.assert_not_called()

@patch('routes.onboarding.format_user_profile')
@patch('routes.onboarding.save_user_profile') # Mock the function that fails
@patch('routes.onboarding.create_jwt')
@patch('routes.onboarding.generate_user_id')
def test_onboarding_fail_save_profile_error_dict_no_status(mock_gen_id, mock_create_jwt, mock_save_profile, mock_format_profile, client, app):
    """Test save failure handling when error dict is missing status_code."""
    test_user_id = "u:testuserid_nostatus"
    test_token = "test.jwt.token.nostatus"
    mock_gen_id.return_value = test_user_id
    mock_create_jwt.return_value = test_token
    # Simulate save_user_profile returning an error dictionary WITHOUT status_code
    mock_save_profile.return_value = {"error": "DB error no status"}

    data = {"age": 25}
    response = client.post('/onboarding/onboarding', json=data)

    # The route should default to 500 status code in this case
    assert response.status_code == 500
    json_data = response.get_json()
    assert "error" in json_data
    assert "Profile save failed: DB error no status" in json_data["error"]
    # Ensure format_user_profile was NOT called after save failed
    mock_format_profile.assert_not_called()