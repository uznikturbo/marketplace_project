from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save
from django.dispatch import receiver

from users.models import normalize_number

User = get_user_model()


@receiver(pre_save, sender=User)
def check_phone(sender, instance, **kwargs):
    instance.number = normalize_number(instance.number)
