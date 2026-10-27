from django.urls import reverse

from catalog.models import Cart, CartItem, Favorite, ProductRating

from .base import BaseTestCase, make_category, make_product, make_user


class CatalogViewTests(BaseTestCase):
    def test_lists_only_available_products(self):
        available = make_product(name="Available product")
        hidden = make_product(name="Hidden product", is_available=False)

        response = self.client.get(reverse("catalog"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, available.name)
        self.assertNotContains(response, hidden.name)

    def test_search_matches_name(self):
        match = make_product(name="Wireless keyboard")
        other = make_product(name="Office chair")

        response = self.client.get(reverse("catalog"), {"q": "keyboard"})

        self.assertContains(response, match.name)
        self.assertNotContains(response, other.name)

    def test_search_matches_description(self):
        match = make_product(name="Gadget", description="Has a long battery life")
        make_product(name="Other gadget", description="Nothing special")

        response = self.client.get(reverse("catalog"), {"q": "battery"})

        self.assertContains(response, match.name)

    def test_category_filter_includes_subcategories(self):
        root = make_category(name="Electronics")
        child = make_category(name="Phones", parent=root)
        in_tree = make_product(name="Smartphone", category=child)
        outside = make_product(name="Sofa")

        response = self.client.get(reverse("catalog"), {"category": root.id})

        self.assertContains(response, in_tree.name)
        self.assertNotContains(response, outside.name)

    def test_unknown_category_returns_empty_list(self):
        make_product(name="Visible product")

        response = self.client.get(reverse("catalog"), {"category": 999999})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["products"]), [])

    def test_invalid_category_parameter_does_not_crash(self):
        make_product(name="Visible product")

        response = self.client.get(reverse("catalog"), {"category": "not-a-number"})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["current_category_id"])

    def test_product_detail_renders(self):
        product = make_product(name="Detail product")

        response = self.client.get(reverse("product_detail", args=[product.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, product.name)

    def test_product_detail_missing_product_returns_404(self):
        response = self.client.get(reverse("product_detail", args=[999999]))

        self.assertEqual(response.status_code, 404)


class CatalogPaginationTests(BaseTestCase):
    def _create_products(self, count):
        return [make_product(name=f"Paged product {i:02d}") for i in range(count)]

    def test_first_page_contains_page_size_products(self):
        products = self._create_products(13)

        response = self.client.get(reverse("catalog"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["products"]), 12)
        self.assertEqual(response.context["paginator"].count, 13)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_second_page_contains_the_rest(self):
        products = self._create_products(13)

        first = self.client.get(reverse("catalog"))
        second = self.client.get(reverse("catalog"), {"page": 2})

        first_names = {product.name for product in first.context["products"]}
        second_names = {product.name for product in second.context["products"]}

        self.assertEqual(len(second_names), 1)
        self.assertEqual(first_names | second_names, {p.name for p in products})
        self.assertFalse(first_names & second_names)

    def test_page_out_of_range_returns_last_page(self):
        self._create_products(13)

        response = self.client.get(reverse("catalog"), {"page": 999})

        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(len(response.context["products"]), 1)

    def test_pagination_preserves_search_query(self):
        self._create_products(13)

        response = self.client.get(
            reverse("catalog"), {"q": "Paged product", "page": 2}
        )

        self.assertContains(response, "q=Paged+product&amp;page=1")

    def test_pagination_preserves_category_filter(self):
        root = make_category(name="Paged root")
        for i in range(13):
            make_product(name=f"Category product {i:02d}", category=root)

        response = self.client.get(
            reverse("catalog"), {"category": root.id, "page": 2}
        )

        self.assertContains(response, f"category={root.id}&amp;page=1")

    def test_pagination_is_hidden_for_a_single_page(self):
        self._create_products(12)

        response = self.client.get(reverse("catalog"))

        self.assertEqual(response.context["paginator"].count, 12)
        self.assertNotContains(response, 'class="pagination"')


class ReviewTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product()
        self.url = reverse("submit_review", args=[self.product.pk])

    def test_anonymous_user_is_redirected(self):
        response = self.client.post(self.url, {"rating": 5})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProductRating.objects.count(), 0)

    def test_unconfirmed_user_cannot_leave_review(self):
        user = make_user(confirmed=False)
        self.client.force_login(user)

        response = self.client.post(self.url, {"rating": 5})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProductRating.objects.count(), 0)

    def test_valid_review_is_created_and_redirects(self):
        user = make_user(confirmed=True)
        self.client.force_login(user)

        response = self.client.post(self.url, {"rating": 4, "review": "Nice"})

        self.assertRedirects(
            response, reverse("product_detail", args=[self.product.pk])
        )
        review = ProductRating.objects.get(product=self.product, user=user)
        self.assertEqual(review.rating, 4)
        self.assertEqual(review.review, "Nice")

    def test_invalid_rating_is_not_saved(self):
        user = make_user(confirmed=True)
        self.client.force_login(user)

        response = self.client.post(self.url, {"rating": 9})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProductRating.objects.count(), 0)

    def test_non_numeric_rating_is_not_saved(self):
        user = make_user(confirmed=True)
        self.client.force_login(user)

        self.client.post(self.url, {"rating": "five"})

        self.assertEqual(ProductRating.objects.count(), 0)

    def test_get_is_not_allowed(self):
        user = make_user(confirmed=True)
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)


class CartViewTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product(quantity=5)

    def _guest_cart(self):
        return Cart.objects.get(session_key=self.client.session["cart_session_key"])

    def test_add_creates_guest_cart_item(self):
        response = self.client.post(
            reverse("cart_add", args=[self.product.pk]), {"quantity": 2}
        )

        self.assertEqual(response.status_code, 302)
        cart = self._guest_cart()
        self.assertEqual(cart.items.get(product=self.product).quantity, 2)

    def test_add_accumulates_quantity(self):
        url = reverse("cart_add", args=[self.product.pk])
        self.client.post(url, {"quantity": 2})
        self.client.post(url, {"quantity": 3})

        self.assertEqual(self._guest_cart().items.get().quantity, 5)

    def test_add_clamps_quantity_to_stock(self):
        self.client.post(
            reverse("cart_add", args=[self.product.pk]), {"quantity": 99}
        )

        self.assertEqual(self._guest_cart().items.get().quantity, 5)

    def test_add_rejects_unavailable_product(self):
        self.product.is_available = False
        self.product.save()

        self.client.post(
            reverse("cart_add", args=[self.product.pk]), {"quantity": 1}
        )

        self.assertFalse(CartItem.objects.filter(product=self.product).exists())

    def test_add_rejects_out_of_stock_product(self):
        self.product.quantity = 0
        self.product.save()

        self.client.post(
            reverse("cart_add", args=[self.product.pk]), {"quantity": 1}
        )

        self.assertFalse(CartItem.objects.filter(product=self.product).exists())

    def test_add_with_invalid_quantity_defaults_to_one(self):
        self.client.post(
            reverse("cart_add", args=[self.product.pk]), {"quantity": "abc"}
        )

        self.assertEqual(self._guest_cart().items.get().quantity, 1)

    def test_add_requires_post(self):
        response = self.client.get(reverse("cart_add", args=[self.product.pk]))

        self.assertEqual(response.status_code, 405)

    def test_authenticated_user_gets_persistent_cart(self):
        user = make_user()
        self.client.force_login(user)

        self.client.post(
            reverse("cart_add", args=[self.product.pk]), {"quantity": 2}
        )

        cart = Cart.objects.get(user=user)
        self.assertEqual(cart.items.get(product=self.product).quantity, 2)

    def test_update_sets_quantity(self):
        url = reverse("cart_add", args=[self.product.pk])
        self.client.post(url, {"quantity": 1})

        response = self.client.post(
            reverse("cart_update", args=[self.product.pk]), {"quantity": 4}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._guest_cart().items.get().quantity, 4)

    def test_update_clamps_quantity_to_stock(self):
        self.client.post(
            reverse("cart_add", args=[self.product.pk]), {"quantity": 1}
        )

        self.client.post(
            reverse("cart_update", args=[self.product.pk]), {"quantity": 50}
        )

        self.assertEqual(self._guest_cart().items.get().quantity, 5)

    def test_update_requires_post(self):
        response = self.client.get(reverse("cart_update", args=[self.product.pk]))

        self.assertEqual(response.status_code, 405)

    def test_remove_deletes_item(self):
        self.client.post(
            reverse("cart_add", args=[self.product.pk]), {"quantity": 2}
        )

        response = self.client.post(
            reverse("cart_remove", args=[self.product.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._guest_cart().items.count(), 0)

    def test_remove_requires_post(self):
        response = self.client.get(reverse("cart_remove", args=[self.product.pk]))

        self.assertEqual(response.status_code, 405)

    def test_remove_does_not_touch_other_users_cart(self):
        other_user = make_user()
        other_cart = Cart.objects.create(user=other_user)
        CartItem.objects.create(cart=other_cart, product=self.product, quantity=1)

        self.client.post(reverse("cart_remove", args=[self.product.pk]))

        self.assertTrue(CartItem.objects.filter(cart=other_cart).exists())

    def test_cart_detail_renders(self):
        self.client.post(
            reverse("cart_add", args=[self.product.pk]), {"quantity": 1}
        )

        response = self.client.get(reverse("cart_detail"))

        self.assertEqual(response.status_code, 200)


class FavoriteTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product()

    def test_authenticated_toggle_adds_and_removes(self):
        user = make_user()
        self.client.force_login(user)
        url = reverse("toggle_favorite", args=[self.product.pk])

        first = self.client.post(url)
        self.assertEqual(first.json()["status"], "added")
        self.assertTrue(
            Favorite.objects.filter(user=user, product=self.product).exists()
        )

        second = self.client.post(url)
        self.assertEqual(second.json()["status"], "removed")
        self.assertFalse(
            Favorite.objects.filter(user=user, product=self.product).exists()
        )

    def test_anonymous_toggle_uses_session(self):
        url = reverse("toggle_favorite", args=[self.product.pk])

        first = self.client.post(url)
        self.assertEqual(first.json()["status"], "added")
        self.assertEqual(self.client.session["favorites"], [self.product.pk])

        second = self.client.post(url)
        self.assertEqual(second.json()["status"], "removed")
        self.assertEqual(self.client.session["favorites"], [])

    def test_wishlist_shows_only_own_favorites(self):
        user = make_user()
        mine = make_product(name="My favorite")
        foreign = make_product(name="Foreign favorite")
        Favorite.objects.create(user=user, product=mine)
        Favorite.objects.create(user=make_user(), product=foreign)
        self.client.force_login(user)

        response = self.client.get(reverse("wishlist_view"))

        self.assertContains(response, mine.name)
        self.assertNotContains(response, foreign.name)

    def test_anonymous_wishlist_uses_session(self):
        product = make_product(name="Session favorite")
        session = self.client.session
        session["favorites"] = [product.pk]
        session.save()

        response = self.client.get(reverse("wishlist_view"))

        self.assertContains(response, product.name)


class CartMergeSignalTests(BaseTestCase):
    def test_guest_cart_is_merged_on_login(self):
        product = make_product(quantity=10)
        user = make_user(password="StrongPass123!")
        self.client.post(
            reverse("cart_add", args=[product.pk]), {"quantity": 2}
        )
        guest_cart_id = Cart.objects.get(
            session_key=self.client.session["cart_session_key"]
        ).pk

        self.client.post(
            reverse("login"),
            {"username": user.number, "password": "StrongPass123!"},
        )

        user_cart = Cart.objects.get(user=user)
        self.assertEqual(user_cart.items.get(product=product).quantity, 2)
        self.assertFalse(Cart.objects.filter(pk=guest_cart_id).exists())

    def test_quantities_are_summed_when_both_carts_have_product(self):
        product = make_product(quantity=10)
        user = make_user(password="StrongPass123!")
        user_cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=user_cart, product=product, quantity=3)

        self.client.post(
            reverse("cart_add", args=[product.pk]), {"quantity": 2}
        )
        self.client.post(
            reverse("login"),
            {"username": user.number, "password": "StrongPass123!"},
        )

        self.assertEqual(user_cart.items.get(product=product).quantity, 5)

    def test_empty_guest_cart_is_not_merged(self):
        user = make_user(password="StrongPass123!")

        self.client.post(
            reverse("login"),
            {"username": user.number, "password": "StrongPass123!"},
        )

        self.assertFalse(Cart.objects.filter(user=user).exists())


class CartContextProcessorTests(BaseTestCase):
    def test_anonymous_page_view_does_not_create_cart(self):
        self.client.get(reverse("home"))

        self.assertEqual(Cart.objects.count(), 0)

    def test_catalog_page_view_does_not_create_cart(self):
        make_product()

        self.client.get(reverse("catalog"))

        self.assertEqual(Cart.objects.count(), 0)
