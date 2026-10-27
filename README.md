# Marketplace

A full-stack e-commerce marketplace built with Django. It ships with a
storefront, a guest-friendly cart, checkout with delivery and payment
options, a vendor dashboard, SMS phone verification, and integrations with
Nova Poshta and LiqPay.

The UI is server-rendered (Django templates) with no separate frontend
build step.

---

## Table of contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Environment variables](#environment-variables)
- [Running the tests](#running-the-tests)
- [How the main flows work](#how-the-main-flows-work)
- [Security notes](#security-notes)
- [Known limitations](#known-limitations)

---

## Features

### Storefront

- Product catalog with search, category filtering (including nested
  categories) and caching of category trees.
- Product pages with average rating, reviews and active discounts.
- Wishlist for both authenticated users and guests (session based).
- Responsive templates with an inline design system.

### Cart and checkout

- Cart for authenticated users and guests; the guest cart is merged into
  the user cart on login.
- Quantity is validated against available stock on every operation.
- Checkout validates the cart, re-checks stock inside a transaction with
  `select_for_update`, and rolls the whole order back if anything fails.
- Order items keep a price snapshot, so later price changes do not alter
  historical orders.
- Cash-on-delivery fee is calculated as `20 UAH + 2%` of the cart total.

### Payments

- LiqPay integration (sandbox and production) with a signed redirect and
  a server callback.
- The callback verifies the signature with `hmac.compare_digest`, handles
  malformed payloads, ignores unknown orders, and never downgrades an
  already paid order.
- Payment flows are disabled gracefully when keys are not configured.

### Delivery

- Nova Poshta city and warehouse lookup proxied through the backend, with
  request timeouts and error handling.
- Branch, parcel locker and courier delivery options.

### Accounts

- Phone number as the login identifier, with normalization to
  `+380XXXXXXXXX` and case-insensitive e-mail uniqueness.
- Registration, login with a safe `next` redirect, and logout.
- SMS confirmation of the phone number with a resend cooldown, a limit of
  five verification attempts and a fresh code invalidating the counter.
- Profile editing, order history and wishlist pages.

### Vendors

- Vendor-only dashboard protected by a dedicated decorator.
- Product CRUD with an image formset; vendors can only touch their own
  products.
- Discount management with validation of percentage and date range.
- Vendor order list with revenue statistics and status updates.

### Operations

- `/health` endpoint that checks the database and returns `200`/`503` JSON.
- `/favicon.ico` served directly by the application.
- Django admin customized with Jazzmin.
- Celery worker for background SMS delivery.

---

## Tech stack

| Layer            | Technology                                  |
| ---------------- | ------------------------------------------- |
| Language         | Python 3.12+                                |
| Framework        | Django 6.0                                  |
| Database         | PostgreSQL (`psycopg2-binary`)              |
| Cache            | Redis                                       |
| Background jobs  | Celery + Redis                              |
| Static files     | WhiteNoise                                  |
| Admin theme      | django-jazzmin                              |
| Phone numbers    | django-phonenumber-field                    |
| Payments         | LiqPay                                      |
| Delivery         | Nova Poshta API                             |
| Configuration    | python-dotenv                               |
| WSGI server      | Gunicorn                                    |

---

## Project structure

```text
rozetka2.0/
├── .env.example              # documented environment template
├── requirements.txt          # pinned dependencies
├── README.md
├── .venv/                    # local virtualenv (not tracked)
└── marketplace/
    ├── manage.py
    ├── marketplace/          # project configuration
    │   ├── settings.py
    │   ├── urls.py
    │   ├── celery.py
    │   ├── wsgi.py
    │   └── asgi.py
    ├── catalog/              # products, categories, cart, favorites, reviews
    ├── orders/               # checkout, orders, LiqPay, Nova Poshta
    ├── users/                # custom user model, profile, SMS verification
    ├── registration/         # sign-up, login, SMS task and code generation
    ├── vendors/              # vendor dashboard and product management
    ├── core/                 # home page, health check, middleware, favicon
    ├── templates/            # shared templates
    ├── static/               # source static assets
    └── tests/                # test suite (176 tests)
```

Each app owns its models, views, URLs and templates. Shared helpers live in
`catalog/utils.py` and `core/`.

---

## Getting started

### Prerequisites

- Python 3.12 or newer
- PostgreSQL 14+
- Redis 6+ (cache and Celery broker)
- A virtualenv tool (`venv` is enough)

### 1. Clone and create a virtualenv

```bash
git clone https://github.com/uznikturbo/marketplace_project.git
cd rozetka2.0
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure the environment

```bash
cp .env.example .env
```

Open `.env` and set at least:

- `DJANGO_SECRET_KEY` — generate one with:
  ```bash
  python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
  ```
- `POSTGRES_PASSWORD`
- `DJANGO_DEBUG=True` for local development

`DJANGO_SECRET_KEY` is required when `DJANGO_DEBUG=False`; the application
refuses to start without it.

### 3. Create the database

```bash
sudo -u postgres psql -c "CREATE USER myuser WITH PASSWORD 'your-password' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE marketplace_db OWNER myuser;"
```

`CREATEDB` is required because Django creates a separate test database.

### 4. Apply migrations

Migration files are generated locally and are not tracked in this
repository yet, so create them first:

```bash
cd marketplace
python manage.py makemigrations
python manage.py migrate
```

### 5. Start Redis (if it is not running)

```bash
redis-server
```

### 6. Run the application

```bash
cd marketplace
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

Create an administrator:

```bash
python manage.py createsuperuser
```

The admin panel is available at <http://127.0.0.1:8000/admin/>.

### 7. Run the Celery worker (optional)

SMS messages are sent in the background. Without a worker, the task is
queued but not executed.

```bash
cd marketplace
celery -A marketplace worker -l info
```

If `SMS_API_URL` is empty, the task writes the confirmation code to the
worker log instead of sending an SMS, which is convenient for local
development.

---

## Environment variables

All variables are read in `marketplace/settings.py` via `python-dotenv`.
See `.env.example` for a ready-to-copy template.

| Variable                      | Required | Default                              | Description                                              |
| ----------------------------- | -------- | ------------------------------------ | -------------------------------------------------------- |
| `DJANGO_SECRET_KEY`           | yes\*    | —                                    | Django secret key. Required when `DJANGO_DEBUG=False`.   |
| `DJANGO_DEBUG`                | no       | `False`                              | Enables debug mode.                                      |
| `DJANGO_ALLOWED_HOSTS`        | no       | `localhost,127.0.0.1,.ngrok-free.app,.ngrok.io` | Comma-separated `ALLOWED_HOSTS`.                |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | no       | `https://*.ngrok-free.app`           | Comma-separated trusted origins.                         |
| `POSTGRES_DB`                 | no       | `marketplace_db`                     | Database name.                                           |
| `POSTGRES_USER`               | no       | `myuser`                             | Database user.                                           |
| `POSTGRES_PASSWORD`           | yes      | —                                    | Database password.                                       |
| `POSTGRES_HOST`               | no       | `localhost`                          | Database host.                                           |
| `POSTGRES_PORT`               | no       | `5432`                               | Database port.                                           |
| `REDIS_CACHE_URL`             | no       | `redis://127.0.0.1:6379/1`           | Redis URL used for the cache.                            |
| `CELERY_BROKER_URL`           | no       | `redis://127.0.0.1:6379/0`           | Celery broker URL.                                       |
| `CELERY_RESULT_BACKEND`       | no       | value of `CELERY_BROKER_URL`         | Celery result backend.                                   |
| `NOVAPOST_API`                | no       | empty                                | Nova Poshta API key. Lookup endpoints return 503 if unset.|
| `LIQPAY_PUBLIC_KEY`           | no       | empty                                | LiqPay public key. Online payment is disabled if unset.  |
| `LIQPAY_PRIVATE_KEY`          | no       | empty                                | LiqPay private key, used for signatures.                 |
| `SMS_API_URL`                 | no       | empty                                | SMS provider endpoint. Codes are logged when unset.      |
| `SMS_API_KEY`                 | no       | empty                                | SMS provider API key.                                    |

\* Required in production (`DJANGO_DEBUG=False`).

---

## Running the tests

The suite contains **176 tests** and does not require Redis: it switches to
an in-memory cache and a fast password hasher.

```bash
cd marketplace
python manage.py test
```

Useful variants:

```bash
# one module
python manage.py test tests.test_orders

# one class or test
python manage.py test tests.test_orders.CheckoutTests
python manage.py test tests.test_orders.CheckoutTests.test_postpaid_order_is_created

# verbose
python manage.py test -v 2
```

Test modules:

| Module                     | What it covers                                                        |
| -------------------------- | --------------------------------------------------------------------- |
| `tests/test_models.py`     | Phone/e-mail normalization, uniqueness, ratings, prices, discounts, cart totals |
| `tests/test_catalog.py`    | Catalog, search, categories, reviews, cart rules, favorites, cart merge |
| `tests/test_orders.py`     | Checkout, stock rollback, payments, LiqPay callback, Nova Poshta        |
| `tests/test_users.py`      | Profile, order history, SMS send/verify limits                         |
| `tests/test_vendors.py`    | Vendor access, product ownership, discounts, vendor orders             |
| `tests/test_registration.py` | Registration, login and `next` safety, SMS task behavior            |
| `tests/test_core.py`       | Home page, health check, favicon, timezone middleware                  |

> The test database is created and destroyed automatically. The database
> user therefore needs the `CREATEDB` privilege.

---

## How the main flows work

### Guest cart and login

A guest cart is stored with the session key. Before `login()` rotates the
session, the original key is saved in `request.session["cart_session_key"]`,
so the `user_logged_in` signal can find the guest cart, merge its items into
the user cart and delete the guest one.

### Checkout

1. The cart is validated (must exist and be non-empty).
2. The form is validated.
3. Inside `transaction.atomic()` every product is locked with
   `select_for_update`, availability and stock are re-checked, `OrderItem`
   rows are created with a price snapshot, and stock is decremented.
4. The cart is cleared and the order id is stored in the session for guests.
5. LiqPay orders are redirected to a signed payment page; cash-on-delivery
   orders go straight to the success page.

### LiqPay callback

`POST /orders/liqpay-callback/` receives `data` and `signature`:

- the signature is verified as `base64(sha1(private_key + data + private_key))`
  using a constant-time comparison;
- the payload is decoded and validated;
- `success`, `wait_accept` and `sandbox` mark the order as paid and move it
  to processing;
- `failure` and `error` mark it as failed, unless it is already paid;
- unknown orders return `404`, malformed requests return `400`.

### SMS verification

- A six-digit code is generated with `secrets`, stored in the cache for five
  minutes and sent by a Celery task.
- Resending is blocked for 60 seconds.
- Five wrong attempts block verification until a new code is requested.
- If the broker is unavailable, the endpoint returns `503` and clears the
  cooldown so the user is not locked out.

---

## Security notes

- Secrets are read from environment variables; `.env` is git-ignored.
- All state-changing cart endpoints are `POST`-only and CSRF-protected.
- Order pages and payment pages enforce ownership (no IDOR).
- Guest orders are visible only from the session that created them.
- Login redirects use `url_has_allowed_host_and_scheme`.
- Payment callbacks are signature-checked with `hmac.compare_digest`.
- Passwords are hashed with Django's default hasher; the test suite uses a
  faster one for speed only.

Before deploying:

- set `DJANGO_DEBUG=False` and a strong `DJANGO_SECRET_KEY`;
- configure HTTPS and set `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
  `SECURE_SSL_REDIRECT` and HSTS;
- run `python manage.py check --deploy`;
- run `python manage.py collectstatic`;
- serve the app with Gunicorn behind a reverse proxy.

---

## Known limitations

- No API layer (DRF); everything is server-rendered.
- No CI pipeline yet.
- Migration files are not committed, so a fresh clone must run
  `makemigrations` (see step 4).
- `staticfiles/` (collected assets) is currently tracked in git; ideally it
  should be generated during deployment.
- `debug_toolbar` is installed unconditionally and should be moved to a
  development-only settings module.
- Payment and SMS integrations are tested with mocks; no sandbox end-to-end
  tests are included.

---

## License

This project was built for learning and portfolio purposes.
