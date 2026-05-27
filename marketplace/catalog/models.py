from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

User = get_user_model()


class Category(models.Model):
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="subcategories",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"

    def __str__(self):
        full_path = [self.name]
        k = self.parent
        while k is not None:
            full_path.append(k.name)
            k = k.parent
        return " -> ".join(full_path[::-1])


class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="products"
    )
    properties = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_available = models.BooleanField(default=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return self.name

    @property
    def average_rating(self):
        avg = self.ratings.aggregate(models.Avg("rating"))["rating__avg"]
        return round(avg, 1) if avg else 0.0

    @property
    def ratings_count(self):
        return self.ratings.count()

    @property
    def rating_percentage(self):
        return (self.average_rating / 5) * 100

    @property
    def active_discount(self):
        return self.discounts.filter(
            start_at__lte=timezone.now(), end_at__gte=timezone.now()
        ).first()

    @property
    def is_discounted(self):
        return self.active_discount is not None

    @property
    def get_current_price(self):
        """Рахує актуальну ціну"""
        discount = self.active_discount
        if discount:
            # Обов'язково Decimal, щоб не було конфліктів типів
            discount_amount = (self.price * Decimal(discount.value)) / 100
            return self.price - discount_amount
        return self.price


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image_url = models.URLField()


class ProductRating(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="ratings"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveIntegerField()
    review = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ProductDiscount(models.Model):
    value = models.PositiveSmallIntegerField(default=1)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="discounts"
    )


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    session_key = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_total_price(self):
        return sum(item.get_total_price() for item in self.items.all())

    def get_raw_total_price(self):
        return sum(item.product.price * item.quantity for item in self.items.all())

    def get_discount_amount(self):
        return self.get_raw_total_price() - self.get_total_price()


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def get_total_price(self):
        return self.product.get_current_price * self.quantity


class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="favorited_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product")
