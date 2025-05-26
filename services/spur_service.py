import firebase_admin
from class_defs.spur_def import Spur
from flask import g
from google.cloud import firestore
from infrastructure.clients import db
from infrastructure.id_generator import extract_user_id_from_other_id
from infrastructure.logger import get_logger

logger = get_logger(__name__)

def save_spur(user_id, spur):
    try:
        if not user_id:
            logger.error("Error: Missing user ID in save_spur")
            raise ValueError("Error: Missing user ID in save_spur")

        if not spur or not isinstance(spur, Spur):
            logger.error("Error: Missing user ID in save_spur")
            raise ValueError("Error: Missing user ID in save_spur")

        user_id = g.user['user_id']
        spur_dict = Spur.to_dict(spur)
        spur_id = spur_dict.get("spur_id", "")
        conversation_id = spur_dict.get("conversation_id", "")
        connection_id = spur_dict.get("connection_id", "")
        situation = spur_dict.get("situation", "")
        topic = spur_dict.get("topic","")
        variant = spur_dict.get("varint", "")
        tone = spur_dict.get("tone", "")
        text = spur_dict.get("text", "")
        created_at = spur_dict.get("created_at", None)
        
        
        

        doc_ref = db.collection("users").document(user_id).collection("spurs").document(spur_id)
        doc_data = {
            "user_id": user_id,
            "spur_id": spur,
            "conversation_id": conversation_id,
            "connection_id": connection_id,
            "situation": situation,
            "topic": topic,
            "variant": variant,
            "tone": tone,
            "text": text,
            "created_at": created_at
            }

        doc_ref.set(doc_data)
        
        return {"status": "spur saved", "spur_id": doc_ref.id}
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return f"error: {err_point} - Error: {str(e)}", 500

def get_saved_spurs(user_id, filters=None):
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return f"error - {err_point} - Error:", 400
    try:
        ref = db.collection("users").document(user_id).collection("spurs")
        query = ref

        if filters:
            if "variant" in filters:
                query = query.where("variant", "==", filters["variant"])
            if "situation" in filters:
                query = query.where("situation", "==", filters["situation"])
            if "date_from" in filters:
                query = query.where("date_saved", ">=", filters["date_from"])
            if "date_to" in filters:
                query = query.where("date_saved", "<=", filters["date_to"])
            sort_order = filters.get("sort", "desc")
            direct = firestore.Query.ASCENDING if sort_order == "asc" else firestore.Query.DESCENDING
            query = query.order_by("date_saved", direction=direct)

        keyword = filters.get("keyword", "").lower() if filters else ""

        docs = query.stream()
        result = []
        for doc in docs:
            data = doc.to_dict()
            if keyword and keyword not in data.get("text", "").lower():
                continue  # Skip if keyword not in text

            result.append({
                "spur_id": doc.id,
                "variant": data.get("variant"),
                "text": data.get("text"),
                "situation": data.get("situation"),
                "date_saved": data.get("date_saved")
            })

        return result
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return f"error - {err_point} - Error: {str(e)}", 500


def delete_saved_spur(user_id, spur_id):
    if not user_id or not spur_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return f"error - {err_point} - Error:", 400

    try:
        doc_ref = db.collection("users").document(user_id).collection("spurs").document(spur_id)
        doc_ref.delete()
        return {"status": "spur deleted"}
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return f"error - {err_point} - Error: {str(e)}", 500

def get_spur(spur_id: str) -> Spur:
    
    user_id = extract_user_id_from_other_id(spur_id)
    if not user_id or not spur_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point} - Missing user_id or spur_id")
        raise ValueError("Error: Missing user_id or spur_id")

    doc_ref = db.collection("users").document(user_id).collection("spurs").document(spur_id)
    doc = doc_ref.get()
    if doc.exists:
        spur = Spur.from_dict(doc)
        return spur
    else:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        raise Exception(f"error - {err_point} - Error:")

