from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import hashlib
import base64
from .models import OrderStatus, Order, PaymentStatus
from django.http import HttpResponse
import json


@csrf_exempt
def liqpay_callback(request):
    if request.method == "POST":
        data = request.POST.get("data")
        signature = request.POST.get("signature")

        print("\n=== LIQPAY CALLBACK RECEIVED ===")
        print(f"Data present: {bool(data)}")
        print(f"Signature present: {bool(signature)}")

        if not data or not signature:
            print("❌ ОШИБКА: Пустая дата или сигнатура!")
            return HttpResponse("Bad Request", status=400)

        sign_string = settings.LIQPAY_PRIVATE_KEY + data + settings.LIQPAY_PRIVATE_KEY
        expected_signature = base64.b64encode(
            hashlib.sha1(sign_string.encode("utf-8")).digest()
        ).decode("utf-8")

        if signature == expected_signature:
            print("✅ Подпись совпала!")

            decoded_data = json.loads(base64.b64decode(data).decode("utf-8"))
            status = decoded_data.get("status")
            order_id = decoded_data.get("order_id")

            print(f"ℹ️ Статус от LiqPay: '{status}' для заказа №{order_id}")

            try:
                order = Order.objects.get(id=order_id.split("_")[0])
                if status in ["success", "wait_accept", "sandbox"]:
                    order.payment_status = PaymentStatus.PAID
                    order.payment_id = decoded_data.get("transaction_id")
                    order.status = OrderStatus.PROCESSING
                    order.save()
                    print(f"✅ Заказ №{order_id} успешно отмечен как ОПЛАЧЕН.")
                elif status in ["failure", "error"]:
                    order.payment_status = PaymentStatus.FAILED
                    order.save()
                    print(f"❌ Заказ №{order_id} отмечен как ОШИБКА ОПЛАТЫ.")
                else:
                    print(f"⚠️ Получен неизвестный статус: {status}")

            except Order.DoesNotExist:
                print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Заказ №{order_id} не найден в БД!")
        else:
            print("❌ КРИТИЧЕСКАЯ ОШИБКА: Подпись НЕ СОВПАЛА!")
            print(f"Ожидалось: {expected_signature}")
            print(f"Пришло: {signature}")

        print("================================\n")
        return HttpResponse("OK")

    return HttpResponse("Method not allowed", status=405)
