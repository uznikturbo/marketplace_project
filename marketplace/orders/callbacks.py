import base64
import binascii
import hashlib
import hmac
import json

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Order, OrderStatus, PaymentStatus


@csrf_exempt
def liqpay_callback(request):
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    data = request.POST.get("data")
    signature = request.POST.get("signature")

    if not data or not signature:
        return HttpResponse("Bad Request", status=400)

    if not settings.LIQPAY_PRIVATE_KEY:
        return HttpResponse("Payment provider is not configured", status=503)

    sign_string = settings.LIQPAY_PRIVATE_KEY + data + settings.LIQPAY_PRIVATE_KEY
    expected_signature = base64.b64encode(
        hashlib.sha1(sign_string.encode("utf-8")).digest()
    ).decode("utf-8")

    if not hmac.compare_digest(signature, expected_signature):
        return HttpResponse("Invalid signature", status=400)

    try:
        decoded_data = json.loads(base64.b64decode(data).decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return HttpResponse("Bad Request", status=400)

    if not isinstance(decoded_data, dict):
        return HttpResponse("Bad Request", status=400)

    status = decoded_data.get("status")
    order_id = decoded_data.get("order_id")

    if not order_id:
        return HttpResponse("Bad Request", status=400)

    try:
        order = Order.objects.get(id=str(order_id).split("_")[0])
    except (Order.DoesNotExist, ValueError):
        return HttpResponse("Order not found", status=404)

    if status in ("success", "wait_accept", "sandbox"):
        order.payment_status = PaymentStatus.PAID
        order.payment_id = decoded_data.get("transaction_id")
        order.status = OrderStatus.PROCESSING
        order.save(
            update_fields=["payment_status", "payment_id", "status", "updated_at"]
        )
    elif status in ("failure", "error") and order.payment_status != PaymentStatus.PAID:
        order.payment_status = PaymentStatus.FAILED
        order.save(update_fields=["payment_status", "updated_at"])

    return HttpResponse("OK")
