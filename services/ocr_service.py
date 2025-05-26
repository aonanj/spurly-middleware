from flask import jsonify
from google.cloud import vision_v1
from google.cloud.vision_v1 import ImageAnnotatorClient, Image, types
from infrastructure.clients import vision_client
from infrastructure.logger import get_logger
from utils.ocr_utils import extract_conversation, crop_top_bottom_cv
import cv2
import numpy as np


logger = get_logger(__name__)


def process_image(user_id, image_file) -> list[dict]:
	"""""
		Accepts a user_id and file_name as arg, file should be a screen shot of a messaging conversation. 
		file should be in request.files. Perform error check before calling ocr(...) -->
				
				if 'file' not in request.files:
					return jsonify({"error": "No file part"})
					
				file = request.files['file']
				
				if file.filename == '':
					return jsonify({"error": "No selected file"})
		
		Will need to import Flask and request to use this error check. 
	"""""
	client = vision_client
	try:
		# Save the file temporarily to process it
		image_byte = image_file.read()

		np_arr = np.frombuffer(image_byte, np.uint8)
		image_array = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

		if image_array is None:
			err_point = __package__ or __name__
			logger.error(f"Error: {err_point}")
			raise RuntimeError (f"[{err_point}] - Error:")

		cropped_img = crop_top_bottom_cv(image_array)

		if cropped_img is None:
			err_point = __package__ or __name__
			logger.error(f"Error: {err_point} - Cropped image is None")
			raise RuntimeError(f"[{err_point}] - Error: Cropped image is None")
		
		success, encoded_image = cv2.imencode('.png', cropped_img)
		if not success:
			err_point = __package__ or __name__
			logger.error(f"Error: {err_point}")
			raise RuntimeError(f"[{err_point}] - Error:")
		
		content = encoded_image.tobytes()
		image = Image(content=content)


		response = client.annotate_image({'image': image})
		## OR
		## response = client.batch_document_text_detection(requests=[{"image": image}])
		## OR (original)
		## response = client.document_text_detection(image=image)

		if response.error.message:
			err_point = __package__ or __name__
			logger.error(f"Error: {err_point}: {response.error.message}")
			raise RuntimeError (f"[{err_point}] - Error - {response.error.messasge}")
		
		conversation_msgs = extract_conversation(user_id, response.full_text_annotation.pages[0])

		if conversation_msgs:
			return conversation_msgs
		else:
			err_point = __package__ or __name__
			logger.error(f"Error: {err_point}")
			raise RuntimeError(f"error: {err_point} - Error")
	except Exception as e:
				err_point = __package__ or __name__
				logger.error("[%s] Error: %s", err_point, e)
				raise Exception (f"error: [{err_point}] - Error: {str(e)}")
