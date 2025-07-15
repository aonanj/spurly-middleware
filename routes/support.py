from flask import Blueprint, request, jsonify, g
from datetime import datetime, timezone
from infrastructure.token_validator import verify_token, handle_all_errors, verify_app_check_token
from infrastructure.logger import get_logger
from infrastructure.clients import get_firestore_db
from infrastructure.email_service import email_service  
import uuid

logger = get_logger(__name__)

support_bp = Blueprint("support", __name__)

@support_bp.route("/user-support", methods=["POST"])
@handle_all_errors
@verify_token
@verify_app_check_token
def submit_support_request():
    """
    Submit a support request from a user.
    
    Expected JSON payload:
    {
        "email": "user@example.com",
        "name": "User Name",
        "subject": "Subject of support request",
        "user_id": "user_id_string",
        "message": "Support request message"
    }
    
    Returns:
        JSON response with success status and request ID
    """
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400
        
        # Extract user_id from token
        token_user_id = getattr(g, "user_id", None)
        if not token_user_id:
            return jsonify({"error": "Invalid authentication state"}), 401
        
        # Validate required fields
        required_fields = ["email", "name", "subject", "message"]
        missing_fields = []
        
        for field in required_fields:
            if not data.get(field, "").strip():
                missing_fields.append(field)
        
        if missing_fields:
            return jsonify({
                "error": "Missing required fields",
                "missing_fields": missing_fields
            }), 400
        
        # Verify user_id matches if provided
        if data.get("user_id") and data["user_id"] != token_user_id:
            logger.warning(f"User ID mismatch in support request. Token: {token_user_id}, Request: {data.get('user_id')}")
            # Use the authenticated user_id from token
            data["user_id"] = token_user_id
        else:
            data["user_id"] = token_user_id
        
        # Validate email format
        email = data.get("email", "").strip().lower()
        if not email or "@" not in email:
            return jsonify({"error": "Invalid email format"}), 400
        
        # Create support request document
        support_request_id = f"sr_{uuid.uuid4().hex[:12]}"
        
        support_request = {
            "request_id": support_request_id,
            "user_id": data["user_id"],
            "email": email,
            "name": data.get("name", "").strip(),
            "subject": data.get("subject", "").strip()[:200],  # Limit subject length
            "message": data.get("message", "").strip()[:5000],  # Limit message length
            "status": "pending",  # pending, in_progress, resolved, closed
            "priority": "normal",  # low, normal, high, urgent
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "assigned_to": None,
            "resolution": None,
            "notes": [],
            "email_sent_to_support": False,  # Track email status
            "confirmation_email_sent": False  # Track confirmation status
        }
        
        # Save to Firestore
        db = get_firestore_db()
        
        # Store in a global support_requests collection for easy admin access
        support_ref = db.collection("support_requests").document(support_request_id)
        support_ref.set(support_request)
        
        # Also store a reference in the user's document for user history
        user_support_ref = db.collection("users").document(data["user_id"]).collection("support_requests").document(support_request_id)
        user_support_ref.set({
            "request_id": support_request_id,
            "subject": support_request["subject"],
            "status": support_request["status"],
            "created_at": support_request["created_at"]
        })
        
        logger.info(f"Support request {support_request_id} created for user {data['user_id']}")
        
        # Send emails asynchronously to not block the response
        # Option 1: Send synchronously (simpler but slower)
        email_to_support_sent = False
        confirmation_email_sent = False
        
        try:
            # Send email to support team
            email_to_support_sent = email_service.send_support_request_to_team(support_request)
            if email_to_support_sent:
                support_ref.update({"email_sent_to_support": True})
                logger.info(f"Support email sent for request {support_request_id}")
            else:
                logger.error(f"Failed to send support email for request {support_request_id}")
        except Exception as e:
            logger.error(f"Error sending support email for request {support_request_id}: {str(e)}")
        
        try:
            # Send confirmation email to user
            confirmation_email_sent = email_service.send_support_request_confirmation(support_request)
            if confirmation_email_sent:
                support_ref.update({"confirmation_email_sent": True})
                logger.info(f"Confirmation email sent for request {support_request_id}")
            else:
                logger.error(f"Failed to send confirmation email for request {support_request_id}")
        except Exception as e:
            logger.error(f"Error sending confirmation email for request {support_request_id}: {str(e)}")
        
        # Return success even if emails fail - the support request is still saved
        response_message = "Support request submitted successfully"
        if not email_to_support_sent:
            response_message += ". Note: There was an issue sending the notification email, but your request has been saved."
        
        return jsonify({
            "success": True,
            "message": response_message,
            "request_id": support_request_id,
            "status": "pending",
            "email_sent": email_to_support_sent,
            "confirmation_sent": confirmation_email_sent
        }), 201
        
    except Exception as e:
        logger.error(f"Error submitting support request: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to submit support request"}), 500


