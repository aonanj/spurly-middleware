# infrastructure/email_service.py
import os
import requests
from typing import Optional, Dict, Any
from infrastructure.logger import get_logger

logger = get_logger(__name__)

class EmailService:
    def __init__(self):
        # Mailgun configuration
        self.mailgun_api_key = os.environ.get('MAILGUN_API_KEY')
        self.mailgun_domain = os.environ.get('MAILGUN_DOMAIN', 'mg.spurly.io')  
        self.mailgun_api_base = os.environ.get('MAILGUN_API_BASE', 'https://api.mailgun.net/v3')
        self.from_email = os.environ.get('SUPPORT_FROM_EMAIL', f'noreply@{self.mailgun_domain}')
        self.support_email = os.environ.get('SUPPORT_TO_EMAIL', 'support@spurly.io')
        
        # Log configuration (without exposing sensitive data)
        logger.error(f"Email Service initialized with Mailgun")
        logger.error(f"Mailgun domain: {self.mailgun_domain}")
        logger.error(f"From email: {self.from_email}")
        logger.error(f"API key configured: {bool(self.mailgun_api_key)}")

        if not self.mailgun_api_key:
            logger.warning("Mailgun API key not configured. Emails will not be sent.")
    
    def send_email(
        self, 
        to_email: str, 
        subject: str, 
        html_content: str,
        text_content: Optional[str] = None,
        reply_to: Optional[str] = None,
        tags: Optional[list] = None
    ) -> bool:
        """
        Send an email using Mailgun API.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            text_content: Plain text content (optional)
            reply_to: Reply-to email address (optional)
            tags: List of tags for tracking (optional)
            
        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        if not self.mailgun_api_key:
            logger.error("Mailgun API key not configured. Cannot send email.")
            return False
            
        try:
            # Prepare the request
            url = f"{self.mailgun_api_base}/{self.mailgun_domain}/messages"
            
            # Build the data payload
            data = {
                "from": f"Spurly Support <{self.from_email}>",
                "to": to_email,
                "subject": subject,
                "html": html_content
            }
            
            # Add optional fields
            if text_content:
                data["text"] = text_content
            
            if reply_to:
                data["h:Reply-To"] = reply_to
            
            if tags:
                # Mailgun allows up to 3 tags per message
                for tag in tags[:3]:
                    data[f"o:tag"] = tag
            
            # Send the request
            logger.info(f"Sending email via Mailgun - To: {to_email}, Subject: {subject}")
            
            response = requests.post(
                url,
                auth=("api", self.mailgun_api_key),
                data=data,
                timeout=30
            )
            
            # Log response
            logger.info(f"Mailgun response - Status: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info(f"Email sent successfully. Message ID: {response_data.get('id', 'N/A')}")
                return True
            else:
                logger.error(f"Failed to send email. Status: {response.status_code}, Response: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout sending email to {to_email}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error sending email to {to_email}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending email to {to_email}: {str(e)}", exc_info=True)
            return False
    
    def send_support_request_to_team(self, support_request: Dict[str, Any]) -> bool:
        """
        Send support request notification to the support team.
        """
        subject = f"[Support Request #{support_request['request_id']}] {support_request['subject']}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 30px;">
                    <h2 style="color: #2c3e50; margin-top: 0;">New Support Request</h2>
                    
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 5px 0;"><strong>Request ID:</strong></td>
                                <td style="padding: 5px 0;">{support_request['request_id']}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px 0;"><strong>User ID:</strong></td>
                                <td style="padding: 5px 0;">{support_request['user_id']}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px 0;"><strong>From:</strong></td>
                                <td style="padding: 5px 0;">{support_request['name']} ({support_request['email']})</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px 0;"><strong>Subject:</strong></td>
                                <td style="padding: 5px 0;">{support_request['subject']}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px 0;"><strong>Priority:</strong></td>
                                <td style="padding: 5px 0;">{support_request['priority']}</td>
                            </tr>
                            <tr>
                                <td style="padding: 5px 0;"><strong>Submitted:</strong></td>
                                <td style="padding: 5px 0;">{support_request['created_at']}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <h3 style="color: #2c3e50;">Message:</h3>
                    <div style="background-color: #ffffff; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                        <p style="white-space: pre-wrap; margin: 0;">{support_request['message']}</p>
                    </div>
                    
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
                    
                    <p style="font-size: 12px; color: #666; margin: 0;">
                        This is an automated notification from Spurly Support System.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
New Support Request

Request ID: {support_request['request_id']}
User ID: {support_request['user_id']}
From: {support_request['name']} ({support_request['email']})
Subject: ‼️{support_request['subject']}
Priority: {support_request['priority']}
Submitted: {support_request['created_at']}

Message:
{support_request['message']}

---
This is an automated notification from Spurly Support System.
        """
        
        return self.send_email(
            to_email=self.support_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            reply_to=support_request['email'],
            tags=["support-request", "new-ticket", f"user-{support_request['user_id'][:8]}"]
        )
    
    def send_support_request_confirmation(self, support_request: Dict[str, Any]) -> bool:
        """
        Send confirmation email to the user who submitted the support request.
        """
        subject = f"We received your support request - #{support_request['request_id']}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 30px;">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <h1 style="color: #2c3e50; margin: 0;">Thank you for contacting us</h1>
                    </div>
                    
                    <p>Hi {support_request['name']},</p>
                    
                    <p>We've received your support request and will respond within 24 hours.</p>
                    
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>Request ID:</strong> {support_request['request_id']}</p>
                        <p style="margin: 10px 0 0 0;"><strong>Subject:</strong> {support_request['subject']}</p>
                        <p style="margin: 10px 0 0 0;"><strong>Status:</strong> <span style="color: #28a745;">Pending Review</span></p>
                    </div>
                    
                    <p><strong>Your message:</strong></p>
                    <div style="background-color: #ffffff; padding: 15px; border-left: 4px solid #3498db; margin: 20px 0;">
                        <p style="white-space: pre-wrap; color: #555; margin: 0;">{support_request['message'][:500]}{'...' if len(support_request['message']) > 500 else ''}</p>
                    </div>
                    
                    <p>Please save your Request ID for future reference. If you need to follow up on this request, 
                    simply reply to this email.</p>
                    
                    <p>Best regards,<br>
                    The Spurly Support Team</p>
                    
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
                    
                    <p style="font-size: 12px; color: #666; margin: 0;">
                        This is an automated confirmation email. If you need immediate assistance, 
                        please reply to this email with additional information.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
Thank you for contacting us

Hi {support_request['name']},

We've received your support request and will respond within 24 hours.

Request ID: {support_request['request_id']}
Subject: {support_request['subject']}
Status: Pending Review

Your message:
{support_request['message'][:500]}{'...' if len(support_request['message']) > 500 else ''}

Please save your Request ID for future reference. If you need to follow up on this request, 
simply reply to this email.

Best regards,
The Spurly Support Team

---
This is an automated confirmation email. If you need immediate assistance, 
please reply to this email with additional information.
        """
        
        return self.send_email(
            to_email=support_request['email'],
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            tags=["support-confirmation", f"request-{support_request['request_id']}", f"user-{support_request['user_id'][:8]}"]
        )

# Create a singleton instance
email_service = EmailService()