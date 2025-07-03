# infrastructure/tasks.py
from celery import Celery
from infrastructure.email_service import email_service
from infrastructure.logger import get_logger

logger = get_logger(__name__)

# Initialize Celery
celery_app = Celery('spurly', broker='redis://localhost:6379/0')

@celery_app.task(bind=True, max_retries=3)
def send_support_emails_task(self, support_request_dict):
    """
    Asynchronously send support request emails.
    """
    try:
        # Send to support team
        support_sent = email_service.send_support_request_to_team(support_request_dict)
        
        # Send confirmation to user
        confirmation_sent = email_service.send_support_request_confirmation(support_request_dict)
        
        # Update Firestore with email status
        from infrastructure.clients import get_firestore_db
        db = get_firestore_db()
        support_ref = db.collection("support_requests").document(support_request_dict['request_id'])
        support_ref.update({
            "email_sent_to_support": support_sent,
            "confirmation_email_sent": confirmation_sent
        })
        
        return {
            "support_email_sent": support_sent,
            "confirmation_email_sent": confirmation_sent
        }
        
    except Exception as e:
        logger.error(f"Error in email task for request {support_request_dict.get('request_id')}: {str(e)}")
        # Retry the task
        raise self.retry(exc=e, countdown=60)  # Retry after 1 minute