@support_bp.route("/api/user-support/<request_id>", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def get_support_request(request_id: str):
    """
    Get a specific support request by ID.
    Users can only access their own support requests.
    
    Args:
        request_id: The support request ID
        
    Returns:
        JSON response with support request details
    """
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            return jsonify({"error": "Invalid authentication state"}), 401
        
        if not request_id:
            return jsonify({"error": "Request ID is required"}), 400
        
        # Get the support request
        db = get_firestore_db()
        doc_ref = db.collection("support_requests").document(request_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return jsonify({"error": "Support request not found"}), 404
        
        support_data = doc.to_dict()
        
        # Verify the user owns this support request
        if support_data.get("user_id") != user_id:
            return jsonify({"error": "Unauthorized access to support request"}), 403
        
        # Convert datetime objects to ISO format
        if isinstance(support_data.get("created_at"), datetime):
            support_data["created_at"] = support_data["created_at"].isoformat()
        if isinstance(support_data.get("updated_at"), datetime):
            support_data["updated_at"] = support_data["updated_at"].isoformat()
        
        return jsonify(support_data), 200
        
    except Exception as e:
        logger.error(f"Error getting support request {request_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to retrieve support request"}), 500


@support_bp.route("/api/user-support/list", methods=["GET"])
@handle_all_errors
@verify_token
@verify_app_check_token
def list_user_support_requests():
    """
    List all support requests for the authenticated user.
    
    Query parameters:
        status (optional): Filter by status (pending, in_progress, resolved, closed)
        limit (optional): Maximum number of requests to return (default: 20, max: 100)
        
    Returns:
        JSON response with list of support requests
    """
    try:
        user_id = getattr(g, "user_id", None)
        if not user_id:
            user_id = request.args.get("user_id")
            if not user_id:
                return jsonify({"error": "Invalid authentication state"}), 401
        
        # Get query parameters
        status_filter = request.args.get("status")
        limit = request.args.get("limit", 20, type=int)
        
        if limit <= 0 or limit > 100:
            limit = 20
        
        # Query user's support requests
        db = get_firestore_db()
        query = db.collection("users").document(user_id).collection("support_requests")
        
        # Apply status filter if provided
        if status_filter and status_filter in ["pending", "in_progress", "resolved", "closed"]:
            query = query.where("status", "==", status_filter)
        
        # Order by creation date (newest first) and limit
        query = query.order_by("created_at", direction="DESCENDING").limit(limit)
        
        # Execute query
        docs = query.stream()
        
        support_requests = []
        for doc in docs:
            data = doc.to_dict()
            # Convert datetime to ISO format
            if isinstance(data.get("created_at"), datetime):
                data["created_at"] = data["created_at"].isoformat()
            support_requests.append(data)
        
        return jsonify({
            "success": True,
            "count": len(support_requests),
            "support_requests": support_requests
        }), 200
        
    except Exception as e:
        user_id = getattr(g, "user_id", None)
        logger.error(f"Error listing support requests for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to list support requests"}), 500
    
@support_bp.route("/apple-subscription-notification", methods=["POST"])
@handle_all_errors
def receive_subscription_notification():
    """
    Endpoint to receive App Store Server notifications regarding subscription events.

    Expected payload (example structure from Apple):
    {
        "notification_type": "DID_RENEW",
        "subtype": "INITIAL_BUY",
        "data": {...}
    }

    Sends an email containing the notification type and full payload.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid or missing JSON payload"}), 400

        notification_type = data.get("notification_type", "UNKNOWN")
        subtype = data.get("subtype", "N/A")

        subject = f"Apple Subscription Notification: {notification_type} ({subtype})"
        message = f"Received Apple subscription notification:\n\n{data}"

        email_service.send_email(
            to_email="admin@spurly.io",
            subject=subject,
            html_content=message
        )
        
        ## TODO: data["user_id"] doesn't exist, this needs to be updated to map transaction ID to user ID
        # db = get_firestore_db()
        # doc_ref = db.collection("users").document(data["user_id"]).collection("apple_subscription_notifications").document()
        # doc_ref.set({
        #     "timestamp": datetime.now(timezone.utc).isoformat(),
        #     "notification_type": notification_type,
        #     "subtype": subtype,
        #     "raw_payload": data
        # })

        return jsonify({"status": "notification received"}), 200

    except Exception as e:
        logger.error(f"Error processing subscription notification: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500