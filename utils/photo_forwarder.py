import base64
import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MODEL_AI_ENDPOINT_URL = 'https://your-model-endpoint'

def forward_full_image_to_model(image_bytes: bytes) -> dict:
	payload = {'image_base64': base64.b64encode(image_bytes).decode('utf-8')}
	try:
		session = requests.Session()
		retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
		adapter = HTTPAdapter(max_retries=retry)
		session.mount('http://', adapter)
		session.mount('https://', adapter)
		resp = session.post(MODEL_AI_ENDPOINT_URL, json=payload)
		resp.raise_for_status()
		return resp.json()
	except requests.exceptions.RequestException as e:
		logging.getLogger(__name__).error("Error forwarding image to model: %s", e)
		raise