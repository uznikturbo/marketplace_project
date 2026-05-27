from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save
from django.dispatch import receiver

User = get_user_model()


@receiver(pre_save, sender=User)
def check_phone(sender, instance, **kwargs):
    phone_str = str(instance.number).strip()
    if phone_str.startswith("+38"):
        return
    if phone_str.startswith("38"):
        instance.number = "+" + phone_str
    else:
        instance.number = "+38" + phone_str
