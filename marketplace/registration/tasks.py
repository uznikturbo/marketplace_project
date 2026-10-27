import requests
from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_sms_conf_task(self, phone, code):
    api_url = (settings.SMS_API_URL or "").strip()
    api_key = (settings.SMS_API_KEY or "").strip()

    # Без налаштованого провайдера не робимо невалідний HTTP-запит.
    # Код пишемо в лог, щоб функцію можна було перевірити локально.
    if not api_url:
        logger.warning(
            "SMS_API_URL is not configured. Confirmation code for %s: %s", phone, code
        )
        return False

    payload = {
        "api_key": api_key,
        "to": phone,
        "message": f"Ваш код підтвердження: {code}. Дійсний 5 хвилин.",
    }

    try:
        response = requests.post(api_url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("Error sending SMS to %s: %s", phone, exc)
        raise self.retry(exc=exc)
