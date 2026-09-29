import os
import requests
from celery import Celery

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"

# In production, pass a real Slack/Discord webhook URL via Docker environment variables
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

celery_app = Celery("opspilot_tasks", broker=CELERY_BROKER_URL)

@celery_app.task
def send_incident_alert(incident_title: str, severity: str):
    alert_msg = f"🚨 *ALERT: High Severity Incident [{severity.upper()}]* 🚨\nTitle: {incident_title}"
    print(alert_msg)
    
    if WEBHOOK_URL:
        try:
            response = requests.post(WEBHOOK_URL, json={"text": alert_msg, "content": alert_msg})
            response.raise_for_status()
            return "Alert dispatched successfully"
        except Exception as e:
            return f"Failed to dispatch alert: {str(e)}"
            
    return "Webhook URL not configured. Logged to console only."
