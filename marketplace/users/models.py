from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


def normalize_number(number):
    """Приводить номер телефону до єдиного формату (+380XXXXXXXXX)."""
    if not number:
        return number

    number = str(number).strip()
    if not number:
        return number
    if number.startswith("+38"):
        return number
    if number.startswith("38"):
        return "+" + number
    if number.startswith("+"):
        return number
    return "+38" + number


class CustomUserManager(BaseUserManager):
    def create_user(self, number, password=None, **extra_fields):
        if not number:
            raise ValueError("Number required")
        user = self.model(number=number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must be staff")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must be superuser")

        return self.create_user(number, password, **extra_fields)


class CustomUser(AbstractUser):
    username = None

    number = models.CharField(unique=True)
    email = models.EmailField(unique=True)

    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    middle_name = models.CharField(max_length=100, blank=True, null=True)

    default_city = models.CharField(max_length=100, blank=True)
    default_city_ref = models.CharField(max_length=36, blank=True)

    default_address = models.CharField(max_length=255, blank=True)
    default_warehouse_ref = models.CharField(max_length=36, blank=True)

    confirmed = models.BooleanField(default=True)
    is_vendor = models.BooleanField(default=False)

    USERNAME_FIELD = "number"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def clean(self):
        super().clean()
        # Нормалізація тут (а не лише в сигналі pre_save) потрібна для того,
        # щоб перевірка унікальності номера/пошти бачила вже нормалізовані дані.
        self.number = normalize_number(self.number)
        if self.email:
            self.email = self.email.strip().lower()

    def save(self, *args, **kwargs):
        self.number = normalize_number(self.number)
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.number)
