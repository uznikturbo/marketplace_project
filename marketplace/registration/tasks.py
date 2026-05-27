import requests
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_sms_conf_task(self, phone, code):
    api_url = "https:/"
    payload = {
        "api_key": "",
        "to": phone,
        "message": f"Ваш код підтвердження: {code}. Дійсний 5 хвилин.",
    }
    logger.info(f"Set message to {phone}")

    try:
        response = requests.post(api_url, json=payload, timeout=5)

        if response.status_code >= 500:
            raise requests.RemoteDisconnected("API problem")

        return response.status_code == 200

    except (requests.RequestException, requests.RemoteDisconnected) as exc:
        logger.warning(f"Error sending SMS. Retrying...")
        raise self.retry(exc=exc)
