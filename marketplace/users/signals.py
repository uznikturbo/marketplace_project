from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save
from django.dispatch import receiver

from users.models import normalize_number

User = get_user_model()


@receiver(pre_save, sender=User)
def update_user_profile(sender, instance, **kwargs):
    if instance.pk is None:
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    if normalize_number(old_instance.number) != normalize_number(instance.number):
        instance.confirmed = False
