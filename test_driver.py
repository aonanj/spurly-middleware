import json
import requests

# Set your Flask server URL here
BASE_URL = "http://127.0.0.1:5000/"

payload = {
    "conversation": [
        {"speaker": "user", "text": "Hey, how was your weekend?"},
        {"speaker": "connection", "text": "Pretty good—mostly relaxed and caught up on sleep."},
        {"speaker": "user", "text": "Nice. Any good shows or books?"}
    ],
    "user_profile": {
        "Tone": "warm",
        "Humor Style": "sarcastic",
        "Flirt Level": "medium",
        "Openness": "low",
        "Banter Tolerance": "high",
        "Emoji Use": "occasionally"
    },
    "connection_profile": {
        "Tone Baseline": "cool",
        "Flirt Level": "low",
        "Openness": "high",
        "Drinking": "never",
        "Greenlight Topics": ["dogs", "hiking"],
        "Redlight Topics": ["politics"]
    },
    "situation": "re_engagement",
    "topic": "books"
}

response = requests.post(BASE_URL, json=payload)

if response.ok:
    print(json.dumps(response.json(), indent=2))
else:
    print("Error:", response.status_code, response.text)
