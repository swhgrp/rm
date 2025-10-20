"""
HR Services
"""
from hr.services.email import EmailService, send_new_hire_notification, send_termination_notification

__all__ = [
    "EmailService",
    "send_new_hire_notification",
    "send_termination_notification"
]
