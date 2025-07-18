from dataclasses import fields
from datetime import datetime, timezone
from class_defs.spur_def import Spur
from class_defs.profile_def import ConnectionProfile
from infrastructure.clients import get_firestore_db
from infrastructure.id_generator import extract_user_id_from_other_id
from infrastructure.logger import get_logger
from infrastructure.id_generator import generate_spur_id, get_null_connection_id
from services.connection_service import get_connection_profile

logger = get_logger(__name__)

def save_spur(user_id, spur: dict) -> dict:
    """
    Save a spur to Firestore.
    
    Args:
        user_id (str): The ID of the user saving the spur.
        spur (dict): A dictionary containing spur details.
    Returns:
        dict: A dictionary indicating success or failure.
        
    """
    try:
        if not user_id:
            err_point = __package__ or __name__
            logger.error("Error in [%s]: Missing user ID in save_spur", err_point)
            raise ValueError("Error: Missing user ID in save_spur")

        if not spur or not isinstance(spur, dict):
            err_point = __package__ or __name__
            logger.error("Error in [%s]: Missing user ID in save_spur", err_point)
            raise ValueError("Error: Missing user ID in save_spur")

        user_id = user_id
        if not user_id:
            err_point = __package__ or __name__
            logger.error("Error in [%s]: No user_id found in flask context", err_point)
            raise ValueError("Error: No user_id found in flask context")
        
        spur_dict = spur
        if 'user_id' not in spur_dict:
            spur_dict['user_id'] = user_id
        if 'spur_id' not in spur_dict:
            spur_id = generate_spur_id(user_id)
            spur_dict['spur_id'] = spur_id
        else:
            spur_id = spur_dict['spur_id']
            
        if 'connection_id' not in spur_dict:
            spur_dict['connection_id'] = get_null_connection_id(user_id)
        elif spur_dict.get('connection_id'):
            connection_id = spur_dict['connection_id']
            connection = get_connection_profile(user_id, connection_id)
            if connection: 
                spur_dict['connection_name'] = ConnectionProfile.get_attr_as_str(connection, "connection_name")
                
        if 'created_at' not in spur_dict:
            spur_dict['created_at'] = datetime.now(timezone.utc)

        if 'text' not in spur_dict or not spur_dict['text']:
            logger.error("Error: Spur text is required")
            raise ValueError("Error: Spur text is required")
        
        
        
        db = get_firestore_db()
        doc_ref = db.collection("users").document(user_id).collection("spurs").document(spur_id)
        doc_data = {
            "user_id": user_id,
            "spur_id": spur_id,
            "conversation_id": spur_dict.get("conversation_id", ""),
            "connection_id": spur_dict.get("connection_id", ""),
            "connection_name": spur_dict.get("connection_name", ""),
            "situation": spur_dict.get("situation", ""),
            "topic": spur_dict.get("topic", ""),
            "variant": spur_dict.get("variant", ""),
            "tone": spur_dict.get("tone", ""),
            "text": spur_dict.get("text", ""),
            "created_at": spur_dict.get("created_at", datetime.now(timezone.utc))
        }

        doc_ref.set(doc_data)
        
        return {"success": "spur saved", "spur_id": doc_ref.id}
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        return {"error": f"{err_point} - Error: {str(e)}", "status_code": 500}


def get_saved_spurs(user_id: str) -> list[Spur]:
    if not user_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return []
    try:
        db = get_firestore_db()
        ref = db.collection("users").document(user_id).collection("spurs")
        spurs_stream = ref.stream()
        spurs_list = []
        for spur_doc in spurs_stream:
            if spur_doc.exists:
                spurs_data = spur_doc.to_dict()
                complete_data = {}
                for f_info in fields(Spur):
                    if f_info.name in spurs_data:
                        complete_data[f_info.name] = spurs_data[f_info.name]
                    elif callable(f_info.default_factory):
                        complete_data[f_info.name] = f_info.default_factory()
                    else:
                        complete_data[f_info.name] = None
                        
                spur = Spur.from_dict(complete_data)
                spurs_list.append(spur)
        return spurs_list
    except Exception as e:
        err_point = __package__ or "spur_service"
        logger.error("[%s] Error getting spurs for user %s: %s", err_point, user_id, e, exc_info=True)
        return []         
        
        # query = ref        

        # if filters:
        #     if "variant" in filters:
        #         query = query.where("variant", "==", filters["variant"])
        #     if "situation" in filters:
        #         query = query.where("situation", "==", filters["situation"])
        #     if "date_from" in filters:
        #         query = query.where("date_saved", ">=", filters["date_from"])
        #     if "date_to" in filters:
        #         query = query.where("date_saved", "<=", filters["date_to"])
        #     sort_order = filters.get("sort", "desc")
        #     direct = firestore.Query.ASCENDING if sort_order == "asc" else firestore.Query.DESCENDING
        #     query = query.order_by("date_saved", direction=direct)

        # keyword = filters.get("keyword", "").lower() if filters else ""

        # docs = query.stream()
        # result = []
        # for doc in docs:
        #     data = doc.to_dict()
        #     if keyword and keyword not in data.get("text", "").lower():
        #         continue  # Skip if keyword not in text

    #         result.append({
    #             "spur_id": doc.id,
    #             "variant": data.get("variant"),
    #             "text": data.get("text"),
    #             "situation": data.get("situation"),
    #             "date_saved": data.get("date_saved")
    #         })

    #     return result
    # except Exception as e:
    #     err_point = __package__ or __name__
    #     logger.error("[%s] Error: %s", err_point, e)
    #     return f"error - {err_point} - Error: {str(e)}", 500


def delete_saved_spur(user_id, spur_id):
    if not user_id or not spur_id:
        err_point = __package__ or __name__
        logger.error(f"Error: {err_point}")
        return f"error - {err_point} - Error:", 400

    try:
        db = get_firestore_db()
        doc_ref = db.collection("users").document(user_id).collection("spurs").document(spur_id)
        doc_ref.delete()
        return {"success": "spur deleted"}
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
    try:
        db = get_firestore_db()
        doc_ref = db.collection("users").document(user_id).collection("spurs").document(spur_id)
        doc = doc_ref.get()
        if doc.exists:
            spur = Spur.from_dict(doc)
            return spur
        else:
            err_point = __package__ or __name__
            logger.error(f"Error: {err_point}")
            raise Exception(f"error - {err_point} - Error:")
    except Exception as e:
        err_point = __package__ or __name__
        logger.error("[%s] Error: %s", err_point, e)
        raise ValueError(f"error - {err_point} - Error: {str(e)}")

